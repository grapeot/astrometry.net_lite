from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from domain.enums import SubmissionStatus
from domain.models import Job, Submission
from services.ids import get_next_sequence
from services import queue as queue_service
from services.storage import save_upload_file

logger = logging.getLogger(__name__)

SUBMISSIONS_COLLECTION = "submissions"
JOBS_COLLECTION = "jobs"
API_KEYS_COLLECTION = "api_keys"

# Public API key constants
PUBLIC_API_KEY = "public"
PUBLIC_API_KEY_PRIORITY = 100  # Lowest priority
PRIORITY_NORMAL = 50  # Default priority for regular users
PRIORITY_HIGH = 0  # High priority for VIP users


async def ensure_public_api_key(db: AsyncIOMotorDatabase) -> None:
    """Ensure public API key exists in database. Called at application startup."""
    existing = await db[API_KEYS_COLLECTION].find_one({"apikey": PUBLIC_API_KEY})
    if not existing:
        await db[API_KEYS_COLLECTION].insert_one({
            "apikey": PUBLIC_API_KEY,
            "priority": PUBLIC_API_KEY_PRIORITY,
            "is_system": True,
            "created_at": datetime.now(UTC),
            "description": "Public API key for unauthenticated users",
            "enabled": True,
        })
        logger.info("Created public API key")
    else:
        # Ensure priority is correct (in case it was modified)
        await db[API_KEYS_COLLECTION].update_one(
            {"apikey": PUBLIC_API_KEY},
            {"$set": {"priority": PUBLIC_API_KEY_PRIORITY, "is_system": True}}
        )


async def get_api_key_priority(db: AsyncIOMotorDatabase, api_key: str) -> int:
    """Get priority for an API key. Lower number = higher priority."""
    if api_key == PUBLIC_API_KEY:
        # Try to get from database first, fallback to constant
        doc = await db[API_KEYS_COLLECTION].find_one({"apikey": PUBLIC_API_KEY})
        if doc:
            return doc.get("priority", PUBLIC_API_KEY_PRIORITY)
        return PUBLIC_API_KEY_PRIORITY
    
    # For regular API keys, get priority from database
    doc = await db[API_KEYS_COLLECTION].find_one({"apikey": api_key})
    if doc:
        return doc.get("priority", PRIORITY_NORMAL)
    
    # Default priority for unknown API keys
    return PRIORITY_NORMAL


async def validate_api_key(db: AsyncIOMotorDatabase, api_key: str) -> bool:
    """Validate API key. Public API key is always valid."""
    if api_key == PUBLIC_API_KEY:
        return True
    
    doc = await db[API_KEYS_COLLECTION].find_one({"apikey": api_key, "enabled": {"$ne": False}})
    return doc is not None


async def create_submission(
    db: AsyncIOMotorDatabase,
    api_key: str,
    filename: str,
    data: bytes,
    upload_args: dict[str, Any],
) -> dict[str, Any]:
    unique_name = f"{uuid.uuid4().hex}_{filename}"
    stored_path = str(save_upload_file(unique_name, data))
    submission = Submission(
        api_key=api_key,
        original_filename=filename,
        stored_path=stored_path,
        upload_args=upload_args,
    )
    doc = submission.model_dump(by_alias=True, exclude_none=True)
    result = await db[SUBMISSIONS_COLLECTION].insert_one(doc)
    submission_id = result.inserted_id

    job_id = await get_next_sequence(db, "jobs")
    job = Job(job_id=job_id, submission_id=submission_id, results={"session": api_key, "original_filename": filename})
    await db[JOBS_COLLECTION].insert_one(job.model_dump(by_alias=True, exclude_none=True))

    await db[SUBMISSIONS_COLLECTION].update_one(
        {"_id": submission_id},
        {"$set": {"status": SubmissionStatus.queued.value, "updated_at": datetime.now(UTC)}, "$push": {"jobs": job_id}},
    )

    payload = {
        "submission_id": str(submission_id),
        "stored_path": stored_path,
        "upload_args": upload_args,
    }
    queue_msg = await queue_service.enqueue_job(db, job_id, payload, api_key)

    return {
        "status": "success",
        "subid": str(submission_id),
        "hash": unique_name,
        "job_id": job_id,
        "queue_id": str(queue_msg.id) if queue_msg.id else None,
    }


async def mark_submission_started(db: AsyncIOMotorDatabase, submission_id: str) -> None:
    await db[SUBMISSIONS_COLLECTION].update_one(
        {"_id": ObjectId(submission_id)},
        {
            "$set": {
                "processing_started": datetime.now(UTC),
                "status": SubmissionStatus.processing.value,
                "updated_at": datetime.now(UTC),
            }
        },
    )


async def mark_submission_finished(db: AsyncIOMotorDatabase, submission_id: str, status: SubmissionStatus) -> None:
    await db[SUBMISSIONS_COLLECTION].update_one(
        {"_id": ObjectId(submission_id)},
        {
            "$set": {
                "processing_finished": datetime.now(UTC),
                "status": status.value,
                "updated_at": datetime.now(UTC),
            }
        },
    )


async def get_submission(db: AsyncIOMotorDatabase, submission_id: str) -> Optional[Submission]:
    doc = await db[SUBMISSIONS_COLLECTION].find_one({"_id": ObjectId(submission_id)})
    if doc:
        return Submission(**doc)
    return None


async def list_submission_jobs(db: AsyncIOMotorDatabase, submission_id: str) -> list[int]:
    doc = await db[SUBMISSIONS_COLLECTION].find_one({"_id": ObjectId(submission_id)}, {"jobs": 1})
    if doc:
        return doc.get("jobs", [])
    return []
