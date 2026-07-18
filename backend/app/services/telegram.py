"""Telegram bot integration: new-lead notifications with inline action
buttons, and webhook callback handling (Accept / Reject / Call, /note)."""

import html
import logging

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ActivityLog, Lead
from app.services import runtime_settings

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"


def _enabled(db: Session) -> bool:
    settings = get_settings()
    return bool(settings.telegram_bot_token) and runtime_settings.get(
        db, "telegram_enabled"
    ).lower() != "false"


async def _api(method: str, payload: dict) -> dict | None:
    settings = get_settings()
    url = f"{API_BASE}/bot{settings.telegram_bot_token}/{method}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:
        logger.error("Telegram API %s failed: %s", method, exc)
        return None


async def notify_new_lead(db: Session, lead: Lead) -> None:
    if not _enabled(db):
        logger.info("Telegram disabled — skipping notification for lead %s", lead.id)
        return
    settings = get_settings()
    budget = f"${lead.budget:,.0f}" if lead.budget else "—"
    text = (
        f"🔥 <b>New Lead Received!</b>\n"
        f"📌 Service: {html.escape(lead.service or '—')}\n"
        f"💰 Budget: {html.escape(budget)}\n"
        f"⏱ Timeline: {html.escape(lead.timeline or '—')}\n"
        f"👤 Contact: {html.escape(lead.client_name or 'Anonymous')}"
        f" ({html.escape(lead.client_email or 'no email')})\n"
        f"⭐ Score: {lead.score}/100"
    )
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": {
            "inline_keyboard": [
                [
                    {"text": "✅ Accept", "callback_data": f"accept:{lead.id}"},
                    {"text": "❌ Reject", "callback_data": f"reject:{lead.id}"},
                    {"text": "📞 Call", "callback_data": f"call:{lead.id}"},
                ]
            ]
        },
    }
    result = await _api("sendMessage", payload)
    if result:
        db.add(ActivityLog(lead_id=lead.id, actor="system", action="telegram",
                           detail="New-lead notification sent to Telegram"))
        db.commit()


async def handle_update(db: Session, update: dict) -> dict:
    """Process a Telegram webhook update (callback buttons and /note command)."""
    callback = update.get("callback_query")
    if callback:
        return await _handle_callback(db, callback)

    message = update.get("message") or {}
    text = (message.get("text") or "").strip()
    if text.startswith("/note"):
        return await _handle_note(db, message, text)
    return {"ok": True}


async def _handle_callback(db: Session, callback: dict) -> dict:
    data = callback.get("data", "")
    action, _, lead_id_raw = data.partition(":")
    try:
        lead_id = int(lead_id_raw)
    except ValueError:
        return {"ok": False}
    lead = db.get(Lead, lead_id)
    if lead is None:
        await _answer_callback(callback, "Lead not found.")
        return {"ok": False}

    actor = (callback.get("from") or {}).get("first_name", "manager")
    if action == "accept":
        lead.status = "In Progress"
        reply = f"✅ Lead #{lead.id} accepted — plan your next steps."
    elif action == "reject":
        lead.status = "Rejected"
        reply = f"❌ Lead #{lead.id} rejected."
    elif action == "call":
        contact = lead.client_phone or lead.client_email or "no contact info collected"
        reply = f"📞 Contact for lead #{lead.id}: {contact}"
    else:
        return {"ok": False}

    if action in ("accept", "reject"):
        db.add(ActivityLog(lead_id=lead.id, actor=f"telegram:{actor}",
                           action="status_change", detail=f"Status → {lead.status} (via Telegram)"))
    else:
        db.add(ActivityLog(lead_id=lead.id, actor=f"telegram:{actor}",
                           action="call_requested", detail="Contact info requested via Telegram"))
    db.commit()

    await _answer_callback(callback, reply)
    chat_id = ((callback.get("message") or {}).get("chat") or {}).get("id")
    if chat_id:
        await _api("sendMessage", {"chat_id": chat_id, "text": reply})
    return {"ok": True}


async def _answer_callback(callback: dict, text: str) -> None:
    if callback.get("id"):
        await _api("answerCallbackQuery", {"callback_query_id": callback["id"], "text": text[:190]})


async def _handle_note(db: Session, message: dict, text: str) -> dict:
    # Format: /note <lead_id> <text>   e.g. "/note 12 Very promising client"
    parts = text.split(maxsplit=2)
    chat_id = (message.get("chat") or {}).get("id")
    usage = "Usage: /note <lead_id> <text>"
    if len(parts) < 3 or not parts[1].isdigit():
        if chat_id:
            await _api("sendMessage", {"chat_id": chat_id, "text": usage})
        return {"ok": True}
    lead = db.get(Lead, int(parts[1]))
    if lead is None:
        if chat_id:
            await _api("sendMessage", {"chat_id": chat_id, "text": f"Lead #{parts[1]} not found."})
        return {"ok": True}
    actor = (message.get("from") or {}).get("first_name", "manager")
    db.add(ActivityLog(lead_id=lead.id, actor=f"telegram:{actor}", action="note", detail=parts[2]))
    db.commit()
    if chat_id:
        await _api("sendMessage", {"chat_id": chat_id, "text": f"📝 Note added to lead #{lead.id}."})
    return {"ok": True}
