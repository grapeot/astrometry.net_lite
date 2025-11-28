"""
Frontend API routes for the Job gallery and detail views.

These routes are designed for the React frontend and provide:
- Job listing with pagination
- Job details with stage information
- Real-time log streaming for polling
- Original image access
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.deps import get_db
from domain.enums import JobStatus
from domain.models import Job
from services import jobs as job_service
from services import submissions as submission_service
from services.state_manager import StateManager
from services.storage import prepare_job_dir

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["frontend"])


@router.get("/jobs/list")
async def list_jobs(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by job status"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Get paginated list of jobs for the gallery view.

    Returns jobs sorted by creation time (newest first), with stage information
    for jobs that are currently being processed.
    """
    skip = (page - 1) * limit

    # Build query
    query: dict = {}
    if status:
        # Validate status
        try:
            JobStatus(status)
            query["status"] = status
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status}. Valid values: {[s.value for s in JobStatus]}"
            )

    # Query MongoDB
    cursor = db["jobs"].find(query).sort("created_at", -1).skip(skip).limit(limit)
    jobs = [Job(**doc) async for doc in cursor]

    # Build response
    result_jobs = []
    for job in jobs:
        job_data = {
            "job_id": job.job_id,
            "status": job.status.value,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "has_annotated_image": bool(job.artifacts and job.artifacts.get("annotated")),
        }

        # Add image URLs
        if job_data["has_annotated_image"]:
            job_data["annotated_image_url"] = f"/annotated_display/{job.job_id}"

        # Always provide original image URL (via submission)
        job_data["original_image_url"] = f"/api/files/original/{job.job_id}"

        # For solving jobs, add stage information from file system
        if job.status == JobStatus.solving:
            job_dir = prepare_job_dir(job.job_id)
            state = StateManager(job_dir)
            file_status = state.get_status()
            if file_status:
                job_data["stage"] = file_status.get("stage")
                job_data["message"] = file_status.get("message")

        result_jobs.append(job_data)

    # Get total count
    total = await db["jobs"].count_documents(query)

    return {
        "status": "success",
        "jobs": result_jobs,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "has_next": (skip + limit) < total,
        },
    }


@router.get("/jobs/{job_id}/detail")
async def get_job_detail(
    job_id: int,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Get full job details including calibration, objects, and artifacts.

    For jobs that are being processed, also includes stage and message
    from the file system state.
    """
    job = await job_service.get_job_by_job_id(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    result = {
        "job_id": job.job_id,
        "status": job.status.value,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "failure_reason": job.failure_reason,
        "has_annotated_image": bool(job.artifacts and job.artifacts.get("annotated")),
    }

    # Add image URLs
    if result["has_annotated_image"]:
        result["annotated_image_url"] = f"/annotated_display/{job_id}"

    # Get original image URL via submission
    submission = await submission_service.get_submission(db, str(job.submission_id))
    if submission:
        result["original_image_url"] = f"/api/files/original/{job_id}"
        result["original_filename"] = submission.original_filename

    # Add calibration data
    if job.results and job.results.get("calibration"):
        result["calibration"] = job.results["calibration"]

    # Add objects in field
    if job.objects_in_field:
        result["objects_in_field"] = job.objects_in_field

    # Add artifact download URLs
    artifacts = {}
    if job.artifacts:
        artifact_url_map = {
            "wcs": f"/wcs_file/{job_id}",
            "new_fits": f"/new_fits_file/{job_id}/",
            "corr": f"/corr_file/{job_id}",
            "kml": f"/kml_file/{job_id}/",
            "annotated": f"/annotated_display/{job_id}",
        }
        for artifact_type in job.artifacts:
            if artifact_type in artifact_url_map:
                artifacts[artifact_type] = artifact_url_map[artifact_type]
    result["artifacts"] = artifacts

    # For solving jobs, add stage information from file system
    if job.status == JobStatus.solving:
        job_dir = prepare_job_dir(job_id)
        state = StateManager(job_dir)
        file_status = state.get_status()
        if file_status:
            result["stage"] = file_status.get("stage")
            result["message"] = file_status.get("message")
        else:
            result["stage"] = None
            result["message"] = None

    return {"status": "success", "job": result}


@router.get("/jobs/{job_id}/log")
async def get_job_log(
    job_id: int,
    offset: int = Query(0, ge=0, description="Byte offset to start reading from"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Get job log with incremental reading support.

    This endpoint is designed for polling to get real-time log updates.
    Pass the offset returned in the previous response to get only new content.

    Returns:
        - job_status: Current MongoDB status
        - stage: Current processing stage from file system
        - message: Current status message
        - log: New log content since offset
        - offset: New offset for next request
        - is_running: Whether the job is still running
    """
    job = await job_service.get_job_by_job_id(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job_dir = prepare_job_dir(job_id)
    state = StateManager(job_dir)

    # Get file system status
    file_status = state.get_status()

    # Get incremental log
    log_content, new_offset = state.get_log(offset)

    return {
        "status": "success",
        "job_status": job.status.value,
        "stage": file_status.get("stage") if file_status else None,
        "message": file_status.get("message") if file_status else None,
        "log": log_content,
        "offset": new_offset,
        "is_running": job.status == JobStatus.solving,
    }


@router.get("/files/original/{job_id}")
async def get_original_file(
    job_id: int,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Get the original uploaded image for a job.

    This retrieves the original file from the submission associated with the job.
    """
    job = await job_service.get_job_by_job_id(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Get submission to find original file
    submission = await submission_service.get_submission(db, str(job.submission_id))
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found. Please check the job ID.")

    stored_path = Path(submission.stored_path)
    if not stored_path.is_absolute():
        stored_path = stored_path.resolve()

    if not stored_path.exists():
        raise HTTPException(status_code=404, detail="Original image file not found. It may have been deleted.")

    # Determine media type based on file extension
    suffix = stored_path.suffix.lower()
    media_type_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
        ".fits": "application/fits",
        ".fit": "application/fits",
        ".fts": "application/fits",
    }
    media_type = media_type_map.get(suffix, "application/octet-stream")

    return FileResponse(
        stored_path,
        media_type=media_type,
        filename=submission.original_filename or stored_path.name,
    )
