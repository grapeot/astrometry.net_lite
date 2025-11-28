from __future__ import annotations

import re
import shutil
from pathlib import Path
from urllib.parse import urlparse, unquote

from core.config import settings

# Maximum filename length (conservative limit for cross-platform compatibility)
MAX_FILENAME_LENGTH = 200


def sanitize_filename(filename: str, max_length: int = MAX_FILENAME_LENGTH) -> str:
    """
    Sanitize filename by removing query parameters, URL decoding, and limiting length.
    
    Args:
        filename: Original filename (may contain URL query parameters)
        max_length: Maximum allowed filename length
        
    Returns:
        Sanitized filename safe for filesystem
    """
    # Remove query parameters if present (everything after ?)
    if '?' in filename:
        filename = filename.split('?')[0]
    
    # URL decode the filename
    filename = unquote(filename)
    
    # Remove any remaining special characters that might cause issues
    # Keep alphanumeric, dots, hyphens, underscores
    filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    
    # Remove multiple consecutive underscores
    filename = re.sub(r'_+', '_', filename)
    
    # Limit length while preserving extension
    if len(filename) > max_length:
        path_obj = Path(filename)
        stem = path_obj.stem
        suffix = path_obj.suffix
        
        # Reserve space for extension
        max_stem_length = max_length - len(suffix)
        if max_stem_length > 0:
            filename = stem[:max_stem_length] + suffix
        else:
            # If extension is too long, just truncate
            filename = filename[:max_length]
    
    # Ensure filename is not empty
    if not filename or filename == '.' or filename == '..':
        filename = "upload"
    
    return filename


def ensure_directories() -> None:
    settings.data_root.mkdir(parents=True, exist_ok=True)
    settings.job_output_dir.mkdir(parents=True, exist_ok=True)
    settings.upload_cache_dir.mkdir(parents=True, exist_ok=True)


def save_upload_file(filename: str, data: bytes) -> Path:
    ensure_directories()
    # Sanitize filename before saving
    safe_filename = sanitize_filename(filename)
    path = settings.upload_cache_dir / safe_filename
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
