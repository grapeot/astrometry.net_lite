FROM python:3.12-slim AS base
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    UV_SYSTEM_PYTHON=1

# Install system dependencies and astrometry.net CLI tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    astrometry.net \
    astrometry-data-tycho2 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# List installed astrometry tools for debugging
RUN echo "Checking installed astrometry tools:" && \
    dpkg -L astrometry.net | grep -E 'bin/|/usr/bin/' || true && \
    ls -la /usr/bin/*astrometry* /usr/bin/*solve* /usr/bin/*augment* 2>/dev/null || true

# Verify astrometry.net tools are installed and accessible
# Note: Debian/Ubuntu package includes solve-field and astrometry-engine,
# but not augment-xylist as a separate binary (it's part of solve-field)
RUN solve-field --help > /dev/null 2>&1 || (echo "ERROR: solve-field not found after installation" && exit 1) && \
    astrometry-engine --help > /dev/null 2>&1 || (echo "ERROR: astrometry-engine not found after installation" && exit 1) && \
    echo "✓ astrometry.net tools verified" && \
    echo "Installed tools:" && \
    which solve-field astrometry-engine && \
    echo "Note: augment-xylist functionality is available via solve-field --just-augment"

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    export PATH="/root/.local/bin:$PATH" && \
    uv --version
ENV PATH="/root/.local/bin:$PATH"

# Install Python dependencies
COPY pyproject.toml README.md ./
RUN python <<EOF > requirements.txt
from pathlib import Path
from tomllib import load
data = load(Path('pyproject.toml').open('rb'))
deps = data['project']['dependencies']
print('\n'.join(deps))
EOF
RUN uv pip install --system --no-cache -r requirements.txt

# astrometry.net CLI tools are installed via apt-get above

# Copy application code
COPY api ./api
COPY core ./core
COPY domain ./domain
COPY services ./services
COPY workers ./workers
COPY docs ./docs
COPY scripts ./scripts

# Build frontend (multi-stage build)
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ .
# Build with relative API path for backend serving
ARG VITE_API_BASE=/api
ENV VITE_API_BASE=${VITE_API_BASE:-/api}
RUN npm run build

# Final stage: combine backend and frontend
FROM base
# Copy frontend build to backend
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Set default astrometry.net binary paths (can be overridden via environment variables)
# These binaries are installed via apt-get in /usr/bin/
ENV SOLVE_FIELD_BIN=/usr/bin/solve-field \
    AUGMENT_XYLIST_BIN=/usr/bin/augment-xylist \
    ASTROMETRY_ENGINE_BIN=/usr/bin/astrometry-engine

EXPOSE 8000
ENV API_PORT=8000
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${API_PORT:-8000}"]
