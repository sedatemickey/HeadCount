import argparse
import json

from PIL import Image
from test_detection import synthetic_model

from app.evaluate import evaluate, matched_count
from app.model_cli import install


def test_maximum_matching_does_not_cancel_missed_and_false_heads():
    assert matched_count([[0, 0, 0.2, 0.2]], [[0.7, 0.7, 0.9, 0.9]]) == 0
    assert matched_count([[0, 0, 0.2, 0.2]] * 2, [[0, 0, 0.2, 0.2]]) == 1


def test_offline_installer_is_explicit_and_validates_model(tmp_path, monkeypatch):
    source = synthetic_model(tmp_path)
    destination = tmp_path / "installed" / "head-detector.onnx"
    monkeypatch.setenv("HEADCOUNT_MODEL_PATH", str(destination))
    args = argparse.Namespace(
        accept_license=False,
        path=str(source),
        replace=False,
        sha256=None,
        name="test-only",
        source="test-only",
        license="test-only",
        input_size=640,
    )
    assert install(args) == 2
    assert not destination.exists()
    args.accept_license = True
    assert install(args) == 0
    assert destination.exists()
    assert destination.with_suffix(".json").exists()
    assert install(args) == 2


def test_evaluation_with_actual_runtime_test_graph(tmp_path):
    from app.detection import HeadDetector

    model = synthetic_model(tmp_path)
    Image.new("RGB", (640, 640)).save(tmp_path / "image.jpg")
    dataset = tmp_path / "dataset.json"
    dataset.write_text(
        json.dumps(
            {"images": [{"file": "image.jpg", "heads": [[0.421875, 0.421875, 0.578125, 0.578125]]}]}
        )
    )
    result = evaluate(dataset, HeadDetector(model))
    assert result["recall"] == 1.0
    assert result["precision"] == 1.0
    assert result["mean_absolute_count_error"] == 0.0
