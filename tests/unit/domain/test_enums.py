"""Unit tests for domain/enums.py"""

from __future__ import annotations

import pytest

from domain.enums import ArtifactType, JobStatus, SubmissionStatus


class TestJobStatus:
    """Tests for JobStatus enum."""

    def test_job_status_values(self):
        """Test that all expected job statuses exist."""
        assert JobStatus.queued.value == "queued"
        assert JobStatus.solving.value == "solving"
        assert JobStatus.success.value == "success"
        assert JobStatus.failure.value == "failure"

    def test_job_status_is_str_enum(self):
        """Test that JobStatus is a string enum."""
        assert isinstance(JobStatus.queued, str)
        assert JobStatus.queued == "queued"


class TestSubmissionStatus:
    """Tests for SubmissionStatus enum."""

    def test_submission_status_values(self):
        """Test that all expected submission statuses exist."""
        assert SubmissionStatus.queued.value == "queued"
        assert SubmissionStatus.processing.value == "processing"
        assert SubmissionStatus.success.value == "success"
        assert SubmissionStatus.failure.value == "failure"

    def test_submission_status_is_str_enum(self):
        """Test that SubmissionStatus is a string enum."""
        assert isinstance(SubmissionStatus.queued, str)
        assert SubmissionStatus.processing == "processing"


class TestArtifactType:
    """Tests for ArtifactType enum."""

    def test_artifact_type_values(self):
        """Test that all expected artifact types exist."""
        assert ArtifactType.wcs.value == "wcs"
        assert ArtifactType.new_fits.value == "new_fits"
        assert ArtifactType.corr.value == "corr"
        assert ArtifactType.kml.value == "kml"
        assert ArtifactType.annotated.value == "annotated"

    def test_artifact_type_is_str_enum(self):
        """Test that ArtifactType is a string enum."""
        assert isinstance(ArtifactType.wcs, str)
        assert ArtifactType.annotated == "annotated"

    def test_artifact_type_count(self):
        """Test that there are exactly 5 artifact types."""
        assert len(ArtifactType) == 5
