FROM python:3.12-slim AS base
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    UV_SYSTEM_PYTHON=1

# Install system dependencies and astrometry.net CLI tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    astrometry.net \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Verify astrometry.net tools are installed and accessible
RUN solve-field --help > /dev/null 2>&1 || (echo "ERROR: solve-field not found after installation" && exit 1) && \
    echo "✓ astrometry.net tools verified"

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

# Set default astrometry.net binary paths (can be overridden via environment variables)
# These binaries are installed via apt-get in /usr/bin/
ENV SOLVE_FIELD_BIN=/usr/bin/solve-field \
    ASTROMETRY_ENGINE_BIN=/usr/bin/astrometry-engine

EXPOSE 8002
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8002"]
