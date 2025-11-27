from fastapi import HTTPException, Request, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from core.config import settings


def get_settings():
    return settings


def get_db(request: Request) -> AsyncIOMotorDatabase:
    db = getattr(request.app.state, "mongo_db", None)
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database not initialised")
    return db
