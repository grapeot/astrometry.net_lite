# Astrometry.net Lite - System Design

## Overview

Astrometry.net Lite is a simplified, maintainable reimplementation of the astrometry.net plate-solving service. It uses FastAPI + React with MongoDB for persistence, calling the Homebrew-installed Astrometry CLI tools directly.

**Key Design Principles:**
- Protocol-compatible with the original astrometry.net API
- Single-tenant deployment (one logical user, multiple API keys)
- MongoDB as the single data store (replacing SQLite)
- File system for job artifacts and real-time progress tracking

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (React)                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  JobGrid    │  │ JobDetail   │  │  Console (Auth)     │  │
│  │  (public)   │  │ (public)    │  │  (upload/manage)    │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└────────────────────────────┬────────────────────────────────┘
                             │ HTTP
┌────────────────────────────▼────────────────────────────────┐
│                    FastAPI Backend                           │
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

## Technology Stack

| Component | Technology |
|-----------|------------|
| Backend | FastAPI + Uvicorn |
| Database | MongoDB 7+ (Motor async driver) |
| Queue | MongoDB-backed (queue_messages collection) |
| Solver | Astrometry.net CLI (Homebrew) |
| Frontend | React + Vite + TypeScript |
| Image Processing | Pillow, Astropy |

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
  jobs: [1, 2, 3],  // job_id references
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

**queue_messages**
```javascript
{
  _id: ObjectId,
  job_id: 123,
  payload: { submission_id, stored_path, upload_args },
  locked_at: null,  // distributed lock timestamp
  completed_at: null,
  failed_at: null,
  attempts: 0,
  failure_reason: null
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

The system uses a hybrid approach for state management:

1. **MongoDB (Authoritative)**: Final job status (queued, solving, success, failure)
2. **File System (Progress)**: Processing stage, real-time logs, recovery info

### State Flow

```
MongoDB Status:    queued ──► solving ──► success
                                │
                                └──────► failure

File System Stage: started ──► solving ──► calibrating ──► annotating ──► completed
                      │           │            │              │
                      └───────────┴────────────┴──────────────┴──────► failed
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

### Recovery Mechanism

On worker startup:
1. Query MongoDB for jobs with `status=solving` and `finished_at=null`
2. Check file system `status.json` for each job
3. Reset incomplete jobs to `queued` for reprocessing

## API Endpoints

### Legacy API (Authentication Required)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/login` | POST | API key authentication |
| `/api/upload` | POST | File upload |
| `/api/url_upload` | POST | URL upload |
| `/api/submissions/{id}` | GET/POST | Submission status |
| `/api/submissions/{id}/jobs` | GET/POST | Submission jobs |
| `/api/jobs/{id}` | GET/POST | Job status |
| `/api/jobs/{id}/calibration` | GET/POST | Calibration data |
| `/api/jobs/{id}/info` | GET/POST | Full job info |
| `/api/jobs/{id}/objects_in_field` | GET/POST | Detected objects |
| `/api/jobs/{id}/annotations` | GET/POST | Annotations |
| `/api/myjobs/` | GET/POST | User's jobs |
| `/api/jobs_by_tag` | GET/POST | Search by tag |

### Frontend API (Public)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/jobs/list` | GET | Paginated job list |
| `/api/jobs/{id}/detail` | GET | Full job details |
| `/api/jobs/{id}/log` | GET | Real-time log (incremental) |
| `/api/files/original/{id}` | GET | Original uploaded image |

### File Downloads (No /api prefix)

| Endpoint | Description |
|----------|-------------|
| `/wcs_file/{id}` | WCS FITS file |
| `/new_fits_file/{id}/` | Solved FITS file |
| `/corr_file/{id}` | Correlation data |
| `/kml_file/{id}/` | KML/KMZ (disabled by default) |
| `/annotated_display/{id}` | Annotated image |

## Frontend Pages

### Public Pages (No Authentication)

1. **Job Gallery** (`/`)
   - Grid display of all jobs
   - Status badges (queued/solving/success/failure)
   - Click to view details

2. **Job Detail** (`/jobs/:id`)
   - Full job information
   - Real-time log streaming (10s polling)
   - Calibration data and downloads
   - Objects in field

### Authenticated Pages

3. **Console** (`/console`)
   - API key login
   - File upload
   - Job management

## Worker Processing Flow

```python
async def process_job(job_id, payload):
    state = StateManager(job_dir)

    # 1. Initialize
    state.update_stage("started", "Preparing...")

    # 2. Run solve-field (stream logs)
    state.update_stage("solving", "Running solve-field...")
    proc = subprocess.Popen(["solve-field", ...])
    for line in proc.stdout:
        state.append_log(line)

    # 3. Extract calibration
    state.update_stage("calibrating", "Extracting calibration...")
    calibration = parse_wcs(wcs_path)

    # 4. Generate annotation
    state.update_stage("annotating", "Generating annotated image...")
    annotated = generate_annotation(source, wcs, catalogs)

    # 5. Complete
    state.update_stage("completed", "Done")
    update_mongodb(job_id, status="success", results=calibration)
```

## Configuration

### Environment Variables (.env)

```bash
# MongoDB
MONGODB_URI=mongodb://localhost:27017
MONGODB_DBNAME=astrometry_dev

# API Server
API_HOST=127.0.0.1
API_PORT=8002

# File Paths
DATA_ROOT=./data
JOB_OUTPUT_DIR=./data/jobs
UPLOAD_CACHE_DIR=./data/uploads
ASTROMETRY_INDEX_DIR=./astrometry_indexes
CATALOGS_DIR=./catalogs

# CLI Binaries (Homebrew defaults)
SOLVE_FIELD_BIN=/opt/homebrew/bin/solve-field
AUGMENT_XYLIST_BIN=/opt/homebrew/bin/augment-xylist
ASTROMETRY_ENGINE_BIN=/opt/homebrew/bin/astrometry-engine

# Features
ENABLE_KMZ=false
QUEUE_VISIBILITY_TIMEOUT_SECONDS=300

# Frontend
FRONTEND_ORIGIN=http://localhost:5173
FRONTEND_PORT=5173
```

## Quick Start

### 1. Start MongoDB
```bash
./scripts/start_mongodb.sh
```

### 2. Initialize API Key
```bash
PYTHONPATH=. python scripts/seed_api_key.py test-key-12345 test@example.com
```

### 3. Start Backend
```bash
./scripts/start_backend.sh
# or: uvicorn api.main:app --reload --host 127.0.0.1 --port 8002
```

### 4. Start Worker
```bash
./scripts/start_worker.sh
```

### 5. Start Frontend
```bash
cd frontend && npm run dev
```

### Access Points
- **API**: http://127.0.0.1:8002
- **Frontend Gallery**: http://localhost:5173
- **Frontend Console**: http://localhost:5173/console

## Annotated Image Generation

The system generates annotated images using:
- **Data Source**: `catalogs/catalogs.csv` (unified catalog)
- **Process**:
  1. Load WCS from solved FITS
  2. Calculate field of view
  3. Filter objects within FOV from catalog
  4. Deduplicate and prioritize objects
  5. Render labels with optimized layout

### Catalog Format (catalogs.csv)
```csv
name,ra,dec,type,catalog
M31,10.6847,41.2687,Galaxy,Messier
NGC 224,10.6847,41.2687,Galaxy,NGC
...
```

## Unsupported Features

The following features from the original astrometry.net are not implemented:
- SDSS image overlay (`/api/sdss_image_for_wcs`)
- GALEX image overlay (`/api/galex_image_for_wcs`)
- KMZ generation (requires `wcs2kml`, disabled by default)
- Multi-tenant user management
- Social login / Django admin

These endpoints return friendly error messages explaining they are not supported.

## Project Structure

```
astrometry.net_web_server/
├── api/
│   ├── main.py              # FastAPI app
│   ├── deps.py              # Dependency injection
│   └── routes/
│       ├── legacy.py        # Original API compatibility
│       ├── frontend.py      # Public frontend API
│       └── admin.py         # Health check
├── services/
│   ├── jobs.py              # Job CRUD
│   ├── submissions.py       # Submission handling
│   ├── queue.py             # MongoDB queue
│   ├── solver_bridge.py     # CLI integration
│   ├── state_manager.py     # File system state
│   └── annotator/           # Image annotation
│       ├── catalog.py
│       ├── label_layout.py
│       └── renderer.py
├── workers/
│   └── run_worker.py        # Queue worker
├── domain/
│   ├── models.py            # Pydantic models
│   └── enums.py             # Status enums
├── frontend/
│   └── src/
│       ├── pages/           # JobGrid, JobDetail
│       ├── components/      # JobCard, LogViewer
│       └── hooks/           # useJobList, useJobDetail
├── core/
│   └── config.py            # Settings
├── scripts/                 # Startup scripts
├── catalogs/                # Star catalogs
└── astrometry_indexes/      # Index files
```
