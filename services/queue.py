from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase

from core.config import settings
from domain.models import QueueMessage

QUEUE_COLLECTION = "queue_messages"


def _collection(db: AsyncIOMotorDatabase) -> AsyncIOMotorCollection:
    return db[QUEUE_COLLECTION]


async def enqueue_job(
    db: AsyncIOMotorDatabase,
    job_id: int,
    payload: dict[str, Any],
    api_key: Optional[str] = None,
) -> QueueMessage:
    """Enqueue a job with priority based on API key."""
    # Lazy import to avoid circular dependency
    from services.submissions import get_api_key_priority
    
    # Get priority from API key if provided
    priority = await get_api_key_priority(db, api_key) if api_key else 50
    
    doc = QueueMessage(
        job_id=job_id,
        payload=payload,
        priority=priority,
        api_key=api_key,
    ).model_dump(by_alias=True, exclude_none=True)
    
    result = await _collection(db).insert_one(doc)
    doc["_id"] = result.inserted_id
    return QueueMessage(**doc)


async def lease_job(db: AsyncIOMotorDatabase) -> Optional[QueueMessage]:
    """Lease a job from the queue, ordered by priority (lower number = higher priority)."""
    now = datetime.now(UTC)
    expiry = now - timedelta(seconds=settings.queue_visibility_timeout_seconds)
    doc = await _collection(db).find_one_and_update(
        {
            "completed_at": None,
            "failed_at": None,
            "$or": [
                {"locked_at": None},
                {"locked_at": {"$lt": expiry}},
            ],
        },
        {
            "$set": {"locked_at": now},
            "$inc": {"attempts": 1},
        },
        return_document=True,
        sort=[
            ("priority", 1),      # Lower priority number = higher priority
            ("created_at", 1),    # Same priority: FIFO by creation time
        ],
    )
    if doc:
        return QueueMessage(**doc)
    return None


async def complete_job(db: AsyncIOMotorDatabase, queue_id) -> None:
    await _collection(db).update_one({"_id": queue_id}, {"$set": {"completed_at": datetime.now(UTC)}})


async def fail_job(db: AsyncIOMotorDatabase, queue_id, reason: str) -> None:
    await _collection(db).update_one(
        {"_id": queue_id},
        {"$set": {"failed_at": datetime.now(UTC), "failure_reason": reason}},
    )
