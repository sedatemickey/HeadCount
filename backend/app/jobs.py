import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from .db import Job

logger = logging.getLogger(__name__)


class JobManager:
    def __init__(self, sessions, detector, storage_path, lock: threading.RLock):
        self.sessions = sessions
        self.detector = detector
        self.storage_path = storage_path
        self.lock = lock
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="head-detection")

    def recover(self):
        with self.sessions.begin() as db:
            for job in db.scalars(select(Job).where(Job.status.in_(["queued", "running"]))):
                job.status = "interrupted"
                job.error = "服务重启，识别已中断，请重新识别。"

    def submit(self, job_id):
        self.executor.submit(self._run, job_id)

    def _run(self, job_id):
        with self.lock, self.sessions.begin() as db:
            job = db.get(Job, job_id)
            if not job:
                return
            job.status = "running"
            upload_id, mode = job.upload_id, job.mode
        try:
            result = self.detector.detect(
                self.storage_path / "temp" / upload_id / "display.jpg", mode
            )
            with self.lock, self.sessions.begin() as db:
                job = db.get(Job, job_id)
                if job:
                    job.status = "succeeded"
                    job.result = result
        except Exception:
            logger.exception("Detection job %s failed", job_id)
            with self.lock, self.sessions.begin() as db:
                job = db.get(Job, job_id)
                if job:
                    job.status = "failed"
                    job.error = "识别失败，请检查本地模型配置后重试；也可以继续手动标注。"

    def close(self):
        self.executor.shutdown(wait=True, cancel_futures=False)
