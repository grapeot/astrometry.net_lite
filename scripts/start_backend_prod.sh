#!/bin/sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Load environment variables if .env exists
if [ -f "$PROJECT_ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$PROJECT_ROOT/.env"
  set +a
fi

COMPOSE_FILE="$PROJECT_ROOT/docker-compose.prod.yml"

echo "=========================================="
echo "Starting Astrometry Lite Production"
echo "=========================================="
echo ""
echo "Usage: $0 [--no-cache]"
echo "  --no-cache  Force rebuild without cache"
echo ""

# Check if docker-compose is available
if ! command -v docker-compose >/dev/null 2>&1 && ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker-compose or docker is not installed"
  exit 1
fi

# Use docker compose (newer) or docker-compose (older)
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD="docker-compose"
else
  echo "Error: docker compose is not available"
  exit 1
fi

# Build and start services
# Use --no-cache if NO_CACHE environment variable is set, or if --no-cache flag is passed
NO_CACHE_FLAG=""
if [ "${NO_CACHE:-0}" = "1" ] || [ "${1:-}" = "--no-cache" ]; then
  NO_CACHE_FLAG="--no-cache"
  echo "Building Docker images (without cache)..."
else
  echo "Building Docker images..."
fi

if [ -n "$NO_CACHE_FLAG" ]; then
  $COMPOSE_CMD -f "$COMPOSE_FILE" build --no-cache
else
  $COMPOSE_CMD -f "$COMPOSE_FILE" build
fi

echo ""
echo "Starting services..."
$COMPOSE_CMD -f "$COMPOSE_FILE" up -d

echo ""
echo "=========================================="
echo "Services started successfully!"
echo "=========================================="
echo ""
echo "Backend API: http://localhost:8002"
echo "Frontend:    http://localhost:8002"
echo ""
echo "To view logs:"
echo "  $COMPOSE_CMD -f $COMPOSE_FILE logs -f"
echo ""
echo "To stop services:"
echo "  $COMPOSE_CMD -f $COMPOSE_FILE down"
echo ""

