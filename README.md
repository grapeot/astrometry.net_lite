# Astrometry.net Lite

FastAPI + MongoDB rewrite of the legacy astrometry.net web service. The goal is API compatibility with `net/client/client.py` while slimming the stack to a manageable FastAPI backend plus a React frontend.

## Prerequisites
- Python 3.12+
- MongoDB 7+ (local or Atlas). Dev scripts assume `mongodb://localhost:27017` and the `scripts/start_mongodb.sh` helper.
- Astrometry.net CLI via Homebrew (`solve-field`, `augment-xylist`, `astrometry-engine`).
- Pre-downloaded index files under `./astrometry_indexes/` (already checked into your workspace but ignored by git).

## Quickstart

### Initial Setup

1. Ensure the uv-managed virtualenv exists and is activated:
   ```bash
   source venv/bin/activate
   ```

2. Install backend dependencies (recorded in `pyproject.toml`):
   ```bash
   uv pip install -r <(python - <<'PY'
from pathlib import Path
from tomllib import load
py = Path('pyproject.toml')
data = load(py.open('rb'))
print('\n'.join(data['project']['dependencies'] + data['project']['optional-dependencies']['dev']))
PY
)
   ```
   > Already installed in this repo snapshot.

3. Copy `.env.example` → `.env` (already prepared) or edit `.env` with Mongo URI, CLI paths, and directories.

4. Seed an API key (once per environment):
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

```bash
cd frontend
npm install    # already done once
npm run dev    # launches http://localhost:5173
# Or use the unified script (automatically enters frontend directory)
../scripts/start_frontend.sh
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

### Docker (experimental)

```bash
docker build -t astrometry-lite .
docker run --rm -p 8000:8000 --env-file .env \
  -v "$PWD/data:/app/data" \
  -v "$PWD/astrometry_indexes:/app/astrometry_indexes" \
  astrometry-lite
```

> The Docker image requires astrometry.net CLI binaries. You can add them to the Dockerfile or mount host paths.
> KML/KMZ generation is disabled by default because the Homebrew version doesn't include `wcs2kml`. To enable KMZ, manually install the tool and add `--kmz` parameter when executing the CLI.

### Using the Legacy Python Client

Point the legacy Python client at `http://localhost:8002/api/`.

## Project Layout
```
api/            # FastAPI entrypoint + routes
core/           # Pydantic settings
services/       # Mongo/data/queue/solver services
workers/        # CLI worker loop
frontend/       # React app (pending)
docs/           # Plans + working log
scripts/        # Mongo helpers, etc.
```

## Outstanding Work
See `docs/working_log.md` for a live checklist covering:
- Mongo-backed queue lifecycle
- Legacy API coverage & gaps (`sdss_image_for_wcs`, KDE overlays, KML export, annotated PNGs)
- Frontend implementation milestones
- Docker packaging and CI/test coverage

Contributions should update the working log plus this README when behaviour changes.
