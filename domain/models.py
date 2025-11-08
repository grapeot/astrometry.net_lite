from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from bson import ObjectId
from pydantic import BaseModel, Field

from domain.enums import ArtifactType, JobStatus, SubmissionStatus


class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, ObjectId):
            return v
        if isinstance(v, str):
            return ObjectId(v)
        raise TypeError("ObjectId required")


class MongoModel(BaseModel):
    id: Optional[PyObjectId] = Field(default=None, alias="_id")

    model_config = {
        "arbitrary_types_allowed": True,
        "populate_by_name": True,
        "json_encoders": {ObjectId: str},
    }


class Submission(MongoModel):
    api_key: str
    original_filename: str
    stored_path: str
    upload_args: dict[str, Any] = Field(default_factory=dict)
    status: SubmissionStatus = SubmissionStatus.queued
    jobs: list[int] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    processing_started: Optional[datetime] = None
    processing_finished: Optional[datetime] = None


class Job(MongoModel):
    job_id: int
    submission_id: PyObjectId
    status: JobStatus = JobStatus.queued
    failure_reason: Optional[str] = None
    results: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, str] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    machine_tags: list[str] = Field(default_factory=list)
    objects_in_field: list[dict[str, Any]] = Field(default_factory=list)
    annotations: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class Artifact(MongoModel):
    job_id: int
    artifact_type: ArtifactType
    path: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class QueueMessage(MongoModel):
    job_id: int
    payload: dict[str, Any]
    locked_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    attempts: int = 0
    failure_reason: Optional[str] = None

    @property
    def is_locked(self) -> bool:
        return self.locked_at is not None and self.completed_at is None
