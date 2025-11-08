#!/bin/sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT/frontend"

if [ -d "$PROJECT_ROOT/venv" ]; then
  # Optional: activate Python env so frontend .env can reuse tooling
  # shellcheck disable=SC1091
  . "$PROJECT_ROOT/venv/bin/activate" >/dev/null 2>&1 || true
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required to run the frontend dev server" >&2
  exit 1
fi

echo "Starting Vite dev server (uses VITE_API_BASE from frontend/.env.development if present)"
exec npm run dev
