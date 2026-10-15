import threading
import time
from uuid import uuid4

from conftest import upload
from fastapi.testclient import TestClient
from test_api import TestOnlyDetector, mark, payload

from app.db import Job, Record, Upload
from app.main import create_app


def wait_job(client, job_id):
    for _ in range(100):
        job = client.get(f"/api/detection-jobs/{job_id}").json()
        if job["status"] not in ("running", "queued"):
            return job
        time.sleep(0.02)
    raise AssertionError("Job did not finish")


class BlockingDetector(TestOnlyDetector):
    def __init__(self):
        self.release = threading.Event()

    def detect(self, path, mode):
        self.release.wait(timeout=10)
        return super().detect(path, mode)


def test_running_job_blocks_save_and_duplicate_job_is_reused(settings):
    detector = BlockingDetector()
    with TestClient(create_app(settings, detector)) as client:
        image = upload(client)
        try:
            job = client.post("/api/detection-jobs", json={"upload_id": image["id"]}).json()
            duplicate = client.post("/api/detection-jobs", json={"upload_id": image["id"]}).json()
            assert duplicate["id"] == job["id"]
            assert client.post("/api/records", json=payload(image["id"])).status_code == 409
        finally:
            detector.release.set()
        assert wait_job(client, job["id"])["status"] == "succeeded"


class BrokenDetector(TestOnlyDetector):
    def detect(self, path, mode):
        raise RuntimeError("test-only model failure")


def test_failed_detection_allows_manual_result(settings):
    with TestClient(create_app(settings, BrokenDetector())) as client:
        image = upload(client)
        job = client.post("/api/detection-jobs", json={"upload_id": image["id"]}).json()
        assert wait_job(client, job["id"])["status"] == "failed"
        saved = client.post("/api/records", json=payload(image["id"], [mark()])).json()
        assert saved["head_count"] == 1
        assert saved["detection_status"] == "failed"


def test_interrupted_job_is_visible_after_restart(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        image = upload(client)
        job_id = str(uuid4())
        with app.state.sessions.begin() as db:
            db.add(Job(id=job_id, upload_id=image["id"], status="queued", mode="standard"))
    with TestClient(create_app(settings)) as client:
        assert client.get(f"/api/detection-jobs/{job_id}").json()["status"] == "interrupted"
        assert client.post("/api/records", json=payload(image["id"])).status_code == 201


def test_save_failure_keeps_temp_and_removes_partial_photo(app, client, settings, monkeypatch):
    image = upload(client)
    import shutil

    import app.main as main

    real_copytree = shutil.copytree

    def interrupted_copy(source, destination):
        real_copytree(source, destination)
        raise OSError("test-only disk error")

    monkeypatch.setattr(main.shutil, "copytree", interrupted_copy)
    with TestClient(app, raise_server_exceptions=False) as safe_client:
        response = safe_client.post("/api/records", json=payload(image["id"]))
        assert response.status_code == 500
    assert not list((settings.data_dir / "photos").iterdir())
    assert client.get(image["image_url"]).status_code == 200
    with app.state.sessions() as db:
        assert db.get(Upload, image["id"]).saved_record_id is None
        assert db.query(Record).count() == 0


def test_mark_ids_cannot_be_stolen_from_other_record(client):
    shared = mark()
    first = upload(client)
    saved = client.post("/api/records", json=payload(first["id"], [shared])).json()
    second = upload(client)
    assert client.post("/api/records", json=payload(second["id"], [shared])).status_code == 409
    assert client.get(f"/api/records/{saved['id']}").json()["head_count"] == 1
