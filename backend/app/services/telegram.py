"""Telegram integration.

Outbound messages are dispatched via the notification center (queue-backed
retry with exponential backoff, per-message delivery log). This module owns
the Bot API transport, message/keyboard construction (inline actions +
deep links into the CRM), and the secured webhook handling for manager
actions (Accept / Reject / Call, /note command).
"""

import html
import logging
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import DEFAULT_WORKSPACE_ID, ActivityLog, Lead
from app.services import runtime_settings

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"


class TelegramError(Exception):
    pass


def enabled(db: Session, workspace_id: int) -> bool:
    settings = get_settings()
    return (
        bool(settings.telegram_bot_token)
        and runtime_settings.get(db, "telegram_enabled", workspace_id).lower() != "false"
    )


def workspace_chat_id(db: Session, workspace_id: int) -> str:
    """Per-workspace chat id with .env fallback."""
    return runtime_settings.get(db, "telegram_chat_id", workspace_id) or get_settings().telegram_chat_id


# ── Transport ─────────────────────────────────────────────────────────────
async def _api(method: str, payload: dict, raise_on_error: bool = False) -> dict | None:
    """Call the Bot API.

    Errors are reported using Telegram's own `description` field rather than
    the bare HTTP status. The status alone is close to useless for diagnosis —
    "403 Forbidden" hides "the bot can't send messages to the bot", which is
    the difference between a misconfigured chat id and a revoked token.
    """
    settings = get_settings()
    if not settings.telegram_bot_token:
        if raise_on_error:
            raise TelegramError("TELEGRAM_BOT_TOKEN is not configured")
        return None
    url = f"{API_BASE}/bot{settings.telegram_bot_token}/{method}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload)
    except httpx.HTTPError as exc:
        # Transport-level: DNS, TLS, timeout. No response body to mine.
        logger.error("Telegram API %s failed: %s", method, exc)
        if raise_on_error:
            raise TelegramError(f"{method}: {exc}") from exc
        return None

    try:
        body = resp.json()
    except ValueError:
        body = {}

    # Telegram signals logical failure with ok:false. That can arrive with a
    # 4xx *or*, for some methods, a 200 — so trust `ok`, not the status code.
    if resp.is_success and body.get("ok"):
        return body

    description = body.get("description") or resp.text[:200] or f"HTTP {resp.status_code}"
    detail = f"{method}: {description} (HTTP {resp.status_code})"
    logger.error("Telegram API %s", detail)
    if raise_on_error:
        raise TelegramError(detail)
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


def is_valid_button_url(url: str) -> bool:
    """Whether Telegram will accept `url` on an inline keyboard button.

    Telegram rejects hosts it cannot resolve publicly — localhost, bare IPs and
    single-label names all come back as "Wrong HTTP URL". It rejects the *whole*
    sendMessage call, not just the offending button, so an unreachable
    PUBLIC_APP_URL silently costs you the entire lead card: the Accept / Reject /
    Call actions disappear along with the link. Checked here so a development
    default degrades to a card without the CRM link instead of no card at all.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    if host in ("localhost", "127.0.0.1", "::1") or host.endswith(".localhost"):
        return False
    # A public host is either dotted (example.com) or an explicit IP; a bare
    # label like "backend" only resolves inside a container network.
    return "." in host


def lead_keyboard(lead_id: int, deep_link: str = "") -> dict:
    rows = [
        [
            {"text": "✅ Accept", "callback_data": f"accept:{lead_id}"},
            {"text": "❌ Reject", "callback_data": f"reject:{lead_id}"},
            {"text": "📞 Call", "callback_data": f"call:{lead_id}"},
        ]
    ]
    if deep_link:
        if is_valid_button_url(deep_link):
            rows.append([{"text": "🔗 Open in CRM", "url": deep_link}])
        else:
            logger.warning(
                "Omitting the 'Open in CRM' button: PUBLIC_APP_URL (%s) is not a "
                "publicly resolvable http(s) URL, and Telegram would reject the "
                "whole message. Set PUBLIC_APP_URL to the deployed dashboard URL.",
                deep_link,
            )
    return {"inline_keyboard": rows}


# ── Authorization ─────────────────────────────────────────────────────────
def authorized_chat_ids(db: Session, workspace_id: int) -> set[str]:
    """Chats allowed to drive the CRM over Telegram.

    The webhook secret proves an update came from *Telegram*, not that it came
    from *our manager* — anyone who finds @the_bot can DM it. Without this the
    `/note` and Accept/Reject handlers are world-writable to any Telegram user.
    """
    candidates = {
        runtime_settings.get(db, "telegram_chat_id", workspace_id),
        get_settings().telegram_chat_id,
    }
    return {str(c).strip() for c in candidates if str(c).strip()}


def _is_authorized(db: Session, chat_id, workspace_id: int) -> bool:
    allowed = authorized_chat_ids(db, workspace_id)
    # No configured chat means the integration is not set up. Deny rather than
    # fall open — an empty allowlist must not mean "allow everyone".
    return bool(allowed) and str(chat_id) in allowed


# ── Webhook handling (manager actions) ────────────────────────────────────
BOT_COMMANDS = [
    {"command": "start", "description": "Check that the bot is connected"},
    {"command": "help", "description": "List available commands"},
    {"command": "status", "description": "Show integration status"},
    {"command": "note", "description": "Add a note: /note <lead_id> <text>"},
]

HELP_TEXT = (
    "🤖 <b>Nora AI — lead assistant</b>\n\n"
    "You receive a card for every new lead, with inline actions:\n"
    "✅ Accept · ❌ Reject · 📞 Call · 🔗 Open in CRM\n\n"
    "<b>Commands</b>\n"
    "/start — check the bot is connected\n"
    "/help — this message\n"
    "/status — show integration status\n"
    "/note &lt;lead_id&gt; &lt;text&gt; — attach a note to a lead\n"
    "   e.g. <code>/note 12 Very promising client</code>"
)


async def handle_update(db: Session, update: dict, workspace_id: int = DEFAULT_WORKSPACE_ID) -> dict:
    callback = update.get("callback_query")
    if callback:
        chat_id = ((callback.get("message") or {}).get("chat") or {}).get("id")
        if not _is_authorized(db, chat_id, workspace_id):
            logger.warning("Telegram callback from unauthorized chat %s ignored", chat_id)
            await _answer_callback(callback, "This bot is not configured for your account.")
            return {"ok": False, "error": "unauthorized"}
        return await _handle_callback(db, callback)

    message = update.get("message") or {}
    text = (message.get("text") or "").strip()
    chat_id = (message.get("chat") or {}).get("id")
    if not text:
        return {"ok": True}

    if not _is_authorized(db, chat_id, workspace_id):
        logger.warning("Telegram message from unauthorized chat %s ignored", chat_id)
        if chat_id:
            # Tell them plainly instead of staying silent, but leak nothing
            # about the CRM. The chat id is what an operator needs to add them.
            await _api(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": (
                        "This bot is private and handles lead notifications for its "
                        f"operator only.\nYour chat id is {chat_id}."
                    ),
                },
            )
        return {"ok": False, "error": "unauthorized"}

    # Strip the @botname suffix Telegram appends in groups (/help@my_bot).
    command = text.split(maxsplit=1)[0].split("@", 1)[0].lower()

    if command == "/start":
        return await _reply(chat_id, "✅ Connected. " + HELP_TEXT)
    if command == "/help":
        return await _reply(chat_id, HELP_TEXT)
    if command == "/status":
        return await _reply(chat_id, _status_text(db, workspace_id))
    if command == "/note":
        return await _handle_note(db, message, text)
    if command.startswith("/"):
        return await _reply(chat_id, f"Unknown command {html.escape(command)}.\n\n{HELP_TEXT}")
    return {"ok": True}


async def _reply(chat_id, text: str) -> dict:
    if chat_id:
        await _api("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
    return {"ok": True}


def _status_text(db: Session, workspace_id: int) -> str:
    settings = get_settings()
    chat_id = workspace_chat_id(db, workspace_id)
    lines = [
        "<b>Integration status</b>",
        f"Bot token: {'configured' if settings.telegram_bot_token else '❌ missing'}",
        f"Notification chat: {html.escape(chat_id) if chat_id else '❌ not set'}",
        f"Webhook secret: {'configured' if settings.telegram_webhook_secret else '❌ missing'}",
        f"Notifications: {'on' if enabled(db, workspace_id) else 'off'}",
    ]
    return "\n".join(lines)


async def register_commands() -> bool:
    """Publish the command list so Telegram shows a menu in the UI."""
    result = await _api("setMyCommands", {"commands": BOT_COMMANDS})
    return bool(result)


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
        db.add(
            ActivityLog(
                lead_id=lead.id,
                actor=f"telegram:{actor}",
                action="status_change",
                detail=f"Status → {lead.status} (via Telegram)",
            )
        )
    else:
        db.add(
            ActivityLog(
                lead_id=lead.id,
                actor=f"telegram:{actor}",
                action="call_requested",
                detail="Contact info requested via Telegram",
            )
        )
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
