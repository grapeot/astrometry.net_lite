#!/bin/sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

if [ -d "$PROJECT_ROOT/venv" ]; then
  # shellcheck disable=SC1091
  . "$PROJECT_ROOT/venv/bin/activate"
fi

if [ -f "$PROJECT_ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$PROJECT_ROOT/.env"
  set +a
fi

HOST="${API_HOST:-127.0.0.1}"
PORT="${API_PORT:-8002}"
LOG_DIR="$PROJECT_ROOT/logs"
LOG_FILE="$LOG_DIR/backend.log"

mkdir -p "$LOG_DIR"

echo "Starting backend on ${HOST}:${PORT} (logs → $LOG_FILE)"
exec uvicorn api.main:app --reload --host "$HOST" --port "$PORT" >>"$LOG_FILE" 2>&1
