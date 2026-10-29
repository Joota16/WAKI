from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "WAKI"
    data_dir: Path = Path("data")

    @property
    def database_path(self) -> Path:
        return self.data_dir / "waki.sqlite3"

