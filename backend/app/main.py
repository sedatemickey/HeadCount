import asyncio
import logging
import shutil
import threading
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path, PureWindowsPath
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import Settings
from .db import HeadMark, Job, Record, Upload, make_engine, migrate, utcnow
from .detection import HeadDetector
from .jobs import JobManager
from .schemas import CreateJob, CreateRecord, UpdateRecord
from .storage import InvalidImage, prepare_image, remove_directory

logger = logging.getLogger(__name__)


def record_dict(record, detail=True):
    base = {
        key: getattr(record, key)
        for key in (
            "id",
            "original_name",
            "width",
            "height",
            "uploaded_at",
            "captured_at",
            "timezone",
            "head_count",
            "detection_status",
            "model_version",
            "created_at",
            "updated_at",
            "version",
        )
    }
    base.update(
        {
            "image_url": f"/api/media/records/{record.id}/display",
            "thumbnail_url": f"/api/media/records/{record.id}/thumbnail",
            "original_url": f"/api/media/records/{record.id}/original",
        }
    )
    if detail:
        base["marks"] = [
            {
                key: getattr(mark, key)
                for key in ("id", "x", "y", "bbox", "source", "confidence", "is_modified")
            }
            for mark in record.marks
        ]
        base["initial_detections"] = record.initial_detections
        base["detection_config"] = record.detection_config
    return base


def create_app(settings: Settings | None = None, detector=None) -> FastAPI:
    settings = settings or Settings()
    settings.data_dir = settings.data_dir.resolve()
    ZoneInfo(settings.timezone)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    for name in ("temp", "photos"):
        (settings.data_dir / name).mkdir(exist_ok=True)
    engine, sessions = make_engine(settings.database_url)
    migrate(settings.database_url)
    lock = threading.RLock()
    detector = detector or HeadDetector(settings.model_path, settings.provider)
    jobs = JobManager(sessions, detector, settings.data_dir, lock)

    def cleanup():
        with lock, sessions.begin() as db:
            now = utcnow()
            active_uploads = set(
                db.scalars(select(Job.upload_id).where(Job.status.in_(["queued", "running"])))
            )
            expired = list(
                db.scalars(
                    select(Upload).where(Upload.expires_at < now, Upload.saved_record_id.is_(None))
                )
            )
            for upload in expired:
                if upload.id not in active_uploads:
                    remove_directory(settings.data_dir / "temp" / upload.id)
                    db.delete(upload)
            # A crash between filesystem copy and DB commit may leave an unreferenced directory.
            known_photos = set(db.scalars(select(Record.id)))
            known_temp = set(db.scalars(select(Upload.id)))
            cutoff = datetime.now(timezone.utc).timestamp() - settings.temp_ttl_hours * 3600
            for name, known in (("photos", known_photos), ("temp", known_temp)):
                for path in (settings.data_dir / name).iterdir():
                    saved_temp = (
                        name == "temp"
                        and db.get(Upload, path.name) is not None
                        and db.get(Upload, path.name).saved_record_id is not None
                    )
                    if (
                        path.is_dir()
                        and (path.name not in known or saved_temp)
                        and path.stat().st_mtime < cutoff
                    ):
                        remove_directory(path)

    async def cleanup_loop():
        while True:
            await asyncio.sleep(3600)
            try:
                await run_in_threadpool(cleanup)
            except Exception:
                logger.exception("Temporary file cleanup failed")

    @asynccontextmanager
    async def lifespan(_):
        jobs.recover()
        cleanup()
        task = asyncio.create_task(cleanup_loop())
        yield
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await run_in_threadpool(jobs.close)
        engine.dispose()

    app = FastAPI(
        title="HeadCount",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.sessions = sessions
    app.state.cleanup = cleanup
    app.state.jobs = jobs
    app.state.settings = settings
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"]
    )
    allowed_origins = [
        f"http://{host}:{port}" for host in ("localhost", "127.0.0.1") for port in (5173, 8000)
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def local_origin(request: Request, call_next):
        origin = request.headers.get("origin")
        same_origin = str(request.base_url).rstrip("/")
        if (
            request.method in ("POST", "PUT", "DELETE")
            and origin
            and origin not in [same_origin, *allowed_origins]
        ):
            return JSONResponse({"detail": "仅允许本地页面操作"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(Exception)
    async def internal_error(_, exc):
        logger.exception("Unhandled application error", exc_info=exc)
        return JSONResponse(
            {"detail": "本地服务处理失败，请查看终端日志；已编辑内容请勿关闭。"}, status_code=500
        )

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "timezone": settings.timezone,
            "model": detector.status(),
            "limits": {
                "max_upload_mb": settings.max_upload_bytes // 1024 // 1024,
                "max_pixels": settings.max_pixels,
            },
        }

    def finish_upload(directory, upload_id, name):
        ext, width, height = prepare_image(directory / "incoming", directory, settings.max_pixels)
        uploaded_at = utcnow()
        expires_at = (
            datetime.now(timezone.utc) + timedelta(hours=settings.temp_ttl_hours)
        ).isoformat()
        with lock, sessions.begin() as db:
            db.add(
                Upload(
                    id=upload_id,
                    original_name=name,
                    original_ext=ext,
                    width=width,
                    height=height,
                    uploaded_at=uploaded_at,
                    expires_at=expires_at,
                )
            )
        return {
            "id": upload_id,
            "original_name": name,
            "width": width,
            "height": height,
            "uploaded_at": uploaded_at,
            "captured_at": datetime.fromisoformat(uploaded_at)
            .replace(second=0, microsecond=0)
            .isoformat(),
            "timezone": settings.timezone,
            "image_url": f"/api/media/uploads/{upload_id}/display",
            "original_url": f"/api/media/uploads/{upload_id}/original",
        }

    @app.post("/api/uploads", status_code=201)
    async def upload_photo(file: UploadFile = File(...)):
        upload_id = str(uuid4())
        directory = settings.data_dir / "temp" / upload_id
        directory.mkdir()
        try:
            size = 0
            with (directory / "incoming").open("wb") as destination:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > settings.max_upload_bytes:
                        raise HTTPException(413, "图片不能超过 25 MB")
                    destination.write(chunk)
            name = PureWindowsPath(Path(file.filename or "照片").name).name[:255]
            return await run_in_threadpool(finish_upload, directory, upload_id, name)
        except InvalidImage as exc:
            remove_directory(directory)
            raise HTTPException(422, str(exc)) from exc
        except BaseException:
            remove_directory(directory)
            raise
        finally:
            await file.close()

    @app.post("/api/detection-jobs", status_code=202)
    def create_job(body: CreateJob):
        upload_id = str(body.upload_id)
        with lock, sessions.begin() as db:
            upload = db.get(Upload, upload_id)
            if not upload or upload.expires_at < utcnow():
                raise HTTPException(404, "临时图片不存在或已过期，请重新上传")
            if upload.saved_record_id:
                raise HTTPException(409, "该照片已保存，重新识别请重新上传")
            existing = db.scalar(
                select(Job).where(Job.upload_id == upload_id, Job.status.in_(["queued", "running"]))
            )
            if existing:
                return {"id": existing.id, "status": existing.status}
            pending = db.scalar(
                select(func.count()).select_from(Job).where(Job.status.in_(["queued", "running"]))
            )
            if pending >= settings.max_pending_jobs:
                raise HTTPException(429, "识别队列已满，请稍后重试")
            status = detector.status()
            if not status["ready"]:
                raise HTTPException(503, status["error"])
            job = Job(id=str(uuid4()), upload_id=upload_id, mode=body.mode, status="queued")
            db.add(job)
            job_id = job.id
        jobs.submit(job_id)
        return {"id": job_id, "status": "queued"}

    @app.get("/api/detection-jobs/{job_id}")
    def get_job(job_id: UUID):
        with sessions() as db:
            job = db.get(Job, str(job_id))
            if not job:
                raise HTTPException(404, "识别任务不存在")
            return {"id": job.id, "status": job.status, "error": job.error, "result": job.result}

    def set_marks(db, record, marks):
        ids = [str(mark.id) for mark in marks]
        if ids and db.scalar(
            select(HeadMark.id)
            .where(HeadMark.id.in_(ids), HeadMark.record_id != record.id)
            .limit(1)
        ):
            raise HTTPException(409, "标记 ID 与其他记录冲突")
        record.marks.clear()
        db.flush()
        for mark in marks:
            values = mark.model_dump(mode="json")
            record.marks.append(HeadMark(**values))
        record.head_count = len(marks)

    @app.post("/api/records", status_code=201)
    def save_record(body: CreateRecord):
        upload_id = str(body.upload_id)
        destination = None
        committed = False
        with lock:
            try:
                with sessions.begin() as db:
                    existing = db.scalar(select(Record).where(Record.upload_id == upload_id))
                    if existing:
                        return record_dict(existing)
                    upload = db.get(Upload, upload_id)
                    if not upload or upload.expires_at < utcnow():
                        raise HTTPException(404, "临时图片已过期，请重新上传")
                    if db.scalar(
                        select(Job.id)
                        .where(Job.upload_id == upload_id, Job.status.in_(["queued", "running"]))
                        .limit(1)
                    ):
                        raise HTTPException(409, "请等待识别结束后再保存")
                    latest = db.scalar(
                        select(Job)
                        .where(Job.upload_id == upload_id)
                        .order_by(Job.created_at.desc())
                        .limit(1)
                    )
                    successful = db.scalar(
                        select(Job)
                        .where(Job.upload_id == upload_id, Job.status == "succeeded")
                        .order_by(Job.created_at.desc())
                        .limit(1)
                    )
                    result = successful.result if successful else None
                    record_id = str(uuid4())
                    destination = settings.data_dir / "photos" / record_id
                    shutil.copytree(settings.data_dir / "temp" / upload_id, destination)
                    record = Record(
                        id=record_id,
                        upload_id=upload_id,
                        original_name=upload.original_name,
                        original_ext=upload.original_ext,
                        width=upload.width,
                        height=upload.height,
                        uploaded_at=upload.uploaded_at,
                        captured_at=body.captured_at.isoformat(),
                        timezone=body.timezone,
                        head_count=0,
                        detection_status=latest.status if latest else "not_run",
                        model_version=result["model_version"] if result else None,
                        detection_config=result["config"] if result else None,
                        initial_detections=result["marks"] if result else [],
                    )
                    db.add(record)
                    set_marks(db, record, body.marks)
                    upload.saved_record_id = record_id
                    db.flush()
                    response = record_dict(record)
                committed = True
            finally:
                if not committed and destination is not None:
                    remove_directory(destination)
            try:
                remove_directory(settings.data_dir / "temp" / upload_id)
            except OSError:
                logger.warning("Saved temporary files will be removed by cleanup: %s", upload_id)
        return response

    @app.get("/api/records")
    def list_records(page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=100)):
        with sessions() as db:
            total = db.scalar(select(func.count()).select_from(Record))
            records = db.scalars(
                select(Record)
                .order_by(Record.captured_at.desc(), Record.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            return {
                "items": [record_dict(record, False) for record in records],
                "total": total,
                "page": page,
                "page_size": page_size,
            }

    @app.get("/api/records/{record_id}")
    def get_record(record_id: UUID):
        with sessions() as db:
            record = db.get(Record, str(record_id))
            if not record:
                raise HTTPException(404, "历史记录不存在")
            return record_dict(record)

    @app.put("/api/records/{record_id}")
    def update_record(record_id: UUID, body: UpdateRecord):
        with lock, sessions.begin() as db:
            record = db.get(Record, str(record_id))
            if not record:
                raise HTTPException(404, "历史记录不存在")
            if record.version != body.version:
                raise HTTPException(409, "记录已被其他页面修改，请重新打开后再编辑")
            set_marks(db, record, body.marks)
            record.captured_at = body.captured_at.isoformat()
            record.timezone = body.timezone
            record.updated_at = utcnow()
            record.version += 1
            db.flush()
            return record_dict(record)

    @app.delete("/api/records/{record_id}", status_code=204)
    def delete_record(record_id: UUID):
        with lock:
            with sessions.begin() as db:
                record = db.get(Record, str(record_id))
                if not record:
                    raise HTTPException(404, "历史记录不存在")
                upload = db.get(Upload, record.upload_id)
                if upload:
                    db.delete(upload)
                db.delete(record)
            # DB deletion first: if removal fails, cleanup removes the orphan later.
            try:
                remove_directory(settings.data_dir / "photos" / str(record_id))
            except OSError:
                logger.warning("Deleted photo awaiting orphan cleanup: %s", record_id)

    @app.get("/api/media/{kind}/{item_id}/{variant}")
    def media(kind: str, item_id: UUID, variant: str):
        if kind not in ("uploads", "records") or variant not in (
            "original",
            "display",
            "thumbnail",
        ):
            raise HTTPException(404, "图片不存在")
        with lock, sessions() as db:
            item = db.get(Upload if kind == "uploads" else Record, str(item_id))
            if not item:
                raise HTTPException(404, "图片不存在")
            if kind == "uploads":
                if item.saved_record_id:
                    directory = settings.data_dir / "photos" / item.saved_record_id
                else:
                    directory = settings.data_dir / "temp" / str(item_id)
            else:
                directory = settings.data_dir / "photos" / str(item_id)
            filename = f"original{item.original_ext}" if variant == "original" else f"{variant}.jpg"
            path = directory / filename
            if not path.is_file():
                raise HTTPException(404, "图片文件不存在")
            return FileResponse(
                path,
                filename=item.original_name if variant == "original" else None,
                content_disposition_type="inline",
            )

    if settings.frontend_dir.is_dir():
        app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
    else:

        @app.get("/")
        def index():
            return {
                "message": "后端已启动。开发时打开 http://127.0.0.1:5173；正式使用请先构建 frontend。"
            }

    return app
