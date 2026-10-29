from pathlib import Path

from pydantic import Field, SecretStr
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

    @property
    def upload_limit(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def database_path(self) -> Path:
        return self.data_dir / "waki.sqlite3"

