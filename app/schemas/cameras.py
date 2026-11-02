from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, field_validator

from app.schemas.hydrology import RiverId

CameraId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$", max_length=64)]


class CameraDefinition(BaseModel):
    id: CameraId
    name: str
    river_id: RiverId


class CameraUpload(BaseModel):
    camera_id: CameraId
    captured_at: AwareDatetime | None = None

    @field_validator("captured_at")
    @classmethod
    def validate_capture_time(cls, value):
        if value is not None:
            if value > datetime.now(timezone.utc) + timedelta(minutes=5):
                raise ValueError("La fecha de captura no puede estar en el futuro. Sin reloj sincronizado, omite X-Captured-At.")
            return value.astimezone(timezone.utc)
        return value


class CameraFrame(BaseModel):
    id: UUID
    camera_id: CameraId
    received_at: AwareDatetime
    captured_at: AwareDatetime | None
    width: int
    height: int
    size_bytes: int
    image_url: str


class LatestCameraFrame(BaseModel):
    camera: CameraDefinition
    latest: CameraFrame | None = None
    server_time: AwareDatetime
    poll_seconds: int = 5
    stale_after_seconds: int = 120
    capture_interval_seconds: int = 60
