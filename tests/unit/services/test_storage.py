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

        storage.prepare_job_dir(12345)

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

        source_mock = MagicMock(spec=Path)
        source_mock.name = "test.jpg"

        storage.copy_to_job(12345, source_mock)

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

        storage.copy_to_job(12345, source_mock, target_name="renamed.jpg")

        # Verify the target name was used
        mock_job_dir.__truediv__.assert_called_with("renamed.jpg")


class TestSanitizeFilename:
    """Tests for sanitize_filename function."""

    def test_removes_query_parameters(self):
        """Test that query parameters are removed from filename."""
        result = storage.sanitize_filename("image.jpg?param=value&other=123")
        assert result == "image.jpg"

    def test_url_decodes_filename(self):
        """Test that URL-encoded filenames are decoded."""
        result = storage.sanitize_filename("file%20name.jpg")
        assert result == "file_name.jpg"

    def test_removes_special_characters(self):
        """Test that special characters are replaced with underscores."""
        result = storage.sanitize_filename("file name@test#123.jpg")
        assert result == "file_name_test_123.jpg"

    def test_removes_multiple_underscores(self):
        """Test that multiple consecutive underscores are collapsed."""
        result = storage.sanitize_filename("file___name.jpg")
        assert result == "file_name.jpg"

    def test_preserves_extension_when_truncating(self):
        """Test that file extension is preserved when truncating long filenames."""
        long_name = "a" * 250 + ".jpg"
        result = storage.sanitize_filename(long_name, max_length=200)
        assert result.endswith(".jpg")
        assert len(result) == 200

    def test_handles_very_long_extension(self):
        """Test handling of filenames with very long extensions."""
        long_ext = "file." + "x" * 250
        result = storage.sanitize_filename(long_ext, max_length=200)
        assert len(result) == 200

    def test_handles_empty_filename(self):
        """Test that empty filename is replaced with default."""
        result = storage.sanitize_filename("")
        assert result == "upload"

    def test_handles_dot_filename(self):
        """Test that '.' filename is replaced with default."""
        result = storage.sanitize_filename(".")
        assert result == "upload"

    def test_handles_dotdot_filename(self):
        """Test that '..' filename is replaced with default."""
        result = storage.sanitize_filename("..")
        assert result == "upload"

    def test_handles_complex_url_with_query_params(self):
        """Test handling of complex URL with query parameters."""
        filename = "R.a5ca20d0d229c783044bb7ad9ac830b9?rik=VGDB9cj0MZfbdg&riu=http%3a%2f%2fwww.astronomersdoitinthedark.com%2fimages%2fproduct%2fimages%2fM42-HH-200-450D-NoFilt-1600-2013-02-09--72x180--2048x.jpg&ehk=HxRyxMNEKHeh75XzkQj6531oNuzsWPnlgKul7ZTjkL8%3d&risl=&pid=ImgRaw&r=0"
        result = storage.sanitize_filename(filename)
        assert "?" not in result
        assert len(result) <= 200
        assert result.startswith("R.a5ca20d0d229c783044bb7ad9ac830b9")

    def test_preserves_valid_characters(self):
        """Test that valid characters (alphanumeric, dots, hyphens, underscores) are preserved."""
        result = storage.sanitize_filename("test-file_123.456.jpg")
        assert result == "test-file_123.456.jpg"

    def test_custom_max_length(self):
        """Test that custom max_length parameter works."""
        long_name = "a" * 300 + ".jpg"
        result = storage.sanitize_filename(long_name, max_length=100)
        assert len(result) == 100
        assert result.endswith(".jpg")


class TestSaveUploadFileWithSanitization:
    """Tests for save_upload_file function with filename sanitization."""

    @patch("services.storage.settings")
    @patch("services.storage.ensure_directories")
    @patch("builtins.open", new_callable=mock_open)
    def test_sanitizes_filename_before_saving(
        self,
        mock_file: MagicMock,
        mock_ensure: MagicMock,
        mock_settings: MagicMock,
    ):
        """Test that filename is sanitized before saving."""
        mock_settings.upload_cache_dir = Path("/data/uploads")

        result = storage.save_upload_file("test file@name.jpg?param=value", b"fake data")

        # Should save with sanitized filename
        assert "?" not in str(result)
        assert "@" not in str(result)
        mock_file.assert_called_once()
        # Verify the saved filename is sanitized
        call_args = mock_file.call_args[0]
        saved_path = call_args[0]
        assert "?" not in str(saved_path)
        assert "@" not in str(saved_path)
