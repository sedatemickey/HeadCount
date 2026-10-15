from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Unit = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class Mark(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    x: Unit
    y: Unit
    bbox: tuple[Unit, Unit, Unit, Unit] | None = None
    source: Literal["auto", "manual"]
    confidence: Unit | None = None
    is_modified: bool = False

    @model_validator(mode="after")
    def check_bbox(self):
        if self.bbox and (self.bbox[0] >= self.bbox[2] or self.bbox[1] >= self.bbox[3]):
            raise ValueError("检测框必须有正面积")
        if self.source == "manual" and self.confidence is not None:
            raise ValueError("手动标记没有模型置信度")
        return self


class SaveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    captured_at: datetime
    timezone: str
    marks: list[Mark] = Field(max_length=2000)

    @field_validator("captured_at")
    @classmethod
    def aware_minute(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("拍照时间必须包含时区")
        return value.astimezone(timezone.utc).replace(second=0, microsecond=0)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("未知时区") from None
        return value

    @field_validator("marks")
    @classmethod
    def unique_ids(cls, marks):
        if len({m.id for m in marks}) != len(marks):
            raise ValueError("标记 ID 重复")
        return marks


class CreateRecord(SaveBody):
    upload_id: UUID


class UpdateRecord(SaveBody):
    version: int = Field(ge=1)


class CreateJob(BaseModel):
    model_config = ConfigDict(extra="forbid")
    upload_id: UUID
    mode: Literal["standard", "fine"] = "standard"
