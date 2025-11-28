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

LOG_DIR="$PROJECT_ROOT/logs"
LOG_FILE="$LOG_DIR/worker.log"
PID_FILE="$LOG_DIR/worker.pid"
mkdir -p "$LOG_DIR"

if [ -f "$PID_FILE" ]; then
  PID=$(cat "$PID_FILE")
  if kill -0 "$PID" 2>/dev/null; then
    echo "Worker already running with PID $PID (PID file $PID_FILE)."
    echo "Kill it manually (e.g. \"kill $PID\") before restarting."
    exit 1
  else
    echo "Stale PID file found, removing."
    rm -f "$PID_FILE"
  fi
fi

echo "Starting worker (logs → $LOG_FILE)"
# Use python from venv if available, otherwise use system python3
PYTHON_CMD="python3"
if [ -d "$PROJECT_ROOT/venv" ]; then
  PYTHON_CMD="$PROJECT_ROOT/venv/bin/python"
fi

nohup "$PYTHON_CMD" -m workers.run_worker >>"$LOG_FILE" 2>&1 &
PID=$!
echo $PID > "$PID_FILE"
echo "Worker PID $PID recorded in $PID_FILE"
