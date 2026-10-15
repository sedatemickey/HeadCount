import hashlib
import json
from pathlib import Path

from app.detection import HeadDetector

MODEL = Path(__file__).resolve().parents[2] / "models/head-detector.onnx"


def test_bundled_artifact_is_real_model_with_portable_provenance():
    manifest = json.loads(MODEL.with_suffix(".json").read_text(encoding="utf-8"))
    assert MODEL.stat().st_size == manifest["size_bytes"] == 103625405
    assert MODEL.stat().st_size < 100 * 1024 * 1024
    with MODEL.open("rb") as file:
        assert not file.read(200).startswith(b"version https://git-lfs.github.com/spec/")
        file.seek(0)
        assert hashlib.file_digest(file, "sha256").hexdigest() == manifest["sha256"]
    assert manifest["source_url"].startswith("https://huggingface.co/")
    assert manifest["upstream_revision"] in manifest["source_url"]
    assert manifest["license_status"] == "conflicting-upstream-declarations"
    assert (MODEL.parent / "NOTICE.md").is_file()
    assert "license: mit" in (MODEL.parent / "UPSTREAM_MODEL_CARD.md").read_text(encoding="utf-8")
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in (MODEL.parent / "AGPL-3.0.txt").read_text(
        encoding="utf-8"
    )


def test_bundled_model_loads_on_cpu_without_network():
    status = HeadDetector(MODEL, "CPUExecutionProvider").status()
    assert status["ready"], status
    assert status["name"] == "yolo-head-medium"
    assert status["provider"] == "CPUExecutionProvider"
