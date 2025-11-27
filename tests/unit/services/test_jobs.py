"""Unit tests for services/jobs.py"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId

from domain.enums import ArtifactType, JobStatus
from domain.models import Job
from services import jobs as job_service


class TestGetJobByJobId:
    """Tests for get_job_by_job_id function."""

    async def test_returns_job_when_found(
        self, mock_db: AsyncMock, sample_job_doc: dict[str, Any]
    ):
        """Test that job is returned when found."""
        mock_collection = AsyncMock()
        mock_collection.find_one.return_value = sample_job_doc
        mock_db.__getitem__.return_value = mock_collection

        result = await job_service.get_job_by_job_id(mock_db, 12345)

        assert result is not None
        assert isinstance(result, Job)
        assert result.job_id == 12345
        mock_collection.find_one.assert_called_once_with({"job_id": 12345})

    async def test_returns_none_when_not_found(self, mock_db: AsyncMock):
        """Test that None is returned when job not found."""
        mock_collection = AsyncMock()
        mock_collection.find_one.return_value = None
        mock_db.__getitem__.return_value = mock_collection

        result = await job_service.get_job_by_job_id(mock_db, 99999)

        assert result is None


class TestUpdateJobStatus:
    """Tests for update_job_status function."""

    async def test_update_to_solving(self, mock_db: AsyncMock):
        """Test updating job status to solving."""
        mock_collection = AsyncMock()
        mock_db.__getitem__.return_value = mock_collection

        await job_service.update_job_status(mock_db, 12345, JobStatus.solving)

        mock_collection.update_one.assert_called_once()
        call_args = mock_collection.update_one.call_args
        assert call_args[0][0] == {"job_id": 12345}
        update_doc = call_args[0][1]
        assert update_doc["$set"]["status"] == "solving"

    async def test_update_to_success_sets_finished_at(self, mock_db: AsyncMock):
        """Test that updating to success sets finished_at."""
        mock_collection = AsyncMock()
        mock_db.__getitem__.return_value = mock_collection

        await job_service.update_job_status(mock_db, 12345, JobStatus.success)

        call_args = mock_collection.update_one.call_args
        update_doc = call_args[0][1]
        assert update_doc["$set"]["status"] == "success"
        assert "finished_at" in update_doc["$set"]

    async def test_update_with_failure_reason(self, mock_db: AsyncMock):
        """Test updating with failure reason."""
        mock_collection = AsyncMock()
        mock_db.__getitem__.return_value = mock_collection

        await job_service.update_job_status(
            mock_db, 12345, JobStatus.failure, failure_reason="solve timeout"
        )

        call_args = mock_collection.update_one.call_args
        update_doc = call_args[0][1]
        assert update_doc["$set"]["failure_reason"] == "solve timeout"

    async def test_update_with_results(self, mock_db: AsyncMock):
        """Test updating with results."""
        mock_collection = AsyncMock()
        mock_db.__getitem__.return_value = mock_collection

        results = {"calibration": {"ra": 180.0, "dec": 45.0}}
        await job_service.update_job_status(
            mock_db, 12345, JobStatus.success, results=results
        )

        call_args = mock_collection.update_one.call_args
        update_doc = call_args[0][1]
        assert "results.calibration" in update_doc["$set"]

    async def test_update_with_annotations(self, mock_db: AsyncMock):
        """Test updating with annotations."""
        mock_collection = AsyncMock()
        mock_db.__getitem__.return_value = mock_collection

        annotations = [{"type": "star", "names": ["Sirius"]}]
        await job_service.update_job_status(
            mock_db, 12345, JobStatus.success, annotations=annotations
        )

        call_args = mock_collection.update_one.call_args
        update_doc = call_args[0][1]
        assert update_doc["$set"]["annotations"] == annotations


class TestMarkJobStarted:
    """Tests for mark_job_started function."""

    async def test_sets_solving_status_and_started_at(self, mock_db: AsyncMock):
        """Test that mark_job_started sets correct fields."""
        mock_collection = AsyncMock()
        mock_db.__getitem__.return_value = mock_collection

        await job_service.mark_job_started(mock_db, 12345)

        call_args = mock_collection.update_one.call_args
        assert call_args[0][0] == {"job_id": 12345}
        update_doc = call_args[0][1]
        assert update_doc["$set"]["status"] == "solving"
        assert "started_at" in update_doc["$set"]


class TestAddArtifact:
    """Tests for add_artifact function."""

    async def test_adds_artifact_to_both_collections(self, mock_db: AsyncMock):
        """Test that artifact is added to both artifacts and jobs collections."""
        mock_artifacts = AsyncMock()
        mock_jobs = AsyncMock()

        def get_collection(name: str):
            if name == "artifacts":
                return mock_artifacts
            return mock_jobs

        mock_db.__getitem__.side_effect = get_collection

        await job_service.add_artifact(
            mock_db, 12345, ArtifactType.wcs, "/data/jobs/12345/wcs.fits"
        )

        # Check artifacts collection update
        mock_artifacts.update_one.assert_called_once()
        artifacts_call = mock_artifacts.update_one.call_args
        assert artifacts_call[0][0] == {"job_id": 12345, "artifact_type": "wcs"}
        assert artifacts_call[1]["upsert"] is True

        # Check jobs collection update
        mock_jobs.update_one.assert_called_once()
        jobs_call = mock_jobs.update_one.call_args
        assert jobs_call[0][0] == {"job_id": 12345}
        assert "artifacts.wcs" in jobs_call[0][1]["$set"]


class TestListJobsByIds:
    """Tests for list_jobs_by_ids function."""

    async def test_returns_jobs_for_given_ids(
        self, mock_db: AsyncMock, sample_job_doc: dict[str, Any]
    ):
        """Test listing jobs by IDs."""
        # Create async iterable cursor class
        class AsyncCursor:
            def __init__(self, docs):
                self.docs = docs
                self.index = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.docs):
                    raise StopAsyncIteration
                doc = self.docs[self.index]
                self.index += 1
                return doc

        doc1 = sample_job_doc.copy()
        doc1["job_id"] = 1
        doc2 = sample_job_doc.copy()
        doc2["job_id"] = 2

        mock_collection = MagicMock()
        mock_collection.find.return_value = AsyncCursor([doc1, doc2])
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        result = await job_service.list_jobs_by_ids(mock_db, [1, 2])

        assert len(result) == 2
        assert all(isinstance(j, Job) for j in result)
        mock_collection.find.assert_called_once_with({"job_id": {"$in": [1, 2]}})


class TestMyJobs:
    """Tests for my_jobs function."""

    async def test_returns_job_ids_for_api_key(self, mock_db: AsyncMock):
        """Test returning job IDs for an API key."""
        # Create async iterable cursor class
        class AsyncCursor:
            def __init__(self, docs):
                self.docs = docs
                self.index = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.docs):
                    raise StopAsyncIteration
                doc = self.docs[self.index]
                self.index += 1
                return doc

        mock_collection = MagicMock()
        mock_collection.find.return_value = AsyncCursor([
            {"job_id": 1}, {"job_id": 2}, {"job_id": 3}
        ])
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        result = await job_service.my_jobs(mock_db, "test_api_key")

        assert result == [1, 2, 3]
        mock_collection.find.assert_called_once_with(
            {"results.session": "test_api_key"}, {"job_id": 1}
        )
