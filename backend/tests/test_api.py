import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from conftest import photo, upload
from fastapi.testclient import TestClient

from app.db import Job, Upload
from app.main import create_app


def mark(**values):
    return {"id": str(uuid4()), "x": 0.5, "y": 0.4, "source": "manual", **values}


def payload(upload_id, marks=None):
    return {
        "upload_id": upload_id,
        "captured_at": "2024-03-12T09:35:48+08:00",
        "timezone": "Asia/Shanghai",
        "marks": marks or [],
    }


def test_missing_model_is_explicit_and_manual_save_works(client):
    assert client.get("/api/health").json()["model"]["ready"] is False
    image = upload(client)
    assert client.post("/api/detection-jobs", json={"upload_id": image["id"]}).status_code == 503
    body = payload(image["id"], [mark(), mark(x=0.8)])
    saved = client.post("/api/records", json=body)
    assert saved.status_code == 201, saved.text
    result = saved.json()
    assert result["head_count"] == 2
    assert result["captured_at"] == "2024-03-12T01:35:00+00:00"
    assert result["uploaded_at"] == image["uploaded_at"]
    assert result["detection_status"] == "not_run"
    assert client.get(result["original_url"]).content == photo()
    assert client.get(result["image_url"]).status_code == 200
    # Exactly the same upload saved twice is idempotent.
    assert client.post("/api/records", json=body).json()["id"] == result["id"]
    assert client.get("/api/records").json()["total"] == 1
    assert client.get(image["image_url"]).status_code == 200


def test_edit_version_delete_and_reopen(client):
    image = upload(client)
    body = payload(image["id"], [mark()])
    record = client.post("/api/records", json=body).json()
    update = {key: value for key, value in body.items() if key != "upload_id"}
    update.update(version=record["version"], marks=[], captured_at="2020-05-08T21:12:00+08:00")
    response = client.put(f"/api/records/{record['id']}", json=update)
    assert response.status_code == 200, response.text
    assert response.json()["head_count"] == 0
    assert response.json()["version"] == 2
    assert client.put(f"/api/records/{record['id']}", json=update).status_code == 409
    detail = client.get(f"/api/records/{record['id']}").json()
    assert detail["captured_at"] == "2020-05-08T13:12:00+00:00"
    assert client.delete(f"/api/records/{record['id']}").status_code == 204
    assert client.get(detail["image_url"]).status_code == 404
    assert client.get("/api/records").json()["total"] == 0


def test_validation_and_security(client, settings):
    assert (
        client.post(
            "/api/uploads", files={"file": ("x.jpg", b"not a photo", "image/jpeg")}
        ).status_code
        == 422
    )
    assert not list((settings.data_dir / "temp").iterdir())
    image = upload(client)
    for bad in ([mark(x=-0.1)], [mark(y=2)], [mark(bbox=[0.8, 0.1, 0.2, 0.6])]):
        assert client.post("/api/records", json=payload(image["id"], bad)).status_code == 422
    duplicate = mark()
    assert (
        client.post("/api/records", json=payload(image["id"], [duplicate, duplicate])).status_code
        == 422
    )
    body = payload(image["id"])
    body["captured_at"] = "2024-01-01T10:00:00"
    assert client.post("/api/records", json=body).status_code == 422
    assert (
        client.post(
            "/api/uploads",
            headers={"Origin": "https://evil.example"},
            files={"file": ("x.jpg", photo())},
        ).status_code
        == 403
    )
    assert client.get("/api/health", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/api/media/uploads/not-a-uuid/display").status_code == 422
    assert client.get(f"/api/media/uploads/{image['id']}/other").status_code == 404


def test_orientation(client):
    image = upload(client, width=160, height=100, orientation=6)
    assert (image["width"], image["height"]) == (100, 160)
    import io

    from PIL import Image

    display = Image.open(io.BytesIO(client.get(image["image_url"]).content))
    assert display.size == (100, 160)
    assert not display.getexif()


def test_limits(client, settings):
    settings.max_upload_bytes = 100
    assert client.post("/api/uploads", files={"file": ("x.jpg", photo())}).status_code == 413
    settings.max_upload_bytes = 100000
    settings.max_pixels = 100
    assert client.post("/api/uploads", files={"file": ("x.jpg", photo())}).status_code == 422
    assert not list((settings.data_dir / "temp").iterdir())


def test_restart_and_cleanup(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        image = upload(client)
        record = client.post("/api/records", json=payload(image["id"], [mark()])).json()
        expired = upload(client)
        active = upload(client)
        with app.state.sessions.begin() as db:
            old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
            db.get(Upload, expired["id"]).expires_at = old
            db.get(Upload, active["id"]).expires_at = old
            db.add(Job(id=str(uuid4()), upload_id=active["id"], mode="standard", status="running"))
        app.state.cleanup()
        assert client.get(expired["image_url"]).status_code == 404
        assert client.get(active["image_url"]).status_code == 200
    app2 = create_app(settings)
    with TestClient(app2) as client:
        assert client.get(f"/api/records/{record['id']}").json()["head_count"] == 1
        assert client.get(record["image_url"]).status_code == 200
        assert client.get(active["image_url"]).status_code == 404


class TestOnlyDetector:
    def status(self):
        return {"ready": True, "name": "test-only", "provider": "test", "error": None}

    def detect(self, path, mode):
        assert path.is_file()
        return {
            "marks": [mark(source="auto", confidence=0.9)],
            "model_version": "test-only",
            "config": {"mode": mode},
            "elapsed_seconds": 0.1,
        }


def test_job_flow_and_provenance(settings):
    with TestClient(create_app(settings, TestOnlyDetector())) as client:
        image = upload(client)
        response = client.post(
            "/api/detection-jobs", json={"upload_id": image["id"], "mode": "fine"}
        )
        assert response.status_code == 202
        for _ in range(100):
            job = client.get(f"/api/detection-jobs/{response.json()['id']}").json()
            if job["status"] == "succeeded":
                break
            time.sleep(0.02)
        assert job["status"] == "succeeded"
        saved = client.post(
            "/api/records", json=payload(image["id"], job["result"]["marks"])
        ).json()
        assert saved["head_count"] == 1
        assert saved["initial_detections"] == job["result"]["marks"]
        assert saved["model_version"] == "test-only"
        assert saved["detection_config"]["mode"] == "fine"
