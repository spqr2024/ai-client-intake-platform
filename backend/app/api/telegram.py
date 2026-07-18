from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_db
from app.services import telegram as telegram_service

router = APIRouter(prefix="/api/webhook", tags=["telegram"])


@router.post("/telegram")
async def telegram_webhook(request: Request, db: Session = Depends(get_db)):
    """Telegram webhook endpoint. Protected by the X-Telegram-Bot-Api-Secret-Token
    header (set via setWebhook secret_token) when TELEGRAM_WEBHOOK_SECRET is set."""
    settings = get_settings()
    if settings.telegram_webhook_secret:
        header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if header != settings.telegram_webhook_secret:
            raise HTTPException(status_code=403, detail="Invalid webhook secret")
    update = await request.json()
    return await telegram_service.handle_update(db, update)
