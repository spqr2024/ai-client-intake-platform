import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app import db_migrate
from app.api import (
    analytics,
    auth,
    chat,
    health,
    kb,
    leads,
    public,
    telegram,
    users,
    workflows,
)
from app.api import (
    audit as audit_api,
)
from app.api import (
    crm as crm_api,
)
from app.api import (
    notifications as notifications_api,
)
from app.api import (
    prompts as prompts_api,
)
from app.api import (
    settings as settings_api,
)
from app.core import queue
from app.core.config import get_settings
from app.core.logging import configure_logging, request_id_var, request_path_var
from app.core.observability import metrics, report_error
from app.core.security import hash_password
from app.db import Base, SessionLocal, engine
from app.models import DEFAULT_WORKSPACE_ID, User
from app.services import chat as chat_service
from app.services import crm as _crm  # noqa: F401 — registers CRM providers + queue handler
from app.services import notifications as _notifications  # noqa: F401 — registers queue handlers

configure_logging(get_settings().log_level)
logger = logging.getLogger("app")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cache-Control": "no-store",
}

# Paths excluded from access logging/metrics — probes would drown real traffic.
_QUIET_PATHS = {"/health", "/health/live", "/health/ready", "/metrics", "/metrics/json"}


def bootstrap(db) -> None:
    """First-run setup: default admin account and default workflow."""
    settings = get_settings()
    if len(settings.jwt_secret) < 32:
        logger.warning(
            "JWT_SECRET is shorter than 32 bytes — generate a strong secret for production"
        )
    if settings.jwt_secret == "change-me-in-production" and not settings.debug:
        logger.warning("JWT_SECRET is still the documented default — change it before deploying")
    if db.scalars(select(User)).first() is None:
        db.add(
            User(
                name="Admin",
                email=settings.admin_email.lower(),
                password_hash=hash_password(settings.admin_password),
                role="admin",
            )
        )
        db.commit()
        logger.info("Created default admin account: %s", settings.admin_email)
    chat_service.get_default_workflow(db)


async def _stale_conversation_reaper() -> None:
    while True:
        await asyncio.sleep(3600)
        try:
            db = SessionLocal()
            try:
                closed = await chat_service.close_stale_conversations(db)
                if closed:
                    logger.info("Closed %s stale conversations", closed)
            finally:
                db.close()
        except Exception as exc:  # noqa: BLE001
            report_error(exc, component="stale_conversation_reaper")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    db_migrate.migrate(engine)
    Base.metadata.create_all(bind=engine)
    db_migrate.post_create(engine)
    db = SessionLocal()
    try:
        bootstrap(db)
        if settings.demo_mode:
            from app.demo import provision_demo_workspace
            from app.services.kb import reindex_workspace

            if provision_demo_workspace(db):
                # Index the seeded articles so the demo KB answers questions
                # immediately instead of sitting in "pending".
                await reindex_workspace(db, DEFAULT_WORKSPACE_ID)
    finally:
        db.close()
    background = [
        asyncio.create_task(_stale_conversation_reaper()),
        asyncio.create_task(queue.worker_loop()),
    ]
    logger.info("Application started", extra={"version": health.APP_VERSION,
                                              "demo_mode": settings.demo_mode})
    yield
    for task in background:
        task.cancel()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=health.APP_VERSION,
        description="Multi-tenant conversational AI client intake and lead qualification platform.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Total-Count"],
    )

    @app.middleware("http")
    async def observability(request: Request, call_next):
        """Assigns a request id, records latency/status metrics, emits one
        structured access log line, and guarantees security headers."""
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        request_id_var.set(request_id)
        request_path_var.set(request.url.path)
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception as exc:  # noqa: BLE001 — convert to 500 + report
            report_error(exc, path=request.url.path, method=request.method,
                         request_id=request_id)
            metrics.counter("http_requests_total",
                            labels={"method": request.method, "status": "500"},
                            help_text="HTTP requests")
            response = JSONResponse(
                status_code=500,
                content={"detail": "Internal server error", "request_id": request_id},
            )
        else:
            duration = time.perf_counter() - started
            if request.url.path not in _QUIET_PATHS:
                route = request.scope.get("route")
                path_label = getattr(route, "path", request.url.path)
                metrics.counter("http_requests_total",
                                labels={"method": request.method,
                                        "status": str(response.status_code)},
                                help_text="HTTP requests")
                metrics.observe("http_request_duration_seconds", duration,
                                labels={"method": request.method, "path": path_label},
                                help_text="HTTP request latency")
                logger.info(
                    "%s %s %s", request.method, request.url.path, response.status_code,
                    extra={"method": request.method, "status": response.status_code,
                           "duration_ms": round(duration * 1000, 2)},
                )

        response.headers["X-Request-ID"] = request_id
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response

    for router in (
        health.router, auth.router, users.router, chat.router, leads.router,
        workflows.router, kb.router, analytics.router, settings_api.router,
        telegram.router, public.router, prompts_api.router,
        notifications_api.router, audit_api.router, crm_api.router,
    ):
        app.include_router(router)
    return app


app = create_app()
