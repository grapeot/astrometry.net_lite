from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from domain.enums import ArtifactType, JobStatus
from domain.models import Artifact, Job
from services.storage import prepare_job_dir

JOBS_COLLECTION = "jobs"
ARTIFACTS_COLLECTION = "artifacts"


async def get_job_by_job_id(db: AsyncIOMotorDatabase, job_id: int) -> Optional[Job]:
    doc = await db[JOBS_COLLECTION].find_one({"job_id": job_id})
    if doc:
        return Job(**doc)
    return None


async def update_job_status(
    db: AsyncIOMotorDatabase,
    job_id: int,
    status: JobStatus,
    *,
    failure_reason: str | None = None,
    results: dict[str, Any] | None = None,
    annotations: list[dict[str, Any]] | None = None,
    objects_in_field: list[dict[str, Any]] | None = None,
) -> None:
    update: dict[str, Any] = {
        "$set": {
            "status": status.value,
        }
    }
    if status in {JobStatus.success, JobStatus.failure}:
        update["$set"]["finished_at"] = datetime.utcnow()
    else:
        update.setdefault("$unset", {})["finished_at"] = ""
    if failure_reason:
        update["$set"]["failure_reason"] = failure_reason
    if results is not None:
        for key, value in results.items():
            update.setdefault("$set", {})[f"results.{key}"] = value
    if annotations is not None:
        update["$set"]["annotations"] = annotations
    if objects_in_field is not None:
        update["$set"]["objects_in_field"] = objects_in_field

    await db[JOBS_COLLECTION].update_one({"job_id": job_id}, update)


async def mark_job_started(db: AsyncIOMotorDatabase, job_id: int) -> None:
    await db[JOBS_COLLECTION].update_one(
        {"job_id": job_id},
        {"$set": {"status": JobStatus.solving.value, "started_at": datetime.utcnow()}},
    )


async def add_artifact(
    db: AsyncIOMotorDatabase,
    job_id: int,
    artifact_type: ArtifactType,
    path: str,
) -> None:
    artifact = Artifact(job_id=job_id, artifact_type=artifact_type, path=path)
    await db[ARTIFACTS_COLLECTION].update_one(
        {"job_id": job_id, "artifact_type": artifact_type.value},
        {"$set": artifact.model_dump(by_alias=True, exclude_none=True)},
        upsert=True,
    )
    await db[JOBS_COLLECTION].update_one(
        {"job_id": job_id},
        {"$set": {f"artifacts.{artifact_type.value}": path}},
    )


async def list_jobs_by_ids(db: AsyncIOMotorDatabase, job_ids: list[int]) -> list[Job]:
    cursor = db[JOBS_COLLECTION].find({"job_id": {"$in": job_ids}})
    return [Job(**doc) async for doc in cursor]


async def my_jobs(db: AsyncIOMotorDatabase, api_key: str) -> list[int]:
    cursor = db[JOBS_COLLECTION].find({"results.session": api_key}, {"job_id": 1})
    return [doc["job_id"] async for doc in cursor]
