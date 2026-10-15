import argparse
import hashlib
import shutil

import pytest
from test_detection import synthetic_model

from app import config, model_cli
from app.detection import HeadDetector


@pytest.fixture
def model_root(tmp_path, monkeypatch):
    root = tmp_path / "project"
    (root / "models").mkdir(parents=True)
    monkeypatch.setattr(config, "ROOT", root)
    monkeypatch.delenv("HEADCOUNT_MODEL_PATH", raising=False)
    source = synthetic_model(tmp_path)
    bundled = config.bundled_model_path()
    shutil.copy2(source, bundled)
    shutil.copy2(source.with_suffix(".json"), bundled.with_suffix(".json"))
    return root, source


def args_for(source, **overrides):
    args = dict(
        path=str(source),
        name="custom-test-only",
        source="test-only",
        license="test-only",
        input_size=640,
        accept_license=True,
        sha256=None,
        replace=False,
        destination=None,
    )
    args.update(overrides)
    return argparse.Namespace(**args)


def pair_bytes(path):
    return path.read_bytes(), path.with_suffix(".json").read_bytes()


def test_model_priority_and_settings_are_resolved_at_creation(model_root, monkeypatch):
    _, source = model_root
    assert config.Settings().model_path == config.bundled_model_path()
    assert model_cli.install(args_for(source)) == 0
    assert config.Settings().model_path == config.local_model_path()
    monkeypatch.setenv("HEADCOUNT_MODEL_PATH", str(source))
    assert config.Settings().model_path == source


def test_incomplete_local_override_does_not_silently_fallback(model_root):
    local = config.local_model_path()
    local.parent.mkdir()
    local.with_suffix(".json").write_text("{}")
    assert config.resolve_model_path() == local
    assert HeadDetector(config.Settings().model_path).status()["ready"] is False


def test_install_writes_local_and_leaves_bundled_untouched(model_root):
    _, source = model_root
    original = pair_bytes(config.bundled_model_path())
    assert model_cli.install(args_for(source)) == 0
    assert pair_bytes(config.bundled_model_path()) == original
    assert HeadDetector(config.local_model_path()).status()["ready"]
    assert model_cli.install(args_for(source)) == 2


def test_incompatible_replacement_preserves_local_and_bundled(model_root, tmp_path):
    _, source = model_root
    assert model_cli.install(args_for(source)) == 0
    previous = pair_bytes(config.local_model_path())
    bundled = pair_bytes(config.bundled_model_path())
    (tmp_path / "bad").mkdir()
    bad = synthetic_model(tmp_path / "bad", label="person")
    assert model_cli.install(args_for(bad, replace=True)) == 2
    assert pair_bytes(config.local_model_path()) == previous
    assert pair_bytes(config.bundled_model_path()) == bundled


def test_replacement_file_error_restores_previous_pair(model_root, monkeypatch):
    _, source = model_root
    assert model_cli.install(args_for(source)) == 0
    previous = pair_bytes(config.local_model_path())
    real_replace = model_cli.os.replace
    failed = False

    def fail_once(src, dst):
        nonlocal failed
        if dst == config.local_model_path().with_suffix(".json") and not failed:
            failed = True
            raise OSError("test-only sidecar replacement failure")
        return real_replace(src, dst)

    monkeypatch.setattr(model_cli.os, "replace", fail_once)
    with pytest.raises(OSError, match="test-only"):
        model_cli.install(args_for(source, name="replacement-test-only", replace=True))
    assert failed
    assert pair_bytes(config.local_model_path()) == previous


def test_restore_bundled_backs_up_override(model_root):
    root, source = model_root
    model_cli.install(args_for(source))
    previous = pair_bytes(config.local_model_path())
    assert model_cli.use_bundled() == 0
    assert config.resolve_model_path() == config.bundled_model_path()
    backups = list((root / "backups/models").glob("local-*"))
    assert len(backups) == 1
    assert pair_bytes(backups[0] / "head-detector.onnx") == previous
    assert model_cli.use_bundled() == 0


def test_restore_refuses_explicit_environment_override(model_root, monkeypatch):
    _, source = model_root
    model_cli.install(args_for(source))
    monkeypatch.setenv("HEADCOUNT_MODEL_PATH", str(source))
    assert model_cli.use_bundled() == 2
    assert config.local_model_path().is_file()


def test_installer_refuses_bundled_destination(model_root, monkeypatch):
    _, source = model_root
    original = pair_bytes(config.bundled_model_path())
    assert (
        model_cli.install(args_for(source, destination=config.bundled_model_path(), replace=True))
        == 2
    )
    monkeypatch.setenv("HEADCOUNT_MODEL_PATH", str(config.bundled_model_path()))
    assert model_cli.install(args_for(source, replace=True)) == 2
    assert pair_bytes(config.bundled_model_path()) == original


def test_restore_will_not_remove_override_if_bundled_is_broken(model_root):
    _, source = model_root
    model_cli.install(args_for(source))
    config.bundled_model_path().write_bytes(b"broken")
    assert model_cli.use_bundled() == 2
    assert config.local_model_path().is_file()


def test_explicit_destination_is_supported_without_changing_selection(model_root, tmp_path):
    _, source = model_root
    target = tmp_path / "external" / "active.onnx"
    assert model_cli.install(args_for(source, destination=target)) == 0
    assert HeadDetector(target).status()["ready"]
    assert config.resolve_model_path() == config.bundled_model_path()
    assert (
        hashlib.sha256(target.read_bytes()).hexdigest()
        == hashlib.sha256(source.read_bytes()).hexdigest()
    )
