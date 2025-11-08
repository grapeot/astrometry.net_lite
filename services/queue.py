from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase

from core.config import settings
from domain.models import QueueMessage

QUEUE_COLLECTION = "queue_messages"


def _collection(db: AsyncIOMotorDatabase) -> AsyncIOMotorCollection:
    return db[QUEUE_COLLECTION]


async def enqueue_job(db: AsyncIOMotorDatabase, job_id: int, payload: dict[str, Any]) -> QueueMessage:
    doc = QueueMessage(job_id=job_id, payload=payload).model_dump(by_alias=True, exclude_none=True)
    result = await _collection(db).insert_one(doc)
    doc["_id"] = result.inserted_id
    return QueueMessage(**doc)


async def lease_job(db: AsyncIOMotorDatabase) -> Optional[QueueMessage]:
    now = datetime.utcnow()
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
        sort=[("locked_at", 1)],
    )
    if doc:
        return QueueMessage(**doc)
    return None


async def complete_job(db: AsyncIOMotorDatabase, queue_id) -> None:
    await _collection(db).update_one({"_id": queue_id}, {"$set": {"completed_at": datetime.utcnow()}})


async def fail_job(db: AsyncIOMotorDatabase, queue_id, reason: str) -> None:
    await _collection(db).update_one(
        {"_id": queue_id},
        {"$set": {"failed_at": datetime.utcnow(), "failure_reason": reason}},
    )
