from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from starlette.datastructures import UploadFile as StarletteUploadFile
from fastapi.responses import FileResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.deps import get_db
from core.config import settings
from domain.enums import ArtifactType, JobStatus
from domain.models import Job
from services import jobs as job_service
from services import submissions as submission_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["legacy"])
file_router = APIRouter(tags=["files"])  # Separate router for file downloads (no /api prefix)


async def _parse_request_payload(request: Request) -> tuple[dict[str, Any], dict[str, UploadFile]]:
    content_type = request.headers.get("content-type", "")
    files: dict[str, UploadFile] = {}
    payload: dict[str, Any] = {}

    upload_types = (UploadFile, StarletteUploadFile)

    if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        data = form.get("request-json")
        if data is None:
            raise HTTPException(status_code=400, detail="missing request-json")
        payload = json.loads(data)
        for key, value in form.multi_items():
            if isinstance(value, upload_types):
                files[key] = value
    elif "application/json" in content_type:
        payload = await request.json()
    else:
        body = await request.body()
        if body:
            payload = json.loads(body)

    return payload, files


def _legacy_error(message: str) -> dict[str, Any]:
    return {"status": "error", "errormessage": message}


@router.post("/login")
async def login(request: Request, db: AsyncIOMotorDatabase = Depends(get_db)):
    payload, _ = await _parse_request_payload(request)
    apikey = payload.get("apikey")
    if not apikey:
        return _legacy_error('need "apikey"')
    valid = await submission_service.validate_api_key(db, apikey)
    if not valid:
        return _legacy_error("bad apikey")
    return {"status": "success", "session": apikey, "message": "authenticated"}


@router.post("/upload")
async def upload(request: Request, db: AsyncIOMotorDatabase = Depends(get_db)):
    payload, files = await _parse_request_payload(request)
    apikey = payload.get("apikey") or payload.get("session")
    if not apikey:
        return _legacy_error("need session")
    if not await submission_service.validate_api_key(db, apikey):
        return _legacy_error("bad apikey")
    upload_file = files.get("file")
    if upload_file is None:
        return _legacy_error("missing file")
    raw = await upload_file.read()
    result = await submission_service.create_submission(
        db,
        api_key=apikey,
        filename=upload_file.filename or "upload",
        data=raw,
        upload_args=payload,
    )
    return result


@router.post("/url_upload")
async def url_upload(request: Request, db: AsyncIOMotorDatabase = Depends(get_db)):
    payload, _ = await _parse_request_payload(request)
    apikey = payload.get("apikey") or payload.get("session")
    if not apikey:
        return _legacy_error("need session")
    if not await submission_service.validate_api_key(db, apikey):
        return _legacy_error("bad apikey")
    url = payload.get("url")
    if not url:
        return _legacy_error("missing url")
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:  # noqa: PERF203
            logger.error("Failed to download %s: %s", url, exc)
            return _legacy_error("failed to fetch url")
        filename = Path(url).name or "remote-upload"
        result = await submission_service.create_submission(
            db,
            api_key=apikey,
            filename=filename,
            data=resp.content,
            upload_args=payload,
        )
    return result


@router.post("/submission_images")
async def submission_images(request: Request, db: AsyncIOMotorDatabase = Depends(get_db)):
    payload, _ = await _parse_request_payload(request)
    subid = payload.get("subid")
    if not subid:
        return _legacy_error("missing subid")
    submission = await submission_service.get_submission(db, subid)
    if not submission:
        return _legacy_error("submission not found")
    return {"status": "success", "image_ids": []}


@router.api_route("/submissions/{submission_id}", methods=["GET", "POST"])
async def submission_status(submission_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    submission = await submission_service.get_submission(db, submission_id)
    if not submission:
        return _legacy_error("submission not found")
    return {
        "status": submission.status.value,
        "user": submission.api_key,
        "processing_started": submission.processing_started.isoformat() if submission.processing_started else None,
        "processing_finished": submission.processing_finished.isoformat() if submission.processing_finished else None,
        "jobs": submission.jobs,
        "job_calibrations": [],
        "images": [],
        "user_images": [],
    }


@router.api_route("/submissions/{submission_id}/jobs", methods=["GET", "POST"])
async def submission_jobs(submission_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    jobs = await submission_service.list_submission_jobs(db, submission_id)
    return {"status": "success", "jobs": jobs}


@router.api_route("/jobs/{job_id}", methods=["GET", "POST"])
async def job_status(job_id: int, db: AsyncIOMotorDatabase = Depends(get_db)):
    job = await job_service.get_job_by_job_id(db, job_id)
    if not job:
        return _legacy_error("job not found")
    return {"status": job.status.value}


def _ensure_job(job: Job | None, job_id: int) -> Job:
    if not job:
        raise HTTPException(status_code=404, detail=f"job {job_id} not found")
    return job


@router.api_route("/jobs/{job_id}/calibration", methods=["GET", "POST"])
async def job_calibration(job_id: int, db: AsyncIOMotorDatabase = Depends(get_db)):
    job = _ensure_job(await job_service.get_job_by_job_id(db, job_id), job_id)
    calibration = job.results.get("calibration") if job.results else None
    if not calibration:
        return {"error": f"no calibration data available for job {job_id}"}
    return calibration


@router.api_route("/jobs/{job_id}/tags", methods=["GET", "POST"])
async def job_tags(job_id: int, db: AsyncIOMotorDatabase = Depends(get_db)):
    job = _ensure_job(await job_service.get_job_by_job_id(db, job_id), job_id)
    return {"tags": job.tags}


@router.api_route("/jobs/{job_id}/machine_tags", methods=["GET", "POST"])
async def job_machine_tags(job_id: int, db: AsyncIOMotorDatabase = Depends(get_db)):
    job = _ensure_job(await job_service.get_job_by_job_id(db, job_id), job_id)
    return {"tags": job.machine_tags}


@router.api_route("/jobs/{job_id}/objects_in_field", methods=["GET", "POST"])
async def job_objects(job_id: int, db: AsyncIOMotorDatabase = Depends(get_db)):
    job = _ensure_job(await job_service.get_job_by_job_id(db, job_id), job_id)
    return {"objects_in_field": job.objects_in_field}


@router.api_route("/jobs/{job_id}/annotations", methods=["GET", "POST"])
async def job_annotations(job_id: int, db: AsyncIOMotorDatabase = Depends(get_db)):
    job = _ensure_job(await job_service.get_job_by_job_id(db, job_id), job_id)
    return {"annotations": job.annotations}


@router.api_route("/jobs/{job_id}/info", methods=["GET", "POST"])
async def job_info(job_id: int, db: AsyncIOMotorDatabase = Depends(get_db)):
    job = _ensure_job(await job_service.get_job_by_job_id(db, job_id), job_id)
    return {
        "objects_in_field": job.objects_in_field,
        "machine_tags": job.machine_tags,
        "tags": job.tags,
        "status": job.status.value,
        "original_filename": job.results.get("original_filename") if job.results else None,
        "calibration": job.results.get("calibration") if job.results else None,
    }


@router.api_route("/myjobs/", methods=["GET", "POST"])
async def my_jobs(request: Request, db: AsyncIOMotorDatabase = Depends(get_db)):
    payload, _ = await _parse_request_payload(request)
    session = payload.get("session")
    if not session:
        return _legacy_error("missing session")
    jobs = await job_service.my_jobs(db, session)
    return {"jobs": jobs, "status": "success"}


@router.api_route("/jobs_by_tag", methods=["GET", "POST"])
async def jobs_by_tag(request: Request, db: AsyncIOMotorDatabase = Depends(get_db)):
    payload, _ = await _parse_request_payload(request)
    query = payload.get("query") or request.query_params.get("query")
    exact = payload.get("exact") or request.query_params.get("exact")
    if not query:
        return _legacy_error("missing query")
    cursor = db["jobs"].find({"tags": query}) if exact else db["jobs"].find({"tags": {"$regex": query, "$options": "i"}})
    job_ids = [doc["job_id"] async for doc in cursor]
    return {"job_ids": job_ids}


@router.post("/sdss_image_for_wcs")
async def sdss_image_for_wcs(request: Request):
    """SDSS overlay feature is not supported in this lite version."""
    return {
        "status": "error",
        "errormessage": "SDSS overlay is not supported in Astrometry Lite. This feature requires external SDSS API integration which is not included in the simplified implementation.",
    }


@router.post("/galex_image_for_wcs")
async def galex_image_for_wcs(request: Request):
    """GALEX overlay feature is not supported in this lite version."""
    return {
        "status": "error",
        "errormessage": "GALEX overlay is not supported in Astrometry Lite. This feature requires external GALEX API integration which is not included in the simplified implementation.",
    }


def _get_artifact_filename(artifact_type: ArtifactType) -> str:
    """Map artifact type to actual filename."""
    mapping = {
        ArtifactType.wcs: "wcs.fits",
        ArtifactType.new_fits: "new.fits",
        ArtifactType.corr: "corr.fits",
        ArtifactType.kml: "sky.kmz",
        ArtifactType.annotated: "annotated.png",
    }
    return mapping.get(artifact_type, f"{artifact_type.value}.fits")


async def _artifact_response(job_id: int, artifact_type: ArtifactType, db: AsyncIOMotorDatabase) -> FileResponse:
    job = await job_service.get_job_by_job_id(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    
    # Get default filename for this artifact type
    default_filename = _get_artifact_filename(artifact_type)
    
    # Ensure job_output_dir is absolute
    job_output_dir = settings.job_output_dir
    if not job_output_dir.is_absolute():
        job_output_dir = job_output_dir.resolve()
    
    # Try to get path from artifacts, otherwise use default location
    artifacts = job.artifacts or {}
    rel = artifacts.get(artifact_type.value)
    
    if rel:
        # Path stored in MongoDB
        stored_path = Path(rel)
        if stored_path.is_absolute():
            path = stored_path
        else:
            # Relative path: try in job directory first
            job_dir_path = job_output_dir / str(job_id) / stored_path.name
            if job_dir_path.exists():
                path = job_dir_path
            else:
                # Try resolving relative to current working directory
                path = stored_path.resolve()
    else:
        # No path in MongoDB, use default location
        path = job_output_dir / str(job_id) / default_filename
    
    # Ensure absolute path for final check
    if not path.is_absolute():
        path = path.resolve()
    
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"file not ready: {path} (job_id={job_id}, type={artifact_type.value}, artifacts={artifacts}, job_output_dir={job_output_dir})"
        )
    
    media_type = "application/fits"
    if artifact_type == ArtifactType.annotated:
        media_type = "image/png"
    elif artifact_type == ArtifactType.kml:
        media_type = "application/vnd.google-earth.kmz"
    return FileResponse(path, media_type=media_type, filename=path.name)


@file_router.get("/wcs_file/{job_id}")
async def wcs_file(job_id: int, db: AsyncIOMotorDatabase = Depends(get_db)):
    return await _artifact_response(job_id, ArtifactType.wcs, db)


@file_router.get("/new_fits_file/{job_id}/")
async def new_fits_file(job_id: int, db: AsyncIOMotorDatabase = Depends(get_db)):
    return await _artifact_response(job_id, ArtifactType.new_fits, db)


@file_router.get("/corr_file/{job_id}")
async def corr_file(job_id: int, db: AsyncIOMotorDatabase = Depends(get_db)):
    return await _artifact_response(job_id, ArtifactType.corr, db)


@file_router.get("/kml_file/{job_id}/")
async def kml_file(job_id: int, db: AsyncIOMotorDatabase = Depends(get_db)):
    job = await job_service.get_job_by_job_id(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    artifacts = job.artifacts or {}
    rel = artifacts.get(ArtifactType.kml.value)
    path = Path(rel) if rel else settings.job_output_dir / str(job_id) / "sky.kmz"
    if not path.exists():
        raise HTTPException(status_code=404, detail="kml not ready")
    return FileResponse(path, media_type="application/vnd.google-earth.kmz", filename=path.name)


@file_router.get("/annotated_display/{job_id}")
async def annotated_display(job_id: int, db: AsyncIOMotorDatabase = Depends(get_db)):
    job = await job_service.get_job_by_job_id(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    annotations_path = job.artifacts.get(ArtifactType.annotated.value) if job.artifacts else None
    if annotations_path:
        path = Path(annotations_path)
        if not path.is_absolute():
            path = (settings.job_output_dir / str(job_id) / path.name).resolve()
    else:
        # Fallback to default location
        path = settings.job_output_dir / str(job_id) / "annotated.png"
        if not path.is_absolute():
            path = path.resolve()
    
    if not path.exists():
        raise HTTPException(status_code=404, detail="annotated image not ready")
    
    # Determine media type based on file extension
    media_type = "image/png"
    if path.suffix.lower() in (".jpg", ".jpeg"):
        media_type = "image/jpeg"
    
    return FileResponse(path, media_type=media_type, filename=path.name)
