"""Unit tests for api/routes/frontend.py"""

from __future__ import annotations

from datetime import UTC, datetime
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


class TestListJobsEndpoint:
    """Tests for GET /api/jobs/list endpoint."""

    def test_list_jobs_success(
        self, client: TestClient, mock_db_in_app: AsyncMock
    ):
        """Test listing jobs successfully."""
        # Setup mock cursor
        jobs_data = [
            {
                "_id": ObjectId(),
                "job_id": 1,
                "submission_id": ObjectId(),
                "status": "success",
                "created_at": datetime.now(UTC),
                "started_at": datetime.now(UTC),
                "finished_at": datetime.now(UTC),
                "artifacts": {"annotated": "path/to/annotated.jpg"},
                "results": {},
                "tags": [],
                "machine_tags": [],
                "objects_in_field": [],
                "annotations": [],
            },
            {
                "_id": ObjectId(),
                "job_id": 2,
                "submission_id": ObjectId(),
                "status": "solving",
                "created_at": datetime.now(UTC),
                "started_at": datetime.now(UTC),
                "finished_at": None,
                "artifacts": {},
                "results": {},
                "tags": [],
                "machine_tags": [],
                "objects_in_field": [],
                "annotations": [],
            },
        ]

        # Create async iterable cursor class
        class AsyncCursor:
            def __init__(self, docs):
                self.docs = docs
                self.index = 0

            def sort(self, *args, **kwargs):
                return self

            def skip(self, *args, **kwargs):
                return self

            def limit(self, *args, **kwargs):
                return self

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.docs):
                    raise StopAsyncIteration
                doc = self.docs[self.index]
                self.index += 1
                return doc

        mock_collection = MagicMock()
        mock_collection.find.return_value = AsyncCursor(jobs_data)
        mock_collection.count_documents = AsyncMock(return_value=2)

        mock_db_in_app.__getitem__ = MagicMock(return_value=mock_collection)

        with patch("api.routes.frontend.prepare_job_dir") as mock_prep:
            mock_prep.return_value = MagicMock()
            with patch("api.routes.frontend.StateManager") as mock_sm:
                mock_sm.return_value.get_status.return_value = {"stage": "solving", "message": "Processing..."}

                response = client.get("/api/jobs/list")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert len(data["jobs"]) == 2
        assert "pagination" in data
        assert data["pagination"]["total"] == 2

    def test_list_jobs_with_pagination(
        self, client: TestClient, mock_db_in_app: AsyncMock
    ):
        """Test listing jobs with pagination parameters."""
        class AsyncCursor:
            def __init__(self):
                pass

            def sort(self, *args, **kwargs):
                return self

            def skip(self, *args, **kwargs):
                return self

            def limit(self, *args, **kwargs):
                return self

            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

        mock_collection = MagicMock()
        mock_collection.find.return_value = AsyncCursor()
        mock_collection.count_documents = AsyncMock(return_value=100)

        mock_db_in_app.__getitem__ = MagicMock(return_value=mock_collection)

        response = client.get("/api/jobs/list?page=2&limit=10")

        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["page"] == 2
        assert data["pagination"]["limit"] == 10

    def test_list_jobs_with_status_filter(
        self, client: TestClient, mock_db_in_app: AsyncMock
    ):
        """Test filtering jobs by status."""
        class AsyncCursor:
            def sort(self, *args, **kwargs):
                return self

            def skip(self, *args, **kwargs):
                return self

            def limit(self, *args, **kwargs):
                return self

            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

        mock_collection = MagicMock()
        mock_collection.find.return_value = AsyncCursor()
        mock_collection.count_documents = AsyncMock(return_value=0)

        mock_db_in_app.__getitem__ = MagicMock(return_value=mock_collection)

        response = client.get("/api/jobs/list?status=success")

        assert response.status_code == 200

    def test_list_jobs_invalid_status(
        self, client: TestClient, mock_db_in_app: AsyncMock
    ):
        """Test filtering with invalid status returns error."""
        response = client.get("/api/jobs/list?status=invalid")

        assert response.status_code == 400


class TestGetJobDetailEndpoint:
    """Tests for GET /api/jobs/{job_id}/detail endpoint."""

    @patch("api.routes.frontend.job_service.get_job_by_job_id")
    @patch("api.routes.frontend.submission_service.get_submission")
    def test_get_job_detail_success(
        self,
        mock_get_sub: AsyncMock,
        mock_get_job: AsyncMock,
        client: TestClient,
        mock_db_in_app: AsyncMock,
    ):
        """Test getting job detail successfully."""
        mock_job = MagicMock(spec=Job)
        mock_job.job_id = 12345
        mock_job.status = JobStatus.success
        mock_job.created_at = datetime.now(UTC)
        mock_job.started_at = datetime.now(UTC)
        mock_job.finished_at = datetime.now(UTC)
        mock_job.failure_reason = None
        mock_job.submission_id = ObjectId()
        mock_job.artifacts = {"wcs": "path/to/wcs.fits", "annotated": "path/to/annotated.jpg"}
        mock_job.results = {"calibration": {"ra": 180.0, "dec": 45.0}}
        mock_job.objects_in_field = ["M31"]
        mock_get_job.return_value = mock_job

        mock_sub = MagicMock(spec=Submission)
        mock_sub.original_filename = "galaxy.jpg"
        mock_get_sub.return_value = mock_sub

        response = client.get("/api/jobs/12345/detail")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["job"]["job_id"] == 12345
        assert data["job"]["calibration"]["ra"] == 180.0
        assert "wcs" in data["job"]["artifacts"]

    @patch("api.routes.frontend.job_service.get_job_by_job_id")
    def test_get_job_detail_not_found(
        self,
        mock_get_job: AsyncMock,
        client: TestClient,
        mock_db_in_app: AsyncMock,
    ):
        """Test getting detail for non-existent job."""
        mock_get_job.return_value = None

        response = client.get("/api/jobs/99999/detail")

        assert response.status_code == 404

    @patch("api.routes.frontend.job_service.get_job_by_job_id")
    @patch("api.routes.frontend.submission_service.get_submission")
    @patch("api.routes.frontend.prepare_job_dir")
    @patch("api.routes.frontend.StateManager")
    def test_get_job_detail_with_solving_status(
        self,
        mock_state_manager: MagicMock,
        mock_prep_dir: MagicMock,
        mock_get_sub: AsyncMock,
        mock_get_job: AsyncMock,
        client: TestClient,
        mock_db_in_app: AsyncMock,
    ):
        """Test getting detail for a job that is solving."""
        mock_job = MagicMock(spec=Job)
        mock_job.job_id = 12345
        mock_job.status = JobStatus.solving
        mock_job.created_at = datetime.now(UTC)
        mock_job.started_at = datetime.now(UTC)
        mock_job.finished_at = None
        mock_job.failure_reason = None
        mock_job.submission_id = ObjectId()
        mock_job.artifacts = {}
        mock_job.results = {}
        mock_job.objects_in_field = []
        mock_get_job.return_value = mock_job

        mock_get_sub.return_value = None

        mock_prep_dir.return_value = MagicMock()
        mock_state_manager.return_value.get_status.return_value = {
            "stage": "extracting",
            "message": "Extracting sources...",
        }

        response = client.get("/api/jobs/12345/detail")

        assert response.status_code == 200
        data = response.json()
        assert data["job"]["stage"] == "extracting"
        assert data["job"]["message"] == "Extracting sources..."


class TestGetJobLogEndpoint:
    """Tests for GET /api/jobs/{job_id}/log endpoint."""

    @patch("api.routes.frontend.job_service.get_job_by_job_id")
    @patch("api.routes.frontend.prepare_job_dir")
    @patch("api.routes.frontend.StateManager")
    def test_get_job_log_success(
        self,
        mock_state_manager: MagicMock,
        mock_prep_dir: MagicMock,
        mock_get_job: AsyncMock,
        client: TestClient,
        mock_db_in_app: AsyncMock,
    ):
        """Test getting job log."""
        mock_job = MagicMock(spec=Job)
        mock_job.status = JobStatus.solving
        mock_get_job.return_value = mock_job

        mock_prep_dir.return_value = MagicMock()
        mock_sm = MagicMock()
        mock_sm.get_status.return_value = {"stage": "solving", "message": "Processing..."}
        mock_sm.get_log.return_value = ("Log content here...", 100)
        mock_state_manager.return_value = mock_sm

        response = client.get("/api/jobs/12345/log")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["log"] == "Log content here..."
        assert data["offset"] == 100
        assert data["is_running"] is True

    @patch("api.routes.frontend.job_service.get_job_by_job_id")
    def test_get_job_log_not_found(
        self,
        mock_get_job: AsyncMock,
        client: TestClient,
        mock_db_in_app: AsyncMock,
    ):
        """Test getting log for non-existent job."""
        mock_get_job.return_value = None

        response = client.get("/api/jobs/99999/log")

        assert response.status_code == 404

    @patch("api.routes.frontend.job_service.get_job_by_job_id")
    @patch("api.routes.frontend.prepare_job_dir")
    @patch("api.routes.frontend.StateManager")
    def test_get_job_log_with_offset(
        self,
        mock_state_manager: MagicMock,
        mock_prep_dir: MagicMock,
        mock_get_job: AsyncMock,
        client: TestClient,
        mock_db_in_app: AsyncMock,
    ):
        """Test getting job log with offset parameter."""
        mock_job = MagicMock(spec=Job)
        mock_job.status = JobStatus.solving
        mock_get_job.return_value = mock_job

        mock_prep_dir.return_value = MagicMock()
        mock_sm = MagicMock()
        mock_sm.get_status.return_value = {}
        mock_sm.get_log.return_value = ("New content", 200)
        mock_state_manager.return_value = mock_sm

        response = client.get("/api/jobs/12345/log?offset=100")

        assert response.status_code == 200
        data = response.json()
        assert data["offset"] == 200


class TestGetOriginalFileEndpoint:
    """Tests for GET /api/files/original/{job_id} endpoint."""

    @patch("api.routes.frontend.job_service.get_job_by_job_id")
    def test_get_original_file_job_not_found(
        self,
        mock_get_job: AsyncMock,
        client: TestClient,
        mock_db_in_app: AsyncMock,
    ):
        """Test getting original file for non-existent job."""
        mock_get_job.return_value = None

        response = client.get("/api/files/original/99999")

        assert response.status_code == 404

    @patch("api.routes.frontend.job_service.get_job_by_job_id")
    @patch("api.routes.frontend.submission_service.get_submission")
    def test_get_original_file_submission_not_found(
        self,
        mock_get_sub: AsyncMock,
        mock_get_job: AsyncMock,
        client: TestClient,
        mock_db_in_app: AsyncMock,
    ):
        """Test getting original file when submission not found."""
        mock_job = MagicMock(spec=Job)
        mock_job.submission_id = ObjectId()
        mock_get_job.return_value = mock_job
        mock_get_sub.return_value = None

        response = client.get("/api/files/original/12345")

        assert response.status_code == 404
        assert "Submission not found" in response.json()["detail"]
