import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def bundled_model_path() -> Path:
    return ROOT / "models/head-detector.onnx"


def local_model_path() -> Path:
    return ROOT / "models/local/head-detector.onnx"


def resolve_model_path() -> Path:
    explicit = os.getenv("HEADCOUNT_MODEL_PATH")
    if explicit:
        return Path(explicit).expanduser()
    local = local_model_path()
    # An incomplete/broken override must report an error, not silently switch models.
    if local.exists() or local.with_suffix(".json").exists():
        return local
    return bundled_model_path()


@dataclass
class Settings:
    data_dir: Path = field(
        default_factory=lambda: Path(os.getenv("HEADCOUNT_DATA_DIR", ROOT / "data"))
    )
    model_path: Path = field(default_factory=resolve_model_path)
    frontend_dir: Path = field(default_factory=lambda: ROOT / "frontend/dist")
    timezone: str = field(default_factory=lambda: os.getenv("HEADCOUNT_TIMEZONE", "Asia/Shanghai"))
    provider: str = field(
        default_factory=lambda: os.getenv("HEADCOUNT_PROVIDER", "CPUExecutionProvider")
    )
    max_upload_bytes: int = 25 * 1024 * 1024
    max_pixels: int = 40_000_000
    temp_ttl_hours: int = 24
    max_pending_jobs: int = 4

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data_dir.resolve().as_posix()}/app.db"
