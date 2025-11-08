from __future__ import annotations

import shutil
from pathlib import Path
from typing import BinaryIO

from core.config import settings


def ensure_directories() -> None:
    settings.data_root.mkdir(parents=True, exist_ok=True)
    settings.job_output_dir.mkdir(parents=True, exist_ok=True)
    settings.upload_cache_dir.mkdir(parents=True, exist_ok=True)


def save_upload_file(filename: str, data: bytes) -> Path:
    ensure_directories()
    path = settings.upload_cache_dir / filename
    with open(path, "wb") as f:
        f.write(data)
    return path


def prepare_job_dir(job_id: int) -> Path:
    job_dir = settings.job_output_dir / str(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def copy_to_job(job_id: int, source: Path, target_name: str | None = None) -> Path:
    job_dir = prepare_job_dir(job_id)
    target = job_dir / (target_name or source.name)
    shutil.copy2(source, target)
    return target
