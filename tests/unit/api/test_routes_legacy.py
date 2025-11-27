"""Unit tests for api/routes/legacy.py"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from api.main import app
from domain.enums import JobStatus
from domain.models import Job, Submission


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_db_in_app(mock_db: AsyncMock):
    """Inject mock database into app state."""
    app.state.mongo_db = mock_db
    yield mock_db
    if hasattr(app.state, "mongo_db"):
        delattr(app.state, "mongo_db")


class TestLoginEndpoint:
    """Tests for POST /api/login endpoint."""

    @patch("api.routes.legacy.submission_service.validate_api_key")
    def test_login_success(
        self, mock_validate: AsyncMock, client: TestClient, mock_db_in_app: AsyncMock
    ):
        """Test successful login."""
        mock_validate.return_value = True

        response = client.post(
            "/api/login",
            data={"request-json": '{"apikey": "valid_key"}'},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["session"] == "valid_key"

    @patch("api.routes.legacy.submission_service.validate_api_key")
    def test_login_invalid_key(
        self, mock_validate: AsyncMock, client: TestClient, mock_db_in_app: AsyncMock
    ):
        """Test login with invalid API key."""
        mock_validate.return_value = False

        response = client.post(
            "/api/login",
            data={"request-json": '{"apikey": "invalid_key"}'},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "bad apikey" in data["errormessage"]

    def test_login_missing_apikey(
        self, client: TestClient, mock_db_in_app: AsyncMock
    ):
        """Test login without API key."""
        response = client.post(
            "/api/login",
            data={"request-json": "{}"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "apikey" in data["errormessage"]


class TestJobStatusEndpoint:
    """Tests for /api/jobs/{job_id} endpoint."""

    @patch("api.routes.legacy.job_service.get_job_by_job_id")
    def test_get_job_status_success(
        self, mock_get_job: AsyncMock, client: TestClient, mock_db_in_app: AsyncMock
    ):
        """Test getting job status successfully."""
        mock_job = MagicMock(spec=Job)
        mock_job.status = JobStatus.success
        mock_get_job.return_value = mock_job

        response = client.get("/api/jobs/12345")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    @patch("api.routes.legacy.job_service.get_job_by_job_id")
    def test_get_job_status_not_found(
        self, mock_get_job: AsyncMock, client: TestClient, mock_db_in_app: AsyncMock
    ):
        """Test getting status for non-existent job."""
        mock_get_job.return_value = None

        response = client.get("/api/jobs/99999")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "not found" in data["errormessage"]


class TestJobCalibrationEndpoint:
    """Tests for /api/jobs/{job_id}/calibration endpoint."""

    @patch("api.routes.legacy.job_service.get_job_by_job_id")
    def test_get_calibration_success(
        self, mock_get_job: AsyncMock, client: TestClient, mock_db_in_app: AsyncMock
    ):
        """Test getting calibration data."""
        mock_job = MagicMock(spec=Job)
        mock_job.results = {
            "calibration": {
                "ra": 180.0,
                "dec": 45.0,
                "radius": 1.5,
                "pixscale": 1.2,
            }
        }
        mock_get_job.return_value = mock_job

        response = client.get("/api/jobs/12345/calibration")

        assert response.status_code == 200
        data = response.json()
        assert data["ra"] == 180.0
        assert data["dec"] == 45.0

    @patch("api.routes.legacy.job_service.get_job_by_job_id")
    def test_get_calibration_not_found(
        self, mock_get_job: AsyncMock, client: TestClient, mock_db_in_app: AsyncMock
    ):
        """Test getting calibration for non-existent job."""
        mock_get_job.return_value = None

        response = client.get("/api/jobs/99999/calibration")

        assert response.status_code == 404

    @patch("api.routes.legacy.job_service.get_job_by_job_id")
    def test_get_calibration_no_data(
        self, mock_get_job: AsyncMock, client: TestClient, mock_db_in_app: AsyncMock
    ):
        """Test getting calibration when no calibration data exists."""
        mock_job = MagicMock(spec=Job)
        mock_job.results = {}
        mock_get_job.return_value = mock_job

        response = client.get("/api/jobs/12345/calibration")

        assert response.status_code == 200
        data = response.json()
        assert "error" in data


class TestJobTagsEndpoint:
    """Tests for /api/jobs/{job_id}/tags endpoint."""

    @patch("api.routes.legacy.job_service.get_job_by_job_id")
    def test_get_tags(
        self, mock_get_job: AsyncMock, client: TestClient, mock_db_in_app: AsyncMock
    ):
        """Test getting job tags."""
        mock_job = MagicMock(spec=Job)
        mock_job.tags = ["M31", "Andromeda Galaxy"]
        mock_get_job.return_value = mock_job

        response = client.get("/api/jobs/12345/tags")

        assert response.status_code == 200
        data = response.json()
        assert data["tags"] == ["M31", "Andromeda Galaxy"]


class TestJobMachineTagsEndpoint:
    """Tests for /api/jobs/{job_id}/machine_tags endpoint."""

    @patch("api.routes.legacy.job_service.get_job_by_job_id")
    def test_get_machine_tags(
        self, mock_get_job: AsyncMock, client: TestClient, mock_db_in_app: AsyncMock
    ):
        """Test getting job machine tags."""
        mock_job = MagicMock(spec=Job)
        mock_job.machine_tags = ["messier m31", "ngc 224"]
        mock_get_job.return_value = mock_job

        response = client.get("/api/jobs/12345/machine_tags")

        assert response.status_code == 200
        data = response.json()
        assert "messier m31" in data["tags"]


class TestJobObjectsEndpoint:
    """Tests for /api/jobs/{job_id}/objects_in_field endpoint."""

    @patch("api.routes.legacy.job_service.get_job_by_job_id")
    def test_get_objects_in_field(
        self, mock_get_job: AsyncMock, client: TestClient, mock_db_in_app: AsyncMock
    ):
        """Test getting objects in field."""
        mock_job = MagicMock(spec=Job)
        mock_job.objects_in_field = ["M31", "NGC 224", "HD 3914"]
        mock_get_job.return_value = mock_job

        response = client.get("/api/jobs/12345/objects_in_field")

        assert response.status_code == 200
        data = response.json()
        assert len(data["objects_in_field"]) == 3


class TestJobAnnotationsEndpoint:
    """Tests for /api/jobs/{job_id}/annotations endpoint."""

    @patch("api.routes.legacy.job_service.get_job_by_job_id")
    def test_get_annotations(
        self, mock_get_job: AsyncMock, client: TestClient, mock_db_in_app: AsyncMock
    ):
        """Test getting annotations."""
        mock_job = MagicMock(spec=Job)
        mock_job.annotations = [
            {"type": "star", "names": ["HD 3914"], "pixelx": 100, "pixely": 200}
        ]
        mock_get_job.return_value = mock_job

        response = client.get("/api/jobs/12345/annotations")

        assert response.status_code == 200
        data = response.json()
        assert len(data["annotations"]) == 1


class TestJobInfoEndpoint:
    """Tests for /api/jobs/{job_id}/info endpoint."""

    @patch("api.routes.legacy.job_service.get_job_by_job_id")
    def test_get_job_info(
        self, mock_get_job: AsyncMock, client: TestClient, mock_db_in_app: AsyncMock
    ):
        """Test getting full job info."""
        mock_job = MagicMock(spec=Job)
        mock_job.status = JobStatus.success
        mock_job.objects_in_field = ["M31"]
        mock_job.machine_tags = ["messier m31"]
        mock_job.tags = ["M31"]
        mock_job.results = {
            "original_filename": "galaxy.jpg",
            "calibration": {"ra": 180.0},
        }
        mock_get_job.return_value = mock_job

        response = client.get("/api/jobs/12345/info")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["original_filename"] == "galaxy.jpg"
        assert data["calibration"]["ra"] == 180.0


class TestSubmissionStatusEndpoint:
    """Tests for /api/submissions/{submission_id} endpoint."""

    @patch("api.routes.legacy.submission_service.get_submission")
    def test_get_submission_status(
        self, mock_get_sub: AsyncMock, client: TestClient, mock_db_in_app: AsyncMock
    ):
        """Test getting submission status."""
        from domain.enums import SubmissionStatus

        mock_sub = MagicMock(spec=Submission)
        mock_sub.status = SubmissionStatus.success
        mock_sub.api_key = "test_key"
        mock_sub.processing_started = None
        mock_sub.processing_finished = None
        mock_sub.jobs = [12345]
        mock_get_sub.return_value = mock_sub

        response = client.get(f"/api/submissions/{ObjectId()}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert 12345 in data["jobs"]

    @patch("api.routes.legacy.submission_service.get_submission")
    def test_get_submission_not_found(
        self, mock_get_sub: AsyncMock, client: TestClient, mock_db_in_app: AsyncMock
    ):
        """Test getting non-existent submission."""
        mock_get_sub.return_value = None

        response = client.get(f"/api/submissions/{ObjectId()}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"


class TestUnsupportedFeatures:
    """Tests for unsupported feature endpoints."""

    def test_sdss_image_not_supported(
        self, client: TestClient, mock_db_in_app: AsyncMock
    ):
        """Test SDSS image endpoint returns not supported."""
        response = client.post("/api/sdss_image_for_wcs")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "not supported" in data["errormessage"].lower()

    def test_galex_image_not_supported(
        self, client: TestClient, mock_db_in_app: AsyncMock
    ):
        """Test GALEX image endpoint returns not supported."""
        response = client.post("/api/galex_image_for_wcs")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "not supported" in data["errormessage"].lower()
