#!/bin/sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

LOG_DIR="$PROJECT_ROOT/logs"
PID_FILE="$LOG_DIR/worker.pid"

if [ ! -f "$PID_FILE" ]; then
  echo "No PID file found at $PID_FILE"
  echo "Worker may not be running."
  exit 0
fi

PID=$(cat "$PID_FILE")

if ! kill -0 "$PID" 2>/dev/null; then
  echo "Worker process $PID is not running (stale PID file)"
  rm -f "$PID_FILE"
  exit 0
fi

echo "Stopping worker (PID: $PID)..."
kill "$PID"

# Wait for process to stop
for i in 1 2 3 4 5; do
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "Worker stopped successfully"
    rm -f "$PID_FILE"
    exit 0
  fi
  sleep 1
done

# If still running, force kill
if kill -0 "$PID" 2>/dev/null; then
  echo "Worker did not stop gracefully, forcing termination..."
  kill -9 "$PID" 2>/dev/null || true
  sleep 1
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "Worker force-stopped"
    rm -f "$PID_FILE"
  else
    echo "Warning: Failed to stop worker process $PID"
    exit 1
  fi
else
  rm -f "$PID_FILE"
fi

