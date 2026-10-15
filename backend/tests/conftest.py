import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(
        data_dir=tmp_path / "data",
        model_path=tmp_path / "missing.onnx",
        frontend_dir=tmp_path / "no-frontend",
    )


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


def photo(width=160, height=100, orientation=None):
    data = io.BytesIO()
    image = Image.new("RGB", (width, height), (200, 180, 160))
    exif = Image.Exif()
    if orientation:
        exif[274] = orientation
    image.save(data, "JPEG", exif=exif)
    return data.getvalue()


def upload(client, **kwargs):
    response = client.post(
        "/api/uploads", files={"file": ("合照.jpg", photo(**kwargs), "image/jpeg")}
    )
    assert response.status_code == 201, response.text
    return response.json()
