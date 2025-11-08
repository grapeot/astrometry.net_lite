# Astrometry.net Lite

FastAPI + MongoDB rewrite of the legacy astrometry.net web service. The goal is API compatibility with `net/client/client.py` while slimming the stack to a manageable FastAPI backend plus a React frontend.

## Prerequisites
- Python 3.12+
- MongoDB 7+ (local or Atlas). Dev scripts assume `mongodb://localhost:27017` and the `scripts/start_mongodb.sh` helper.
- Astrometry.net CLI via Homebrew (`solve-field`, `augment-xylist`, `astrometry-engine`).
- Pre-downloaded index files under `./astrometry_indexes/` (already checked into your workspace but ignored by git).

## Quickstart
1. Ensure the uv-managed virtualenv exists and is activated:
   ```bash
   source venv/bin/activate
   ```
2. Install backend deps (recorded in `pyproject.toml`):
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
4. Start MongoDB for dev:
   ```bash
   ./scripts/start_mongodb.sh
   ```
5. Seed an API key (once per environment):
   ```bash
   PYTHONPATH=. python scripts/seed_api_key.py my-secret-key user@example.com
   ```
6. Launch the API (reads `.env` for `API_HOST`/`API_PORT`):
   ```bash
   ./scripts/start_backend.sh
   ```
7. (Optional) Run the worker in another shell to execute queued jobs:
   ```bash
   ./scripts/start_worker.sh
   ```
   > 日志写入 `logs/worker.log`，PID 记录在 `logs/worker.pid`，若需重启先 `kill $(cat logs/worker.pid)`。

> 典型本地开发会同时运行 4 个进程：MongoDB、后台 API（`start_backend.sh`）、队列 worker（`start_worker.sh`）和前端（`start_frontend.sh`）。

### Frontend

The React dashboard lives in `frontend/` (Vite + TypeScript).

```bash
cd frontend
npm install    # already done once
npm run dev    # launches http://localhost:5173
## 或使用统一脚本（会自动进入 frontend 目录）
../scripts/start_frontend.sh
```

Set `VITE_API_BASE` in `frontend/.env.development` if your API runs on a different host.

### Docker (experimental)

```
docker build -t astrometry-lite .
docker run --rm -p 8000:8000 --env-file .env \
  -v "$PWD/data:/app/data" \
  -v "$PWD/astrometry_indexes:/app/astrometry_indexes" \
  astrometry-lite
```

> 镜像内需要 astrometry.net CLI，可在 Dockerfile 中添加二进制或挂载宿主路径。
> 默认**不**生成 KML/KMZ，因为 Homebrew 版没有 `wcs2kml`。如需 KMZ，请手动安装该工具并在执行 CLI 时加上 `--kmz` 参数。
7. Use the legacy Python client pointing at `http://localhost:8000/api/`.

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
