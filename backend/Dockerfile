# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps are installed before app code so this layer stays cached.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir "psycopg[binary]>=3.1"

COPY app ./app

# Run as an unprivileged user: a container escape from the web process should
# not grant root inside the image. `uploads`/`data` are writable by that user.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/uploads /app/data \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Readiness (not liveness) is used here: the container should report unhealthy
# when its database is unreachable so orchestrators stop routing traffic.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8000/health/ready || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
