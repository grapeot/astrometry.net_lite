"""Unit tests for services/queue.py"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId

from domain.models import QueueMessage
from services import queue as queue_service


class TestEnqueueJob:
    """Tests for enqueue_job function."""

    async def test_creates_queue_message(self, mock_db: AsyncMock):
        """Test that queue message is created."""
        mock_collection = AsyncMock()
        inserted_id = ObjectId()
        mock_collection.insert_one.return_value = MagicMock(inserted_id=inserted_id)
        mock_db.__getitem__.return_value = mock_collection

        payload = {"submission_id": str(ObjectId()), "stored_path": "/data/test.jpg"}
        result = await queue_service.enqueue_job(mock_db, 12345, payload)

        assert isinstance(result, QueueMessage)
        assert result.job_id == 12345
        assert result.payload == payload
        mock_collection.insert_one.assert_called_once()


class TestLeaseJob:
    """Tests for lease_job function."""

    @patch("services.queue.settings")
    async def test_returns_message_when_available(
        self, mock_settings: MagicMock, mock_db: AsyncMock, sample_queue_message_doc: dict[str, Any]
    ):
        """Test that message is returned when available."""
        mock_settings.queue_visibility_timeout_seconds = 300
        mock_collection = AsyncMock()
        mock_collection.find_one_and_update.return_value = sample_queue_message_doc
        mock_db.__getitem__.return_value = mock_collection

        result = await queue_service.lease_job(mock_db)

        assert result is not None
        assert isinstance(result, QueueMessage)
        assert result.job_id == 12345
        mock_collection.find_one_and_update.assert_called_once()

    @patch("services.queue.settings")
    async def test_returns_none_when_queue_empty(
        self, mock_settings: MagicMock, mock_db: AsyncMock
    ):
        """Test that None is returned when queue is empty."""
        mock_settings.queue_visibility_timeout_seconds = 300
        mock_collection = AsyncMock()
        mock_collection.find_one_and_update.return_value = None
        mock_db.__getitem__.return_value = mock_collection

        result = await queue_service.lease_job(mock_db)

        assert result is None

    @patch("services.queue.settings")
    async def test_query_filters_completed_and_failed(
        self, mock_settings: MagicMock, mock_db: AsyncMock
    ):
        """Test that query filters out completed and failed messages."""
        mock_settings.queue_visibility_timeout_seconds = 300
        mock_collection = AsyncMock()
        mock_collection.find_one_and_update.return_value = None
        mock_db.__getitem__.return_value = mock_collection

        await queue_service.lease_job(mock_db)

        call_args = mock_collection.find_one_and_update.call_args
        query = call_args[0][0]
        assert query["completed_at"] is None
        assert query["failed_at"] is None

    @patch("services.queue.settings")
    async def test_increments_attempts(
        self, mock_settings: MagicMock, mock_db: AsyncMock
    ):
        """Test that attempts counter is incremented."""
        mock_settings.queue_visibility_timeout_seconds = 300
        mock_collection = AsyncMock()
        mock_collection.find_one_and_update.return_value = None
        mock_db.__getitem__.return_value = mock_collection

        await queue_service.lease_job(mock_db)

        call_args = mock_collection.find_one_and_update.call_args
        update = call_args[0][1]
        assert update["$inc"]["attempts"] == 1


class TestCompleteJob:
    """Tests for complete_job function."""

    async def test_sets_completed_at(self, mock_db: AsyncMock):
        """Test that completed_at is set."""
        mock_collection = AsyncMock()
        mock_db.__getitem__.return_value = mock_collection

        queue_id = ObjectId()
        await queue_service.complete_job(mock_db, queue_id)

        mock_collection.update_one.assert_called_once()
        call_args = mock_collection.update_one.call_args
        assert call_args[0][0] == {"_id": queue_id}
        assert "completed_at" in call_args[0][1]["$set"]


class TestFailJob:
    """Tests for fail_job function."""

    async def test_sets_failed_at_and_reason(self, mock_db: AsyncMock):
        """Test that failed_at and reason are set."""
        mock_collection = AsyncMock()
        mock_db.__getitem__.return_value = mock_collection

        queue_id = ObjectId()
        await queue_service.fail_job(mock_db, queue_id, "solve timeout")

        mock_collection.update_one.assert_called_once()
        call_args = mock_collection.update_one.call_args
        assert call_args[0][0] == {"_id": queue_id}
        update_doc = call_args[0][1]["$set"]
        assert "failed_at" in update_doc
        assert update_doc["failure_reason"] == "solve timeout"
