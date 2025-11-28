from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Centralised configuration loaded from environment/.env."""

    env: str = "development"

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_dbname: str = "astrometry_dev"
    mongodb_port: int = 27017

    data_root: Path = Path("./data")
    astrometry_index_dir: Path = Path("./astrometry_indexes")
    job_output_dir: Path = Path("./data/jobs")
    upload_cache_dir: Path = Path("./data/uploads")
    catalogs_dir: Path = Path("./catalogs")

    queue_visibility_timeout_seconds: int = 300
    enable_kmz: bool = False

    solve_field_bin: str = "/opt/homebrew/bin/solve-field"
    augment_xylist_bin: str = "/opt/homebrew/bin/augment-xylist"
    astrometry_engine_bin: str = "/opt/homebrew/bin/astrometry-engine"

    api_host: str = "127.0.0.1"
    api_port: int = 8002

    frontend_origin: Optional[str] = None
    frontend_port: int = 5173

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    def model_post_init(self, __context) -> None:
        """Update mongodb_uri with mongodb_port if port differs from URI."""
        import re
        # Only update if URI matches default pattern and port differs
        match = re.match(r"mongodb://([^:]+):(\d+)", self.mongodb_uri)
        if match:
            host = match.group(1)
            current_port = int(match.group(2))
            # Update if port was explicitly set via environment variable and differs
            if current_port != self.mongodb_port:
                self.mongodb_uri = f"mongodb://{host}:{self.mongodb_port}"


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()


settings = get_settings()
