"""Telegram integration.

Outbound messages are dispatched via the notification center (queue-backed
retry with exponential backoff, per-message delivery log). This module owns
the Bot API transport, message/keyboard construction (inline actions +
deep links into the CRM), and the secured webhook handling for manager
actions (Accept / Reject / Call, /note command).
"""

import html
import logging

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ActivityLog, Lead
from app.services import runtime_settings

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"


class TelegramError(Exception):
    pass


def enabled(db: Session, workspace_id: int) -> bool:
    settings = get_settings()
    return bool(settings.telegram_bot_token) and runtime_settings.get(
        db, "telegram_enabled", workspace_id
    ).lower() != "false"


def workspace_chat_id(db: Session, workspace_id: int) -> str:
    """Per-workspace chat id with .env fallback."""
    return runtime_settings.get(db, "telegram_chat_id", workspace_id) or get_settings().telegram_chat_id


# ── Transport ─────────────────────────────────────────────────────────────
async def _api(method: str, payload: dict, raise_on_error: bool = False) -> dict | None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        if raise_on_error:
            raise TelegramError("TELEGRAM_BOT_TOKEN is not configured")
        return None
    url = f"{API_BASE}/bot{settings.telegram_bot_token}/{method}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:
        logger.error("Telegram API %s failed: %s", method, exc)
        if raise_on_error:
            raise TelegramError(f"{method}: {exc}") from exc
        return None


async def send_message(chat_id: str, text: str, reply_markup: dict | None = None) -> None:
    """Raises TelegramError on failure so the queue can retry."""
    payload: dict = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    await _api("sendMessage", payload, raise_on_error=True)


# ── Message construction ──────────────────────────────────────────────────
def build_lead_text(lead: Lead) -> str:
    budget = f"${lead.budget:,.0f}" if lead.budget else "—"
    return (
        f"🔥 <b>New Lead Received!</b>\n"
        f"📌 Service: {html.escape(lead.service or '—')}\n"
        f"💰 Budget: {html.escape(budget)}\n"
        f"⏱ Timeline: {html.escape(lead.timeline or '—')}\n"
        f"👤 Contact: {html.escape(lead.client_name or 'Anonymous')}"
        f" ({html.escape(lead.client_email or 'no email')})\n"
        f"⭐ Score: {lead.score}/100 · Priority: {html.escape(lead.priority)}"
    )


def lead_keyboard(lead_id: int, deep_link: str = "") -> dict:
    rows = [[
        {"text": "✅ Accept", "callback_data": f"accept:{lead_id}"},
        {"text": "❌ Reject", "callback_data": f"reject:{lead_id}"},
        {"text": "📞 Call", "callback_data": f"call:{lead_id}"},
    ]]
    if deep_link:
        rows.append([{"text": "🔗 Open in CRM", "url": deep_link}])
    return {"inline_keyboard": rows}


# ── Webhook handling (manager actions) ────────────────────────────────────
async def handle_update(db: Session, update: dict) -> dict:
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
