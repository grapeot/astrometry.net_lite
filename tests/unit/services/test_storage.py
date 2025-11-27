"""Unit tests for services/storage.py"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

from services import storage


class TestEnsureDirectories:
    """Tests for ensure_directories function."""

    @patch("services.storage.settings")
    def test_creates_required_directories(self, mock_settings: MagicMock):
        """Test that all required directories are created."""
        mock_data_root = MagicMock(spec=Path)
        mock_job_output = MagicMock(spec=Path)
        mock_upload_cache = MagicMock(spec=Path)

        mock_settings.data_root = mock_data_root
        mock_settings.job_output_dir = mock_job_output
        mock_settings.upload_cache_dir = mock_upload_cache

        storage.ensure_directories()

        mock_data_root.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        mock_job_output.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        mock_upload_cache.mkdir.assert_called_once_with(parents=True, exist_ok=True)


class TestSaveUploadFile:
    """Tests for save_upload_file function."""

    @patch("services.storage.settings")
    @patch("services.storage.ensure_directories")
    @patch("builtins.open", new_callable=mock_open)
    def test_saves_file_to_upload_cache(
        self,
        mock_file: MagicMock,
        mock_ensure: MagicMock,
        mock_settings: MagicMock,
    ):
        """Test that file is saved to upload cache directory."""
        mock_settings.upload_cache_dir = Path("/data/uploads")

        result = storage.save_upload_file("test.jpg", b"fake data")

        assert result == Path("/data/uploads/test.jpg")
        mock_ensure.assert_called_once()
        mock_file.assert_called_once_with(Path("/data/uploads/test.jpg"), "wb")
        mock_file().write.assert_called_once_with(b"fake data")


class TestPrepareJobDir:
    """Tests for prepare_job_dir function."""

    @patch("services.storage.settings")
    def test_creates_job_directory(self, mock_settings: MagicMock):
        """Test that job directory is created."""
        mock_job_dir = MagicMock(spec=Path)
        mock_settings.job_output_dir = MagicMock()
        mock_settings.job_output_dir.__truediv__ = MagicMock(return_value=mock_job_dir)

        result = storage.prepare_job_dir(12345)

        mock_job_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)


class TestCopyToJob:
    """Tests for copy_to_job function."""

    @patch("services.storage.prepare_job_dir")
    @patch("shutil.copy2")
    def test_copies_file_to_job_directory(
        self, mock_copy: MagicMock, mock_prepare: MagicMock
    ):
        """Test that file is copied to job directory."""
        mock_job_dir = MagicMock(spec=Path)
        mock_job_dir.__truediv__ = MagicMock(return_value=Path("/data/jobs/12345/test.jpg"))
        mock_prepare.return_value = mock_job_dir

        source = Path("/tmp/test.jpg")
        source_mock = MagicMock(spec=Path)
        source_mock.name = "test.jpg"

        result = storage.copy_to_job(12345, source_mock)

        mock_prepare.assert_called_once_with(12345)
        mock_copy.assert_called_once()

    @patch("services.storage.prepare_job_dir")
    @patch("shutil.copy2")
    def test_uses_custom_target_name(
        self, mock_copy: MagicMock, mock_prepare: MagicMock
    ):
        """Test that custom target name is used when provided."""
        mock_job_dir = MagicMock(spec=Path)
        mock_job_dir.__truediv__ = MagicMock(return_value=Path("/data/jobs/12345/renamed.jpg"))
        mock_prepare.return_value = mock_job_dir

        source_mock = MagicMock(spec=Path)
        source_mock.name = "original.jpg"

        result = storage.copy_to_job(12345, source_mock, target_name="renamed.jpg")

        # Verify the target name was used
        mock_job_dir.__truediv__.assert_called_with("renamed.jpg")
