from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Base(DeclarativeBase):
    pass


class Upload(Base):
    __tablename__ = "uploads"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    original_name: Mapped[str] = mapped_column(String(255))
    original_ext: Mapped[str] = mapped_column(String(10))
    width: Mapped[int]
    height: Mapped[int]
    uploaded_at: Mapped[str]
    expires_at: Mapped[str]
    saved_record_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    upload_id: Mapped[str] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    mode: Mapped[str] = mapped_column(String(20))
    error: Mapped[str | None] = mapped_column(nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[str] = mapped_column(default=utcnow)


class Record(Base):
    __tablename__ = "records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    upload_id: Mapped[str] = mapped_column(String(36), unique=True)
    original_name: Mapped[str] = mapped_column(String(255))
    original_ext: Mapped[str] = mapped_column(String(10))
    width: Mapped[int]
    height: Mapped[int]
    uploaded_at: Mapped[str]
    captured_at: Mapped[str] = mapped_column(index=True)
    timezone: Mapped[str] = mapped_column(String(100))
    head_count: Mapped[int]
    detection_status: Mapped[str]
    model_version: Mapped[str | None] = mapped_column(nullable=True)
    detection_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    initial_detections: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[str] = mapped_column(default=utcnow)
    updated_at: Mapped[str] = mapped_column(default=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)
    marks: Mapped[list["HeadMark"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class HeadMark(Base):
    __tablename__ = "head_marks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    record_id: Mapped[str] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"), index=True)
    x: Mapped[float]
    y: Mapped[float]
    bbox: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str]
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    is_modified: Mapped[bool] = mapped_column(default=False)


def make_engine(url: str):
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

    @event.listens_for(engine, "connect")
    def sqlite_settings(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")

    return engine, sessionmaker(engine, expire_on_commit=False)


def migrate(url: str) -> None:
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[1] / "migrations")
    )
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(config, "head")
