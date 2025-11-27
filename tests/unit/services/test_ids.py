"""Unit tests for services/ids.py"""

from __future__ import annotations

from unittest.mock import AsyncMock


from services import ids


class TestGetNextSequence:
    """Tests for get_next_sequence function."""

    async def test_returns_incremented_sequence(self, mock_db: AsyncMock):
        """Test that sequence is incremented and returned."""
        mock_collection = AsyncMock()
        mock_collection.find_one_and_update.return_value = {"_id": "jobs", "seq": 42}
        mock_db.__getitem__.return_value = mock_collection

        result = await ids.get_next_sequence(mock_db, "jobs")

        assert result == 42
        mock_collection.find_one_and_update.assert_called_once()

    async def test_creates_counter_if_not_exists(self, mock_db: AsyncMock):
        """Test that counter is created with upsert."""
        mock_collection = AsyncMock()
        mock_collection.find_one_and_update.return_value = {"_id": "new_counter", "seq": 1}
        mock_db.__getitem__.return_value = mock_collection

        result = await ids.get_next_sequence(mock_db, "new_counter")

        call_args = mock_collection.find_one_and_update.call_args
        assert call_args[1]["upsert"] is True
        assert result == 1

    async def test_uses_correct_collection(self, mock_db: AsyncMock):
        """Test that counters collection is used."""
        mock_collection = AsyncMock()
        mock_collection.find_one_and_update.return_value = {"seq": 1}
        mock_db.__getitem__.return_value = mock_collection

        await ids.get_next_sequence(mock_db, "test")

        mock_db.__getitem__.assert_called_with("counters")
