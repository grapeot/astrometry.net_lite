"""
Job state management for file system based progress tracking.

This module provides StateManager class for tracking job processing stages
and real-time logs on the file system, complementing MongoDB as the
authoritative state source.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class ProcessingStage:
    """Processing stage constants for file system state."""
    STARTED = "started"
    SOLVING = "solving"
    CALIBRATING = "calibrating"
    ANNOTATING = "annotating"
    COMPLETED = "completed"
    FAILED = "failed"


class StateManager:
    """
    Manages job state on the file system.

    This is used to track fine-grained processing stages and real-time logs,
    while MongoDB remains the authoritative source for final job status.
    """

    def __init__(self, job_dir: Path):
        self.job_dir = job_dir
        self.status_file = job_dir / "status.json"
        self.log_file = job_dir / "solve-field.log"

    def get_status(self) -> Optional[dict[str, Any]]:
        """Read current status from file system."""
        if not self.status_file.exists():
            return None

        try:
            content = self.status_file.read_text()
            return json.loads(content)
        except (json.JSONDecodeError, IOError):
            return None

    def update_stage(
        self,
        stage: str,
        message: str = "",
        error: Optional[str] = None
    ) -> None:
        """
        Atomically update the processing stage.

        Args:
            stage: Current processing stage (from ProcessingStage constants)
            message: Human-readable status message
            error: Error message if stage is FAILED
        """
        # Ensure job directory exists
        self.job_dir.mkdir(parents=True, exist_ok=True)

        current = self.get_status() or {}

        # Track completed steps
        steps_completed = current.get("steps_completed", [])
        current_stage = current.get("stage")
        if current_stage and current_stage not in steps_completed:
            if current_stage not in [ProcessingStage.FAILED, ProcessingStage.COMPLETED]:
                steps_completed.append(current_stage)

        now = datetime.utcnow().isoformat() + "Z"
        new_status = {
            "job_id": current.get("job_id", self._extract_job_id()),
            "stage": stage,
            "message": message,
            "started_at": current.get("started_at", now),
            "updated_at": now,
            "steps_completed": steps_completed,
            "error": error,
        }

        self._atomic_write(self.status_file, json.dumps(new_status, indent=2))

    def append_log(self, content: str) -> None:
        """
        Append content to the log file.

        Args:
            content: Log content to append
        """
        # Ensure job directory exists
        self.job_dir.mkdir(parents=True, exist_ok=True)

        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(content)

    def get_log(self, offset: int = 0) -> tuple[str, int]:
        """
        Get log content starting from offset.

        Args:
            offset: Byte offset to start reading from

        Returns:
            Tuple of (log_content, new_offset)
        """
        if not self.log_file.exists():
            return "", 0

        with open(self.log_file, "r", encoding="utf-8") as f:
            f.seek(offset)
            content = f.read()
            new_offset = f.tell()

        return content, new_offset

    def get_full_log(self) -> str:
        """Get the complete log file content."""
        if not self.log_file.exists():
            return ""
        return self.log_file.read_text(encoding="utf-8")

    def clear_log(self) -> None:
        """Clear the log file (for job restart)."""
        if self.log_file.exists():
            self.log_file.unlink()

    def _atomic_write(self, file_path: Path, content: str) -> None:
        """
        Atomically write content to file using temp file + rename.

        This ensures that readers never see partial writes.
        """
        temp_file = file_path.with_suffix('.tmp')
        temp_file.write_text(content, encoding="utf-8")
        temp_file.rename(file_path)

    def _extract_job_id(self) -> int:
        """Extract job_id from job directory name."""
        try:
            return int(self.job_dir.name)
        except ValueError:
            return 0
