"""Unit tests for services/submissions.py"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from bson import ObjectId

from domain.enums import SubmissionStatus
from domain.models import Submission
from services import submissions as submission_service


class TestValidateApiKey:
    """Tests for validate_api_key function."""

    async def test_returns_true_for_valid_key(self, mock_db: AsyncMock):
        """Test that valid API key returns True."""
        mock_collection = AsyncMock()
        mock_collection.find_one.return_value = {"apikey": "valid_key"}
        mock_db.__getitem__.return_value = mock_collection

        result = await submission_service.validate_api_key(mock_db, "valid_key")

        assert result is True
        mock_collection.find_one.assert_called_once_with({"apikey": "valid_key", "enabled": {"$ne": False}})

    async def test_returns_false_for_invalid_key(self, mock_db: AsyncMock):
        """Test that invalid API key returns False."""
        mock_collection = AsyncMock()
        mock_collection.find_one.return_value = None
        mock_db.__getitem__.return_value = mock_collection

        result = await submission_service.validate_api_key(mock_db, "invalid_key")

        assert result is False


class TestCreateSubmission:
    """Tests for create_submission function."""

    @patch("services.submissions.save_upload_file")
    @patch("services.submissions.get_next_sequence")
    @patch("services.submissions.queue_service.enqueue_job")
    async def test_creates_submission_and_job(
        self,
        mock_enqueue: AsyncMock,
        mock_get_seq: AsyncMock,
        mock_save: MagicMock,
        mock_db: AsyncMock,
    ):
        """Test that submission and job are created."""
        # Setup mocks
        mock_save.return_value = "/data/uploads/abc123_test.jpg"
        mock_get_seq.return_value = 12345

        submission_id = ObjectId()
        mock_submissions = AsyncMock()
        mock_submissions.insert_one.return_value = MagicMock(inserted_id=submission_id)
        mock_submissions.update_one.return_value = None

        mock_jobs = AsyncMock()
        mock_jobs.insert_one.return_value = MagicMock(inserted_id=ObjectId())

        mock_queue_msg = MagicMock()
        mock_queue_msg.id = ObjectId()
        mock_enqueue.return_value = mock_queue_msg

        def get_collection(name: str):
            if name == "submissions":
                return mock_submissions
            if name == "jobs":
                return mock_jobs
            return AsyncMock()

        mock_db.__getitem__.side_effect = get_collection

        # Execute
        result = await submission_service.create_submission(
            mock_db,
            api_key="test_key",
            filename="test.jpg",
            data=b"fake image data",
            upload_args={"scale_type": "ul"},
        )

        # Verify
        assert result["status"] == "success"
        assert result["subid"] == str(submission_id)
        assert result["job_id"] == 12345
        mock_save.assert_called_once()
        mock_submissions.insert_one.assert_called_once()
        mock_jobs.insert_one.assert_called_once()
        mock_enqueue.assert_called_once()


class TestMarkSubmissionStarted:
    """Tests for mark_submission_started function."""

    async def test_updates_processing_started(self, mock_db: AsyncMock):
        """Test that processing_started is set."""
        mock_collection = AsyncMock()
        mock_db.__getitem__.return_value = mock_collection

        await submission_service.mark_submission_started(mock_db, str(ObjectId()))

        mock_collection.update_one.assert_called_once()
        call_args = mock_collection.update_one.call_args
        update_doc = call_args[0][1]["$set"]
        assert "processing_started" in update_doc
        assert update_doc["status"] == "processing"


class TestMarkSubmissionFinished:
    """Tests for mark_submission_finished function."""

    async def test_updates_processing_finished_success(self, mock_db: AsyncMock):
        """Test marking submission as finished with success."""
        mock_collection = AsyncMock()
        mock_db.__getitem__.return_value = mock_collection

        await submission_service.mark_submission_finished(
            mock_db, str(ObjectId()), SubmissionStatus.success
        )

        call_args = mock_collection.update_one.call_args
        update_doc = call_args[0][1]["$set"]
        assert "processing_finished" in update_doc
        assert update_doc["status"] == "success"

    async def test_updates_processing_finished_failure(self, mock_db: AsyncMock):
        """Test marking submission as finished with failure."""
        mock_collection = AsyncMock()
        mock_db.__getitem__.return_value = mock_collection

        await submission_service.mark_submission_finished(
            mock_db, str(ObjectId()), SubmissionStatus.failure
        )

        call_args = mock_collection.update_one.call_args
        update_doc = call_args[0][1]["$set"]
        assert update_doc["status"] == "failure"


class TestGetSubmission:
    """Tests for get_submission function."""

    async def test_returns_submission_when_found(
        self, mock_db: AsyncMock, sample_submission_doc: dict[str, Any]
    ):
        """Test returning submission when found."""
        mock_collection = AsyncMock()
        mock_collection.find_one.return_value = sample_submission_doc
        mock_db.__getitem__.return_value = mock_collection

        sub_id = str(sample_submission_doc["_id"])
        result = await submission_service.get_submission(mock_db, sub_id)

        assert result is not None
        assert isinstance(result, Submission)
        assert result.api_key == "test_api_key"

    async def test_returns_none_when_not_found(self, mock_db: AsyncMock):
        """Test returning None when submission not found."""
        mock_collection = AsyncMock()
        mock_collection.find_one.return_value = None
        mock_db.__getitem__.return_value = mock_collection

        result = await submission_service.get_submission(mock_db, str(ObjectId()))

        assert result is None


class TestListSubmissionJobs:
    """Tests for list_submission_jobs function."""

    async def test_returns_job_ids(self, mock_db: AsyncMock):
        """Test returning job IDs for a submission."""
        mock_collection = AsyncMock()
        mock_collection.find_one.return_value = {"jobs": [12345, 12346, 12347]}
        mock_db.__getitem__.return_value = mock_collection

        result = await submission_service.list_submission_jobs(mock_db, str(ObjectId()))

        assert result == [12345, 12346, 12347]

    async def test_returns_empty_list_when_not_found(self, mock_db: AsyncMock):
        """Test returning empty list when submission not found."""
        mock_collection = AsyncMock()
        mock_collection.find_one.return_value = None
        mock_db.__getitem__.return_value = mock_collection

        result = await submission_service.list_submission_jobs(mock_db, str(ObjectId()))

        assert result == []

    async def test_returns_empty_list_when_no_jobs(self, mock_db: AsyncMock):
        """Test returning empty list when no jobs field."""
        mock_collection = AsyncMock()
        mock_collection.find_one.return_value = {}
        mock_db.__getitem__.return_value = mock_collection

        result = await submission_service.list_submission_jobs(mock_db, str(ObjectId()))

        assert result == []
