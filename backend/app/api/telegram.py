import logging
import secrets as secrets_lib

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.rate_limit import rate_limit
from app.db import get_db
from app.services import telegram as telegram_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhook", tags=["telegram"])


@router.post("/telegram", dependencies=[Depends(rate_limit)])
async def telegram_webhook(request: Request, db: Session = Depends(get_db)):
    """Telegram webhook endpoint, authenticated by the secret token Telegram
    echoes back in `X-Telegram-Bot-Api-Secret-Token` (registered via setWebhook).

    Fails **closed**: an unset `TELEGRAM_WEBHOOK_SECRET` rejects every request
    rather than disabling the check. Updates handled here mutate lead state —
    accept/reject, status changes, internal notes — so an unauthenticated caller
    who can reach this route can drive the CRM. Skipping validation when the
    secret is missing would make a misconfigured deploy silently world-writable,
    which is the opposite of what a missing credential should do.
    """
    settings = get_settings()
    expected = settings.telegram_webhook_secret

    if not expected:
        logger.warning(
            "Telegram webhook rejected: TELEGRAM_WEBHOOK_SECRET is not configured. "
            "Set it and register it with setWebhook(secret_token=...) to enable the endpoint."
        )
        raise HTTPException(status_code=403, detail="Webhook is not configured")

    provided = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    # Constant-time: a plain != leaks the shared secret one byte at a time to an
    # attacker who can measure response latency across many requests.
    if not secrets_lib.compare_digest(provided, expected):
        logger.warning("Telegram webhook rejected: invalid secret token")
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    update = await request.json()
    return await telegram_service.handle_update(db, update)
