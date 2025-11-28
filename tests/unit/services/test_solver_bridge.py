"""Unit tests for services/solver_bridge.py"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from services import solver_bridge


class TestCheckToolsAvailable:
    """Tests for check_tools_available function."""

    @patch("services.solver_bridge.settings")
    @patch("services.solver_bridge.shutil")
    def test_tools_available_when_both_exist(self, mock_shutil, mock_settings):
        """Test that check_tools_available returns True when both tools exist."""
        mock_settings.augment_xylist_bin = "/usr/bin/augment-xylist"
        mock_settings.astrometry_engine_bin = "/usr/bin/astrometry-engine"
        
        # Mock Path.exists to return True
        with patch("pathlib.Path.exists", return_value=True):
            is_available, error_msg = solver_bridge.check_tools_available()
            assert is_available is True
            assert error_msg == ""

    @patch("services.solver_bridge.settings")
    @patch("services.solver_bridge.shutil")
    def test_tools_available_with_path_fallback(self, mock_shutil, mock_settings):
        """Test that check_tools_available falls back to PATH lookup."""
        mock_settings.augment_xylist_bin = "/usr/bin/augment-xylist"
        mock_settings.astrometry_engine_bin = "/usr/bin/astrometry-engine"
        mock_shutil.which.side_effect = lambda x: f"/usr/bin/{x}" if x in ["augment-xylist", "astrometry-engine"] else None
        
        # Mock Path.exists to return False (not at configured path)
        with patch("pathlib.Path.exists", return_value=False):
            is_available, error_msg = solver_bridge.check_tools_available()
            assert is_available is True
            assert error_msg == ""

    @patch("services.solver_bridge.settings")
    @patch("services.solver_bridge.shutil")
    def test_tools_unavailable_when_missing(self, mock_shutil, mock_settings):
        """Test that check_tools_available returns False when tools are missing."""
        mock_settings.augment_xylist_bin = "/usr/bin/augment-xylist"
        mock_settings.astrometry_engine_bin = "/usr/bin/astrometry-engine"
        mock_settings.solve_field_bin = "/usr/bin/solve-field"
        mock_shutil.which.return_value = None
        
        # Mock Path.exists to return False
        with patch("pathlib.Path.exists", return_value=False):
            is_available, error_msg = solver_bridge.check_tools_available()
            assert is_available is False
            assert "augment-xylist" in error_msg or "solve-field" in error_msg


class TestGetToolPath:
    """Tests for _get_tool_path function."""

    @patch("services.solver_bridge.settings")
    @patch("services.solver_bridge.shutil")
    def test_returns_configured_path_when_exists(self, mock_shutil, mock_settings):
        """Test that configured path is returned when it exists."""
        mock_settings.solve_field_bin = "/usr/bin/solve-field"
        
        with patch("pathlib.Path.exists", return_value=True):
            result = solver_bridge._get_tool_path("/usr/bin/solve-field", "solve-field")
            assert result == "/usr/bin/solve-field"

    @patch("services.solver_bridge.settings")
    @patch("services.solver_bridge.shutil")
    def test_falls_back_to_path_lookup(self, mock_shutil, mock_settings):
        """Test that PATH lookup is used when configured path doesn't exist."""
        mock_shutil.which.return_value = "/usr/local/bin/solve-field"
        
        with patch("pathlib.Path.exists", return_value=False):
            result = solver_bridge._get_tool_path("/usr/bin/solve-field", "solve-field")
            assert result == "/usr/local/bin/solve-field"

    @patch("services.solver_bridge.settings")
    @patch("services.solver_bridge.shutil")
    def test_returns_configured_path_when_not_found(self, mock_shutil, mock_settings):
        """Test that configured path is returned even when not found (for error handling)."""
        mock_shutil.which.return_value = None
        
        with patch("pathlib.Path.exists", return_value=False):
            result = solver_bridge._get_tool_path("/usr/bin/solve-field", "solve-field")
            assert result == "/usr/bin/solve-field"


class TestBuildAugmentXylistArgs:
    """Tests for _build_augment_xylist_args function."""

    @patch("services.solver_bridge.settings")
    @patch("services.solver_bridge.shutil")
    def test_includes_default_objs_and_downsample(self, mock_shutil, mock_settings):
        """Test that default --objs 1000 and --downsample 2 are included."""
        mock_settings.augment_xylist_bin = "/usr/bin/augment-xylist"
        mock_settings.solve_field_bin = "/usr/bin/solve-field"
        mock_settings.astrometry_index_dir = Path("/app/astrometry_indexes")
        # Mock which to return None for augment-xylist but solve-field exists
        def which_side_effect(cmd):
            if cmd == "augment-xylist":
                return None
            elif cmd == "solve-field":
                return "/usr/bin/solve-field"
            return None
        mock_shutil.which.side_effect = which_side_effect
        
        source_path = Path("/tmp/test.jpg")
        job_dir = Path("/tmp/job_1")
        upload_args = {}
        
        with patch("pathlib.Path.exists", return_value=False):
            args = solver_bridge._build_augment_xylist_args(source_path, job_dir, upload_args)
            
            # Should fall back to solve-field --just-augment
            assert "--objs" in args
            assert "1000" in args[args.index("--objs") + 1]
            assert "--downsample" in args
            assert "2" in args[args.index("--downsample") + 1]

    @patch("services.solver_bridge.settings")
    @patch("services.solver_bridge.shutil")
    def test_includes_index_dir(self, mock_shutil, mock_settings):
        """Test that --index-dir is included when using solve-field."""
        mock_settings.augment_xylist_bin = "/usr/bin/augment-xylist"
        mock_settings.solve_field_bin = "/usr/bin/solve-field"
        mock_settings.astrometry_index_dir = Path("/app/astrometry_indexes")
        # Mock which to return None for augment-xylist but solve-field exists
        def which_side_effect(cmd):
            if cmd == "augment-xylist":
                return None
            elif cmd == "solve-field":
                return "/usr/bin/solve-field"
            return None
        mock_shutil.which.side_effect = which_side_effect
        
        source_path = Path("/tmp/test.jpg")
        job_dir = Path("/tmp/job_1")
        upload_args = {}
        
        with patch("pathlib.Path.exists", return_value=False):
            args = solver_bridge._build_augment_xylist_args(source_path, job_dir, upload_args)
            
            # Should use solve-field --just-augment
            assert "--index-dir" in args
            idx = args.index("--index-dir")
            assert str(mock_settings.astrometry_index_dir.resolve()) in args[idx + 1]

    @patch("services.solver_bridge.settings")
    @patch("services.solver_bridge.shutil")
    def test_respects_upload_args_downsample(self, mock_shutil, mock_settings):
        """Test that upload_args downsample_factor overrides default."""
        mock_settings.augment_xylist_bin = "/usr/bin/augment-xylist"
        mock_settings.astrometry_index_dir = Path("/app/astrometry_indexes")
        mock_shutil.which.return_value = None
        
        source_path = Path("/tmp/test.jpg")
        job_dir = Path("/tmp/job_1")
        upload_args = {"downsample_factor": 4}
        
        with patch("pathlib.Path.exists", return_value=False):
            args = solver_bridge._build_augment_xylist_args(source_path, job_dir, upload_args)
            
            assert "--downsample" in args
            assert "4" in args[args.index("--downsample") + 1]


class TestBuildAstrometryEngineArgs:
    """Tests for _build_astrometry_engine_args function."""

    @patch("services.solver_bridge.settings")
    @patch("services.solver_bridge.shutil")
    def test_includes_index_dir(self, mock_shutil, mock_settings):
        """Test that -I (index directory) is included."""
        mock_settings.astrometry_engine_bin = "/usr/bin/astrometry-engine"
        mock_settings.astrometry_index_dir = Path("/app/astrometry_indexes")
        mock_shutil.which.return_value = None
        
        job_dir = Path("/tmp/job_1")
        job_id = 123
        
        with patch("pathlib.Path.exists", return_value=False):
            args = solver_bridge._build_astrometry_engine_args(job_dir, job_id)
            
            assert "-I" in args
            idx = args.index("-I")
            assert str(mock_settings.astrometry_index_dir.resolve()) in args[idx + 1]
            assert "-v" in args  # verbose
            assert "-s" in args  # solved file
            assert "-j" in args  # job ID
            assert "job-123" in args

