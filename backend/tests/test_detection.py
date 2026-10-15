import hashlib
import json

import numpy as np
import onnx
import pytest
from onnx import TensorProto, helper, numpy_helper
from PIL import Image

from app.detection import HeadDetector, ModelUnavailable, nms, tile_origins


def synthetic_model(tmp_path, label="head"):
    # Test-only constant-output graph: verifies the real ONNX runtime/adapter, NOT model quality.
    raw = np.array(
        [[[320, 321, 100], [320, 321, 100], [100, 100, 20], [100, 100, 20], [0.9, 0.8, 0.1]]],
        dtype=np.float32,
    )
    graph = helper.make_graph(
        [helper.make_node("Constant", [], ["output"], value=numpy_helper.from_array(raw))],
        "test-only",
        [helper.make_tensor_value_info("images", TensorProto.FLOAT, [1, 3, 640, 640])],
        [helper.make_tensor_value_info("output", TensorProto.FLOAT, [1, 5, 3])],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 9
    helper.set_model_props(model, {"names": str({0: label})})
    path = tmp_path / "test.onnx"
    onnx.save(model, path)
    manifest = {
        "name": "test-only-not-real-detector",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_url": "test-only",
        "license": "test-only",
        "input_size": 640,
        "task": "head-detection",
        "output_format": "yolov8-raw-single-class",
    }
    path.with_suffix(".json").write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_real_onnx_adapter_letterbox_and_nms(tmp_path):
    detector = HeadDetector(synthetic_model(tmp_path))
    assert detector.status()["ready"]
    image = tmp_path / "image.jpg"
    Image.new("RGB", (1280, 640)).save(image)
    result = detector.detect(image)
    assert len(result["marks"]) == 1
    point = result["marks"][0]
    assert point["x"] == pytest.approx(0.5)
    assert point["y"] == pytest.approx(0.5)
    assert point["bbox"] == pytest.approx([0.421875, 0.34375, 0.578125, 0.65625])
    fine = detector.detect(image, "fine")
    assert fine["config"]["tiles"] == 3
    assert all(0 <= m["x"] <= 1 and 0 <= m["y"] <= 1 for m in fine["marks"])


def test_reject_person_and_corrupted_hash(tmp_path):
    detector = HeadDetector(synthetic_model(tmp_path, "person"))
    assert detector.status()["ready"] is False
    path = synthetic_model(tmp_path)
    path.write_bytes(path.read_bytes() + b"corrupted")
    with pytest.raises(ModelUnavailable, match="SHA256"):
        HeadDetector(path).detect(tmp_path / "irrelevant.jpg")


def test_tile_coverage_and_nearby_heads():
    assert tile_origins(100) == [0]
    assert tile_origins(2000)[-1] == 976
    boxes = np.array([[0, 0, 10, 10], [1, 1, 11, 11], [8, 0, 18, 10]], dtype=float)
    assert nms(boxes, np.array([0.9, 0.8, 0.7])) == [0, 2]
    assert nms(np.empty((0, 4)), np.empty(0)) == []
