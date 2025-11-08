from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import admin, legacy
from core.config import settings
from services.mongo import lifespan

app = FastAPI(title="Astrometry Lite API", lifespan=lifespan)

if settings.frontend_origin:
    origins = [settings.frontend_origin]
else:
    origins = ["http://localhost:5173", "http://127.0.0.1:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin.router, prefix="/api")
app.include_router(legacy.router, prefix="/api")


@app.get("/")
def root():
    return {"message": "Astrometry Lite API"}
