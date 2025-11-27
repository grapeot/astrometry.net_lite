"""Unit tests for domain/models.py"""

from __future__ import annotations

from datetime import datetime

import pytest
from bson import ObjectId

from domain.enums import ArtifactType, JobStatus, SubmissionStatus
from domain.models import Artifact, Job, QueueMessage, Submission


class TestJobModel:
    """Tests for Job model."""

    def test_job_creation_with_required_fields(self):
        """Test creating Job with minimum required fields."""
        job = Job(
            job_id=12345,
            submission_id=ObjectId(),
        )

        assert job.job_id == 12345
        assert job.status == JobStatus.queued
        assert job.results == {}
        assert job.artifacts == {}
        assert job.tags == []

    def test_job_creation_with_all_fields(self):
        """Test creating Job with all fields."""
        submission_id = ObjectId()
        job = Job(
            job_id=12345,
            submission_id=submission_id,
            status=JobStatus.success,
            failure_reason=None,
            results={"calibration": {"ra": 180.0}},
            artifacts={"wcs": "path/to/wcs.fits"},
            tags=["M31"],
            machine_tags=["messier m31"],
            objects_in_field=["M31"],
            annotations=[{"type": "star"}],
        )

        assert job.job_id == 12345
        assert job.submission_id == submission_id
        assert job.status == JobStatus.success
        assert job.results["calibration"]["ra"] == 180.0

    def test_job_status_enum_values(self):
        """Test that job status can be set to all enum values."""
        job = Job(job_id=1, submission_id=ObjectId())

        for status in JobStatus:
            job.status = status
            assert job.status == status

    def test_job_model_dump(self):
        """Test model serialization."""
        job = Job(
            job_id=12345,
            submission_id=ObjectId(),
            status=JobStatus.solving,
        )

        data = job.model_dump()
        assert data["job_id"] == 12345
        assert data["status"] == JobStatus.solving


class TestSubmissionModel:
    """Tests for Submission model."""

    def test_submission_creation_with_required_fields(self):
        """Test creating Submission with minimum required fields."""
        submission = Submission(
            api_key="test_key",
            original_filename="galaxy.jpg",
            stored_path="/data/uploads/galaxy.jpg",
        )

        assert submission.api_key == "test_key"
        assert submission.original_filename == "galaxy.jpg"
        assert submission.status == SubmissionStatus.queued
        assert submission.jobs == []

    def test_submission_creation_with_all_fields(self):
        """Test creating Submission with all fields."""
        now = datetime.utcnow()
        submission = Submission(
            api_key="test_key",
            original_filename="galaxy.jpg",
            stored_path="/data/uploads/galaxy.jpg",
            upload_args={"scale_type": "ul"},
            status=SubmissionStatus.success,
            jobs=[12345, 12346],
            created_at=now,
            updated_at=now,
            processing_started=now,
            processing_finished=now,
        )

        assert len(submission.jobs) == 2
        assert submission.status == SubmissionStatus.success
        assert submission.upload_args["scale_type"] == "ul"

    def test_submission_status_enum_values(self):
        """Test that submission status can be set to all enum values."""
        submission = Submission(
            api_key="key",
            original_filename="test.jpg",
            stored_path="/path",
        )

        for status in SubmissionStatus:
            submission.status = status
            assert submission.status == status


class TestArtifactModel:
    """Tests for Artifact model."""

    def test_artifact_creation(self):
        """Test creating Artifact."""
        artifact = Artifact(
            job_id=12345,
            artifact_type=ArtifactType.wcs,
            path="/data/jobs/12345/wcs.fits",
        )

        assert artifact.job_id == 12345
        assert artifact.artifact_type == ArtifactType.wcs
        assert artifact.path == "/data/jobs/12345/wcs.fits"

    def test_artifact_types(self):
        """Test all artifact types."""
        for artifact_type in ArtifactType:
            artifact = Artifact(
                job_id=1,
                artifact_type=artifact_type,
                path=f"/path/{artifact_type.value}",
            )
            assert artifact.artifact_type == artifact_type


class TestQueueMessageModel:
    """Tests for QueueMessage model."""

    def test_queue_message_creation(self):
        """Test creating QueueMessage."""
        msg = QueueMessage(
            job_id=12345,
            payload={"action": "solve"},
        )

        assert msg.job_id == 12345
        assert msg.payload == {"action": "solve"}
        assert msg.locked_at is None
        assert msg.completed_at is None
        assert msg.failed_at is None
        assert msg.attempts == 0

    def test_queue_message_is_locked_property(self):
        """Test is_locked property."""
        msg = QueueMessage(job_id=1, payload={})
        assert msg.is_locked is False

        msg.locked_at = datetime.utcnow()
        assert msg.is_locked is True

        msg.completed_at = datetime.utcnow()
        assert msg.is_locked is False

    def test_queue_message_with_failure(self):
        """Test QueueMessage with failure."""
        msg = QueueMessage(
            job_id=12345,
            payload={},
            attempts=3,
            failure_reason="solve timeout",
            failed_at=datetime.utcnow(),
        )

        assert msg.attempts == 3
        assert msg.failure_reason == "solve timeout"
        assert msg.failed_at is not None
