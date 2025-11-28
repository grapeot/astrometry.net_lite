from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routes import admin, frontend, legacy
from api.routes.legacy import file_router
from core.config import settings
from services.mongo import lifespan

app = FastAPI(title="Astrometry Lite API", lifespan=lifespan)

if settings.frontend_origin:
    origins = [settings.frontend_origin]
else:
    # 默认允许本地开发的前端端口
    origins = [
        f"http://localhost:{settings.frontend_port}",
        f"http://127.0.0.1:{settings.frontend_port}",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin.router, prefix="/api")
app.include_router(frontend.router)  # Frontend API routes - must be before legacy to avoid /jobs/{job_id} capturing /jobs/list
app.include_router(legacy.router, prefix="/api")
app.include_router(file_router)  # File download routes without /api prefix

# Serve static files from frontend/dist
frontend_dist_path = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist_path.exists():
    # Mount static assets (JS, CSS, images, etc.)
    app.mount("/assets", StaticFiles(directory=frontend_dist_path / "assets"), name="assets")
    
    # Serve root-level static files (like vite.svg)
    @app.get("/vite.svg")
    async def serve_vite_svg():
        svg_path = frontend_dist_path / "vite.svg"
        if svg_path.exists():
            return FileResponse(svg_path)
        return {"detail": "Not Found"}
    
    # Root route: serve index.html
    @app.get("/")
    async def serve_index():
        index_path = frontend_dist_path / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return {"detail": "Frontend index.html not found"}
    
    # Catch-all route: serve index.html for all non-API routes (SPA routing)
    # This must be registered last so API routes take precedence
    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        # Skip if this is an API route or file download route (shouldn't happen due to route order, but safety check)
        if full_path.startswith("api/") or full_path.startswith("annotated_display/") or \
           full_path.startswith("wcs_file/") or full_path.startswith("new_fits_file/") or \
           full_path.startswith("corr_file/") or full_path.startswith("kml_file/") or \
           full_path.startswith("assets/"):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Not Found")
        
        # Serve index.html for all other routes (React Router will handle routing)
        index_path = frontend_dist_path / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return {"detail": "Frontend not built. Please run 'npm run build' in the frontend directory."}
else:
    @app.get("/")
    def root():
        return {"message": "Astrometry Lite API", "note": "Frontend not built. Please run 'npm run build' in the frontend directory."}
