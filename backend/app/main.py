import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
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
from app.core.security import hash_password
from app.db import Base, SessionLocal, engine
from app.models import User
from app.services import chat as chat_service
from app.services import notifications as _notifications  # noqa: F401 — registers queue handlers

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
)
logger = logging.getLogger("app")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cache-Control": "no-store",
}


def bootstrap(db) -> None:
    """First-run setup: default admin account and default workflow."""
    settings = get_settings()
    if len(settings.jwt_secret) < 32:
        logger.warning(
            "JWT_SECRET is shorter than 32 bytes — generate a strong secret for production"
        )
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
        except Exception:  # noqa: BLE001
            logger.exception("Stale-conversation reaper failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_migrate.migrate(engine)
    Base.metadata.create_all(bind=engine)
    db_migrate.post_create(engine)
    db = SessionLocal()
    try:
        bootstrap(db)
    finally:
        db.close()
    background = [
        asyncio.create_task(_stale_conversation_reaper()),
        asyncio.create_task(queue.worker_loop()),
    ]
    yield
    for task in background:
        task.cancel()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="2.0.0",
        description="Multi-tenant conversational AI client intake and lead qualification platform.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response

    for router in (
        health.router, auth.router, users.router, chat.router, leads.router,
        workflows.router, kb.router, analytics.router, settings_api.router,
        telegram.router, public.router, prompts_api.router,
        notifications_api.router, audit_api.router,
    ):
        app.include_router(router)
    return app


app = create_app()
