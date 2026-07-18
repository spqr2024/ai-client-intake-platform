"""Operational endpoints: liveness, readiness, metrics.

Liveness answers "is the process alive?" (cheap, no dependencies) — an
orchestrator restarts the container when it fails. Readiness answers "should
traffic be routed here?" and probes dependencies — a failing readiness check
removes the instance from the load balancer without killing it. Conflating
the two causes restart storms when a shared dependency blips, which is why
they are separate here.
"""

import time

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.cache import get_cache
from app.core.config import get_settings
from app.core.observability import metrics
from app.db import get_db

router = APIRouter(tags=["operations"])

_STARTED_AT = time.time()
APP_VERSION = "2.1.0"


def _check_database(db: Session) -> dict:
    started = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
        return {"ok": True, "latency_ms": round((time.perf_counter() - started) * 1000, 2)}
    except Exception as exc:  # noqa: BLE001 — probe must never raise
        return {"ok": False, "error": str(exc)[:200]}


def _check_cache() -> dict:
    settings = get_settings()
    backend = "redis" if settings.redis_url else "memory"
    started = time.perf_counter()
    try:
        cache = get_cache()
        cache.set("health:probe", 1, ttl_seconds=5)
        ok = cache.get("health:probe") == 1
        return {
            "ok": ok,
            "backend": type(cache).__name__.replace("Cache", "").lower(),
            "configured": backend,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "configured": backend, "error": str(exc)[:200]}


@router.get("/health")
def health(db: Session = Depends(get_db)):
    """Backwards-compatible aggregate health check."""
    database = _check_database(db)
    return {"status": "ok" if database["ok"] else "degraded", "database": database["ok"]}


@router.get("/health/live")
def liveness():
    """Process liveness — intentionally dependency-free."""
    return {
        "status": "alive",
        "version": APP_VERSION,
        "uptime_seconds": round(time.time() - _STARTED_AT, 1),
    }


@router.get("/health/ready")
def readiness(response: Response, db: Session = Depends(get_db)):
    """Dependency readiness. Returns 503 when a hard dependency is down so
    orchestrators stop routing traffic here."""
    checks = {"database": _check_database(db), "cache": _check_cache()}
    # The cache degrades gracefully to in-memory, so only the database is hard.
    ready = checks["database"]["ok"]
    if not ready:
        response.status_code = 503
    return {
        "status": "ready" if ready else "not_ready",
        "version": APP_VERSION,
        "uptime_seconds": round(time.time() - _STARTED_AT, 1),
        "checks": checks,
    }


@router.get("/metrics")
def prometheus_metrics():
    """Prometheus text exposition. Scrape directly; Grafana dashboards can be
    built on top without the application depending on either system."""
    metrics.gauge("app_uptime_seconds", round(time.time() - _STARTED_AT, 1),
                  help_text="Seconds since process start")
    return Response(content=metrics.render_prometheus(), media_type="text/plain; version=0.0.4")


@router.get("/metrics/json")
def json_metrics():
    """Human/JSON-friendly view of the same registry (used by tests and ops UIs)."""
    return metrics.snapshot()
