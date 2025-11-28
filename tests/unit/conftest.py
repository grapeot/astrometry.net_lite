"""Shared fixtures for unit tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId

from domain.models import Job, Submission, QueueMessage


@pytest.fixture
def mock_db() -> AsyncMock:
    """Create a mock MongoDB database."""
    db = AsyncMock()
    # Create mock collections
    db.__getitem__ = MagicMock(return_value=AsyncMock())
    return db


@pytest.fixture
def sample_job_doc() -> dict[str, Any]:
    """Sample job document from MongoDB."""
    return {
        "_id": ObjectId(),
        "job_id": 12345,
        "submission_id": ObjectId(),
        "status": "queued",
        "results": {
            "session": "test_api_key",
            "original_filename": "galaxy.jpg",
        },
        "artifacts": {},
        "tags": [],
        "machine_tags": [],
        "objects_in_field": [],
        "annotations": [],
        "created_at": datetime.now(UTC),
        "started_at": None,
        "finished_at": None,
    }


@pytest.fixture
def sample_job(sample_job_doc: dict[str, Any]) -> Job:
    """Sample Job model instance."""
    return Job(**sample_job_doc)


@pytest.fixture
def sample_submission_doc() -> dict[str, Any]:
    """Sample submission document from MongoDB."""
    return {
        "_id": ObjectId(),
        "api_key": "test_api_key",
        "original_filename": "galaxy.jpg",
        "stored_path": "/data/uploads/abc123_galaxy.jpg",
        "upload_args": {},
        "status": "queued",
        "jobs": [12345],
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "processing_started": None,
        "processing_finished": None,
    }


@pytest.fixture
def sample_submission(sample_submission_doc: dict[str, Any]) -> Submission:
    """Sample Submission model instance."""
    return Submission(**sample_submission_doc)


@pytest.fixture
def sample_queue_message_doc() -> dict[str, Any]:
    """Sample queue message document from MongoDB."""
    return {
        "_id": ObjectId(),
        "job_id": 12345,
        "payload": {
            "submission_id": str(ObjectId()),
            "stored_path": "/data/uploads/abc123_galaxy.jpg",
            "upload_args": {},
        },
        "locked_at": None,
        "completed_at": None,
        "failed_at": None,
        "attempts": 0,
        "failure_reason": None,
    }


@pytest.fixture
def sample_queue_message(sample_queue_message_doc: dict[str, Any]) -> QueueMessage:
    """Sample QueueMessage model instance."""
    return QueueMessage(**sample_queue_message_doc)


@pytest.fixture
def success_job_doc(sample_job_doc: dict[str, Any]) -> dict[str, Any]:
    """A job document that has completed successfully."""
    doc = sample_job_doc.copy()
    doc["status"] = "success"
    doc["finished_at"] = datetime.now(UTC)
    doc["results"]["calibration"] = {
        "ra": 180.0,
        "dec": 45.0,
        "radius": 1.5,
        "pixscale": 1.2,
        "orientation": 0.0,
        "parity": 1,
    }
    doc["tags"] = ["M31", "Andromeda Galaxy"]
    doc["machine_tags"] = ["messier m31", "ngc 224"]
    doc["objects_in_field"] = ["M31", "NGC 224"]
    doc["annotations"] = [
        {"type": "star", "names": ["HD 1234"], "pixelx": 100, "pixely": 200},
    ]
    doc["artifacts"] = {
        "wcs": "data/jobs/12345/wcs.fits",
        "new_fits": "data/jobs/12345/new.fits",
        "annotated": "data/jobs/12345/annotated.jpg",
    }
    return doc


@pytest.fixture
def success_job(success_job_doc: dict[str, Any]) -> Job:
    """A Job model instance that has completed successfully."""
    return Job(**success_job_doc)
