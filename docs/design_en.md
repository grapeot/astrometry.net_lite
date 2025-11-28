# Astrometry Lite - System Design

> 中文版本: [design_cn.md](./design_cn.md)

## Overview

**Astrometry Lite** is a modern reimplementation of the [astrometry.net](https://astrometry.net) plate-solving service. The original astrometry.net, created around 2010, revolutionized astronomical image calibration by using geometric invariants and clever heuristics to achieve fast, reliable blind plate solving.

However, the original implementation was built with technologies of that era—Django monolith, WSGI/FastCGI deployment, server-side templating, and Python 2 compatibility layers. This project asks: **What would astrometry.net look like if we built it today, in 2025?**

Astrometry Lite answers this with:
- **FastAPI** for async, high-performance API
- **React + Vite** for modern frontend
- **MongoDB** for flexible document storage
- **Real-time job tracking** via file system state

**Live Demo:** [https://astrometry.yage.ai/](https://astrometry.yage.ai/)

## Original vs Modern Implementation

### The Original (net/ directory)

The original astrometry.net implementation (still preserved in `net/`) showcases 2009-2012 era web development:

| Aspect | Original Implementation |
|--------|------------------------|
| **Framework** | Django 1.x monolith |
| **Deployment** | WSGI/FastCGI (Apache mod_wsgi) |
| **Database** | PostgreSQL with Django ORM |
| **Frontend** | Server-side Django templates |
| **API Style** | Manual JSON serialization, `text/plain` responses |
| **Python** | Python 2/3 hybrid with `__future__` imports |
| **Architecture** | Single Django app with 14 view files, 1398-line models.py |
| **Upload Handling** | Manual multipart boundary construction |
| **Authentication** | Django sessions + social auth |

**Characteristics of the legacy code:**
- Function-based views with regex URL routing
- Custom `python2json`/`json2python` conversion functions
- Monolithic structure mixing API, frontend, and admin
- External secrets via Python module imports
- Heavy reliance on system paths (`/data/`, `/usr/local/`)

### Astrometry Lite (This Project)

| Aspect | Modern Implementation |
|--------|----------------------|
| **Framework** | FastAPI (async, type-safe) |
| **Deployment** | Uvicorn ASGI server |
| **Database** | MongoDB with Motor (async driver) |
| **Frontend** | React + Vite + TypeScript (SPA) |
| **API Style** | OpenAPI/Swagger, proper JSON, Pydantic validation |
| **Python** | Python 3.12+ only |
| **Architecture** | Microservices: separate API, Worker, Frontend (Dev)<br>Unified: Backend serves Frontend (Prod) |
| **Upload Handling** | FastAPI native multipart support |
| **Authentication** | Simple API key (single-tenant) |
| **Static Files** | FastAPI StaticFiles + SPA routing support |
| **Docker** | Multi-stage build, frontend build integrated into backend image |

## Architecture

### Development Environment

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (React + Vite Dev Server)      │
│  Port: 5173                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  JobGrid    │  │ JobDetail   │  │  Console (Auth)     │  │
│  │  (public)   │  │ (public)    │  │  (upload/manage)    │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└────────────────────────────┬────────────────────────────────┘
                             │ HTTP (CORS)
┌────────────────────────────▼────────────────────────────────┐
│                    FastAPI Backend                           │
│  Port: 8002                                                  │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐  │
│  │ Legacy API     │  │ Frontend API   │  │ File Router  │  │
│  │ /api/*         │  │ /api/jobs/*    │  │ /wcs_file/*  │  │
│  └────────────────┘  └────────────────┘  └──────────────┘  │
└───────┬─────────────────────┬───────────────────┬───────────┘
        │                     │                   │
┌───────▼─────────┐  ┌────────▼────────┐  ┌──────▼──────────┐
│    MongoDB      │  │  File System    │  │   Worker        │
│  - api_keys     │  │  - uploads/     │  │  - solve-field  │
│  - submissions  │  │  - jobs/{id}/   │  │  - annotator    │
│  - jobs         │  │    - wcs.fits   │  │                 │
│  - queue        │  │    - status.json│  │                 │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

### Production Environment (Simplified)

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Backend (Unified Service)         │
│  Port: 8002                                                  │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Static File Serving (frontend/dist)                    │ │
│  │  - /assets/* (JS, CSS)                                  │ │
│  │  - / (SPA routing, returns index.html)                  │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐  │
│  │ Legacy API     │  │ Frontend API   │  │ File Router  │  │
│  │ /api/*         │  │ /api/jobs/*    │  │ /wcs_file/*  │  │
│  └────────────────┘  └────────────────┘  └──────────────┘  │
└───────┬─────────────────────┬───────────────────┬───────────┘
        │                     │                   │
┌───────▼─────────┐  ┌────────▼────────┐  ┌──────▼──────────┐
│    MongoDB      │  │  File System    │  │   Worker        │
│  - api_keys     │  │  - uploads/     │  │  - solve-field  │
│  - submissions  │  │  - jobs/{id}/   │  │  - annotator    │
│  - jobs         │  │    - wcs.fits   │  │                 │
│  - queue        │  │    - status.json│  │                 │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

**Production Environment Features:**
- Backend container includes frontend build artifacts (`frontend/dist`)
- FastAPI automatically serves static files and SPA routing
- Frontend uses relative path `/api` to call backend API
- Single port (8002) provides complete service
- No separate nginx or frontend container needed

## Technology Stack

| Component | Technology |
|-----------|------------|
| Backend | FastAPI + Uvicorn |
| Database | MongoDB 7+ (Motor async driver) |
| Queue | MongoDB-backed (queue_messages collection) |
| Solver | Astrometry.net CLI (Homebrew) |
| Frontend | React 19 + Vite 7 + TypeScript |
| Image Processing | Pillow, Astropy |
| Static File Serving | FastAPI StaticFiles (Production) |
| Deployment | Docker + Docker Compose (Multi-stage build) |

## Data Model

### MongoDB Collections

**api_keys**
```javascript
{
  _id: ObjectId,
  apikey: "test-key-12345",  // unique index
  email: "user@example.com",
  created_at: ISODate
}
```

**submissions**
```javascript
{
  _id: ObjectId,
  api_key: "test-key-12345",
  original_filename: "image.jpg",
  stored_path: "./data/uploads/uuid-image.jpg",
  upload_args: { scale_units: "arcsecperpix", ... },
  status: "queued|processing|success|failure",
  jobs: [1, 2, 3],
  created_at: ISODate,
  processing_started: ISODate,
  processing_finished: ISODate
}
```

**jobs**
```javascript
{
  _id: ObjectId,
  job_id: 123,  // unique auto-increment
  submission_id: ObjectId,
  status: "queued|solving|success|failure",
  failure_reason: null,
  results: {
    original_filename: "image.jpg",
    calibration: { ra, dec, pixscale, orientation, radius, ... }
  },
  artifacts: {
    wcs: "./data/jobs/123/wcs.fits",
    new_fits: "./data/jobs/123/new.fits",
    annotated: "./data/jobs/123/annotated.jpg"
  },
  objects_in_field: ["M31", "NGC 224", ...],
  annotations: [{ text: "M31" }, ...],
  created_at: ISODate,
  started_at: ISODate,
  finished_at: ISODate
}
```

### File System Structure

```
data/
├── uploads/           # Original uploaded files
│   └── uuid-image.jpg
└── jobs/
    └── {job_id}/
        ├── status.json      # Real-time processing state
        ├── solve-field.log  # CLI output log
        ├── wcs.fits         # World Coordinate System
        ├── new.fits         # Solved FITS with WCS header
        ├── corr.fits        # Star correlation data
        └── annotated.jpg    # Annotated image
```

## Job State Management

### Hybrid State Model

The system uses a hybrid approach:
1. **MongoDB (Authoritative)**: Final job status
2. **File System (Progress)**: Real-time stage and logs

### State Flow

```
MongoDB Status:    queued ──► solving ──► success
                                │
                                └──────► failure

File System Stage: started ──► solving ──► calibrating ──► annotating ──► completed
```

### status.json Format

```json
{
  "job_id": 123,
  "stage": "solving",
  "message": "Running solve-field...",
  "started_at": "2025-11-26T18:26:02Z",
  "updated_at": "2025-11-26T18:26:15Z",
  "steps_completed": ["started"],
  "error": null
}
```

## API Endpoints

### Legacy API (Authentication Required)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/login` | POST | API key authentication |
| `/api/upload` | POST | File upload |
| `/api/url_upload` | POST | URL upload |
| `/api/submissions/{id}` | GET/POST | Submission status |
| `/api/jobs/{id}` | GET/POST | Job status |
| `/api/jobs/{id}/calibration` | GET/POST | Calibration data |
| `/api/jobs/{id}/info` | GET/POST | Full job info |
| `/api/myjobs/` | GET/POST | User's jobs |

### Frontend API (Public)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/jobs/list` | GET | Paginated job list |
| `/api/jobs/{id}/detail` | GET | Full job details |
| `/api/jobs/{id}/log` | GET | Real-time log |
| `/api/files/original/{id}` | GET | Original image |

### File Downloads

| Endpoint | Description |
|----------|-------------|
| `/wcs_file/{id}` | WCS FITS file |
| `/new_fits_file/{id}/` | Solved FITS file |
| `/corr_file/{id}` | Correlation data |
| `/annotated_display/{id}` | Annotated image |

## Frontend Pages

| Path | Page | Description |
|------|------|-------------|
| `/` | JobGrid | Public job gallery |
| `/jobs/:id` | JobDetail | Job details + real-time log |
| `/console` | Console | Authenticated upload interface |

## Quick Start

### Development Environment

```bash
# 1. Start MongoDB
./scripts/start_mongodb.sh

# 2. Initialize API Key
PYTHONPATH=. python scripts/seed_api_key.py test-key-12345 test@example.com

# 3. Start Backend
./scripts/start_backend.sh

# 4. Start Worker
./scripts/start_worker.sh

# 5. Start Frontend (Dev Server)
cd frontend && npm run dev
```

**Access Points:**
- API: http://127.0.0.1:8002
- Frontend: http://localhost:5173

### Production Environment

#### Option 1: Using Docker Compose (Recommended)

```bash
# Build and start all services (including frontend build)
./scripts/start_backend_prod.sh

# Or manually
docker-compose -f docker-compose.prod.yml up -d --build
```

**Access Point:**
- Unified entry: http://localhost:8002 (Frontend + API)

#### Option 2: Local Deployment

```bash
# 1. Build frontend
cd frontend
VITE_API_BASE=/api npm run build

# 2. Start backend (automatically serves frontend)
./scripts/start_backend.sh

# 3. Start Worker
./scripts/start_worker.sh
```

**Access Point:**
- Unified entry: http://127.0.0.1:8002 (Frontend + API)

## Configuration

See `.env` file for all configuration options including MongoDB URI, CLI paths, and feature flags.

## Project Structure

```
astrometry.net_web_server/
├── api/                 # FastAPI backend
│   ├── main.py          # Application entry (includes static file serving)
│   ├── routes/
│   │   ├── legacy.py    # Original API compatibility
│   │   └── frontend.py  # Public frontend API
├── services/            # Business logic
│   ├── solver_bridge.py # CLI integration
│   ├── state_manager.py # File system state
│   └── annotator/       # Image annotation
├── workers/             # Background processing
├── frontend/            # React application
│   ├── src/
│   │   ├── pages/       # JobGrid, JobDetail
│   │   └── hooks/       # useJobList, useJobDetail
│   └── dist/            # Build artifacts (production)
├── domain/              # Data models
├── scripts/             # Utility scripts
│   └── start_backend_prod.sh  # Production startup script
├── Dockerfile           # Multi-stage build (includes frontend build)
├── docker-compose.prod.yml  # Production configuration
└── docs/                # Documentation
```

**Production Build Notes:**
- `Dockerfile` uses multi-stage build:
  1. `base` stage: Build Python backend
  2. `frontend-builder` stage: Build frontend (with `VITE_API_BASE=/api`)
  3. Final stage: Merge backend and frontend build artifacts into `frontend/dist`
- Backend container includes `frontend/dist`, FastAPI automatically serves static files

## Unsupported Features

The following original features are not implemented:
- SDSS/GALEX image overlay
- KMZ generation (requires wcs2kml)
- Multi-tenant user management
- Social login

These endpoints return friendly error messages.
