FROM python:3.12-slim AS base
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    UV_SYSTEM_PYTHON=1

# Install system dependencies for astrometry.net CLI and Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    wget \
    git \
    swig \
    python3-dev \
    libcfitsio-dev \
    libwcs-dev \
    libnetpbm10-dev \
    libcairo2-dev \
    libpng-dev \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv

# Install Python dependencies
COPY pyproject.toml README.md ./
RUN python - <<'PY' > requirements.txt \
from pathlib import Path; from tomllib import load\n\
data = load(Path('pyproject.toml').open('rb'))\n\
deps = data['project']['dependencies']\n\
print('\n'.join(deps))\n\
PY
RUN uv pip install --system --no-cache -r requirements.txt

# Install astrometry.net CLI tools from source
# This is optional - you can also mount binaries from host using volume mounts
# For faster builds, comment out this section and mount host binaries instead
# Note: Building from source can take 10-20 minutes and requires significant disk space
RUN mkdir -p /tmp/astrometry && cd /tmp/astrometry && \
    wget -q https://github.com/dstndstn/astrometry.net/releases/download/0.95/astrometry.net-0.95.tar.gz -O astrometry.tar.gz && \
    tar -xzf astrometry.tar.gz && \
    cd astrometry.net-0.95 && \
    make -j$(nproc) && \
    make install INSTALL_DIR=/usr/local && \
    cd / && rm -rf /tmp/astrometry

# Copy application code
COPY api ./api
COPY core ./core
COPY domain ./domain
COPY services ./services
COPY workers ./workers
COPY docs ./docs
COPY scripts ./scripts

# Set default astrometry.net binary paths (can be overridden via environment variables)
ENV SOLVE_FIELD_BIN=/usr/local/bin/solve-field \
    AUGMENT_XYLIST_BIN=/usr/local/bin/augment-xylist \
    ASTROMETRY_ENGINE_BIN=/usr/local/bin/astrometry-engine

EXPOSE 8002
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8002"]
