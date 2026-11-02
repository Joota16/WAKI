from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "WAKI"
    data_dir: Path = Path("data")
    max_upload_mb: int = Field(default=8, ge=1, le=20)
    max_photos: int = Field(default=5, ge=1, le=10)
    max_image_pixels: int = Field(default=20_000_000, ge=1, le=40_000_000)
    normalized_max_side: int = Field(default=1920, ge=64, le=4096)
    senamhi_enabled: bool = True
    senamhi_poll_seconds: int = Field(default=3600, ge=300, le=86400)
    iot_key: SecretStr = SecretStr("")
    iot_retention_images: int = Field(default=100, ge=1, le=1000)
    camera_capture_seconds: int = Field(default=60, ge=5, le=86400)
    push_enabled: bool = True
    push_subject: str = 'https://waki.jellbru.lat'
    push_location_max_age_seconds: int = Field(default=86400, ge=300, le=86400)
    model_provider: Literal['none', 'waki'] = 'none'
    ai_water_checkpoint: Path = Path('weights/segformer_chillon_finetuned')
    ai_dino_checkpoint: Path | None = None
    ai_yoloe_checkpoint: Path | None = None
    ai_yoloe_prompts: Path | None = None
    ai_device: str = Field(default='cpu', pattern=r'^(cpu|cuda(:[0-9]+)?)$')
    ai_rivers: str = 'chillon'
    ai_retention_images: int = Field(default=100, ge=1, le=1000)
    ai_max_pending: int = Field(default=4, ge=1, le=32)
    jwt_secret: SecretStr = SecretStr('')
    jwt_expire_minutes: int = Field(default=60, ge=5, le=1440)
    auth_cookie_secure: bool = False
    admin_username: str = ''
    admin_password: SecretStr = SecretStr('')

    @field_validator('jwt_secret')
    @classmethod
    def valid_jwt_secret(cls, value):
        if value.get_secret_value() and len(value.get_secret_value()) < 32:
            raise ValueError('JWT_SECRET debe tener al menos 32 caracteres.')
        return value

    @field_validator('ai_dino_checkpoint', 'ai_yoloe_checkpoint', 'ai_yoloe_prompts', mode='before')
    @classmethod
    def optional_checkpoint(cls, value):
        return None if value in ('', None) else value

    @property
    def upload_limit(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def database_path(self) -> Path:
        return self.data_dir / "waki.sqlite3"

