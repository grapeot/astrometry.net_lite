# Astrometry.net Lite

FastAPI + MongoDB rewrite of the legacy astrometry.net web service. The goal is API compatibility with `net/client/client.py` while slimming the stack to a manageable FastAPI backend plus a React frontend.

## Prerequisites
- Python 3.12+
- [uv](https://github.com/astral-sh/uv) - Fast Python package installer (install: `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Node.js 20+ and npm (for frontend development)
- MongoDB 7+ (local or Atlas). Dev scripts assume `mongodb://localhost:27017` and the `scripts/start_mongodb.sh` helper.
- Astrometry.net CLI via Homebrew (`solve-field`, `augment-xylist`, `astrometry-engine`).
- Pre-downloaded index files under `./astrometry_indexes/`. Download index files from https://data.astrometry.net/ and place them in `./astrometry_indexes/` before running the service.

## Quickstart

### Initial Setup

**Option 1: Automated Setup (Recommended)**

Run the setup script to automatically configure your local development environment:

```bash
./scripts/setup_local.sh
```

This script will:
- Create a Python virtual environment using `uv`
- Install all backend Python dependencies
- Install all frontend Node.js dependencies

**Option 2: Manual Setup**

1. Create and activate the virtual environment:
   ```bash
   uv venv venv
   source venv/bin/activate
   ```

2. Install backend dependencies:
   ```bash
   python <<EOF > /tmp/requirements.txt
   from pathlib import Path
   from tomllib import load
   data = load(Path('pyproject.toml').open('rb'))
   deps = data['project']['dependencies']
   dev_deps = data['project']['optional-dependencies']['dev']
   print('\n'.join(deps + dev_deps))
   EOF
   uv pip install -r /tmp/requirements.txt
   rm /tmp/requirements.txt
   ```

3. Install frontend dependencies:
   ```bash
   cd frontend
   npm install
   cd ..
   ```

4. Copy `.env.example` → `.env` (if not already present) or edit `.env` with Mongo URI, CLI paths, and directories.

5. Seed an API key (once per environment):
   ```bash
   PYTHONPATH=. python scripts/seed_api_key.py test-key-12345 test@example.com
   ```

### Running the Services

For local development, you'll typically run 4 processes simultaneously:

**Terminal 1: MongoDB**
```bash
./scripts/start_mongodb.sh
```

**Terminal 2: Backend API**
```bash
./scripts/start_backend.sh
```
> API runs at http://127.0.0.1:8002 (docs at http://127.0.0.1:8002/docs)

**Terminal 3: Worker (processes queue)**
```bash
./scripts/start_worker.sh
```
> Logs are written to `logs/worker.log`, PID is recorded in `logs/worker.pid`. To restart, first run `kill $(cat logs/worker.pid)`.

**Terminal 4: Frontend (optional)**
```bash
./scripts/start_frontend.sh
```
> Frontend runs at http://localhost:5173

### Frontend

The React dashboard lives in `frontend/` (Vite + TypeScript).

**Using the start script (recommended):**
```bash
./scripts/start_frontend.sh
```

**Or manually:**
```bash
cd frontend
npm run dev    # launches http://localhost:5173
```

Set `VITE_API_BASE` in `frontend/.env.development` if your API runs on a different host.

### Testing the Service

**Quick test (without waiting for job completion):**
```bash
python scripts/test_service.py --quick
```

**Full test (waits for job completion):**
```bash
python scripts/test_service.py --file test.jpg --apikey test-key-12345
```

### Docker Compose

The easiest way to run all services is using Docker Compose, which includes MongoDB, backend, and frontend.

**Prerequisites:**
- Docker and Docker Compose installed
- Pre-downloaded index files in `./astrometry_indexes/` (download from https://data.astrometry.net/)

#### Development Mode (Default)

**Start development services:**
```bash
docker-compose up -d
```

This will start:
- **MongoDB** on port `27017` (data persisted in `./data/mongodb/`)
- **Backend API** on port `8002` (http://localhost:8002) with hot-reload
- **Frontend** on port `5173` (http://localhost:5173) with Vite dev server

**Features:**
- Code is mounted into containers for live editing
- Hot reload enabled for both frontend and backend
- Perfect for local development

**View logs:**
```bash
docker-compose logs -f          # All services
docker-compose logs -f backend  # Backend only
docker-compose logs -f frontend # Frontend only
docker-compose logs -f mongodb # MongoDB only
```

**Stop services:**
```bash
docker-compose down
```

#### Production Mode

For production deployment, use the production configuration:

```bash
# Set API base URL for frontend build (optional)
export VITE_API_BASE=http://your-api-domain.com:8002

# Build and start production services
docker-compose -f docker-compose.prod.yml up -d --build
```

**Features:**
- Frontend built as static files, served by nginx
- Backend runs without reload flag
- No code mounting (code is baked into images)
- Optimized for production performance

**Access services:**
- Frontend: http://localhost:80 (nginx)
- Backend API: http://localhost:8002
- API Docs: http://localhost:8002/docs
- MongoDB: `mongodb://localhost:27017`

**Data persistence:**
All data is persisted in the `./data/` directory:
- MongoDB data: `./data/mongodb/`
- Job outputs: `./data/jobs/`
- Upload cache: `./data/uploads/`
- MongoDB logs: `./data/mongodb.log`

**For detailed deployment instructions, see [DEPLOYMENT.md](DEPLOYMENT.md)**

### Docker (Single Container - Experimental)

For running just the backend in a single container (requires MongoDB running separately):

**Build and run:**
```bash
docker build -t astrometry-backend .
docker run --rm -p 8002:8002 \
  -e MONGODB_URI=mongodb://host.docker.internal:27017 \
  -e MONGODB_DBNAME=astrometry_dev \
  -v "$PWD/data:/app/data" \
  -v "$PWD/astrometry_indexes:/app/astrometry_indexes" \
  astrometry-backend
```

**Alternative: Mount host binaries (faster, requires astrometry.net installed on host):**
```bash
docker build -t astrometry-backend .
docker run --rm -p 8002:8002 \
  -e MONGODB_URI=mongodb://host.docker.internal:27017 \
  -e MONGODB_DBNAME=astrometry_dev \
  -e SOLVE_FIELD_BIN=/host/bin/solve-field \
  -e AUGMENT_XYLIST_BIN=/host/bin/augment-xylist \
  -e ASTROMETRY_ENGINE_BIN=/host/bin/astrometry-engine \
  -v "/opt/homebrew/bin:/host/bin:ro" \
  -v "$PWD/data:/app/data" \
  -v "$PWD/astrometry_indexes:/app/astrometry_indexes" \
  astrometry-backend
```

> **Note:** 
> - The Dockerfile uses `uv` for Python package management, which provides faster dependency resolution and installation.
> - The Dockerfile installs astrometry.net CLI via apt-get (Debian packages), which is faster than building from source.
> - KML/KMZ generation is disabled by default. To enable KMZ, set `ENABLE_KMZ=true` and ensure `wcs2kml` is available.

### Using the Legacy Python Client

Point the legacy Python client at `http://localhost:8002/api/`.

## Project Layout
```
api/            # FastAPI entrypoint + routes
core/           # Pydantic settings
services/       # Mongo/data/queue/solver services
workers/        # CLI worker loop
frontend/       # React app
docs/           # Documentation and design notes
scripts/        # Mongo helpers, etc.
```

