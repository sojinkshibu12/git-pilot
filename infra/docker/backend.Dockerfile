# Backend image — FastAPI + uvicorn
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UVICORN_WORKERS=4

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /srv/app

COPY backend/pyproject.toml ./
COPY backend/ /srv/app/

RUN pip install --no-cache-dir . && pip install --no-cache-dir "uvicorn[standard]"

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--proxy-headers", "--forwarded-allow-ips", "*"]
