FROM python:3.12-slim AS base
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    UV_SYSTEM_PYTHON=1

RUN pip install --no-cache-dir uv

COPY pyproject.toml README.md ./
RUN python - <<'PY' > requirements.txt \
from pathlib import Path; from tomllib import load\n\
data = load(Path('pyproject.toml').open('rb'))\n\
deps = data['project']['dependencies']\n\
print('\n'.join(deps))\n\
PY
RUN uv pip install --system --no-cache -r requirements.txt

COPY api ./api
COPY core ./core
COPY domain ./domain
COPY services ./services
COPY workers ./workers
COPY docs ./docs
COPY scripts ./scripts
COPY .env.example ./

EXPOSE 8002
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8002"]
