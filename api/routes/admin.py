from fastapi import APIRouter, Depends

from api.deps import get_settings
from core.config import AppSettings

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/health")
def health(settings: AppSettings = Depends(get_settings)):
    return {"status": "ok", "env": settings.env}
