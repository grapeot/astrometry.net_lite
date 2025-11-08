from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Centralised configuration loaded from environment/.env."""

    env: str = "development"

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_dbname: str = "astrometry_dev"

    data_root: Path = Path("./data")
    astrometry_index_dir: Path = Path("./astrometry_indexes")
    job_output_dir: Path = Path("./data/jobs")
    upload_cache_dir: Path = Path("./data/uploads")

    queue_visibility_timeout_seconds: int = 300

    solve_field_bin: str = "/opt/homebrew/bin/solve-field"
    augment_xylist_bin: str = "/opt/homebrew/bin/augment-xylist"
    astrometry_engine_bin: str = "/opt/homebrew/bin/astrometry-engine"

    api_host: str = "127.0.0.1"
    api_port: int = 8000

    frontend_origin: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()


settings = get_settings()
