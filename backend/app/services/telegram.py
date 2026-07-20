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


# ── Roles ─────────────────────────────────────────────────────────────────
# Two kinds of chat talk to this bot, and they get disjoint capabilities.
#
#   MANAGER  — a configured chat id. Runs the CRM: lead queries, notes,
#              accept/reject, and conversation with the assistant.
#   PROSPECT — anyone else. May be interviewed by the intake flow, and may
#              never read or mutate CRM state.
#
# The webhook secret only proves an update came from Telegram; it says nothing
# about who sent it. Anyone can DM a public bot, so the role decides everything.
MANAGER = "manager"
PROSPECT = "prospect"


def authorized_chat_ids(db: Session, workspace_id: int) -> set[str]:
    """Chat ids treated as managers."""
    candidates = {
        runtime_settings.get(db, "telegram_chat_id", workspace_id),
        get_settings().telegram_chat_id,
    }
    return {str(c).strip() for c in candidates if str(c).strip()}


def chat_role(db: Session, chat_id, workspace_id: int) -> str:
    """Resolve a chat to MANAGER or PROSPECT.

    Deliberately has no third "blocked" state: a stranger is a potential lead,
    not an intruder. What protects the CRM is that PROSPECT is never granted a
    managerial capability — not that the stranger is turned away at the door.
    """
    allowed = authorized_chat_ids(db, workspace_id)
    # An unconfigured integration has no manager. Everyone is a prospect, so a
    # misconfigured deploy cannot hand CRM control to whoever messages first.
    if allowed and str(chat_id) in allowed:
        return MANAGER
    return PROSPECT


def is_manager(db: Session, chat_id, workspace_id: int) -> bool:
    return chat_role(db, chat_id, workspace_id) == MANAGER


# Kept as the single gate every managerial capability must pass through, so a
# new command cannot accidentally skip the check.
def _is_authorized(db: Session, chat_id, workspace_id: int) -> bool:
    return is_manager(db, chat_id, workspace_id)


# ── Webhook handling (manager actions) ────────────────────────────────────
BOT_COMMANDS = [
    {"command": "start", "description": "Check that the bot is connected"},
    {"command": "help", "description": "List available commands"},
    {"command": "leads", "description": "Recent leads (optionally by status)"},
    {"command": "lead", "description": "Lead detail: /lead <id>"},
    {"command": "stats", "description": "Pipeline summary"},
    {"command": "setstatus", "description": "Move a lead: /setstatus <id> <status>"},
    {"command": "note", "description": "Add a note: /note <lead_id> <text>"},
    {"command": "status", "description": "Show integration status"},
]

# Shown to any chat that is not a configured manager. Deliberately says nothing
# about lead data or the managerial commands: a stranger should not be able to
# map the CRM surface by messaging the bot.
PROSPECT_WELCOME = (
    "👋 <b>Hi, I'm Nora</b> — the intake assistant.\n\n"
    "I help collect project details so the team can get back to you quickly.\n\n"
    "Project enquiries through this chat are coming soon. In the meantime, "
    "please use the contact form on the website and I'll pick it up from there."
)

HELP_TEXT = (
    "🤖 <b>Nora AI — lead assistant</b>\n\n"
    "You receive a card for every new lead, with inline actions:\n"
    "✅ Accept · ❌ Reject · 📞 Call · 🔗 Open in CRM\n\n"
    "<b>Leads</b>\n"
    "/leads — 10 most recent\n"
    "/leads &lt;status&gt; — filter, e.g. <code>/leads Qualified</code>\n"
    "/lead &lt;id&gt; — full detail with actions\n"
    "/stats — pipeline summary\n"
    "/setstatus &lt;id&gt; &lt;status&gt; — e.g. <code>/setstatus 12 Converted</code>\n"
    "/note &lt;id&gt; &lt;text&gt; — e.g. <code>/note 12 Very promising</code>\n\n"
    "<b>Bot</b>\n"
    "/start · /help · /status — connection and integration state"
)


async def handle_update(db: Session, update: dict, workspace_id: int = DEFAULT_WORKSPACE_ID) -> dict:
    callback = update.get("callback_query")
    if callback:
        chat_id = ((callback.get("message") or {}).get("chat") or {}).get("id")
        # Callbacks only ever come from a lead card, and only managers are sent
        # one — so a callback from a prospect is always illegitimate.
        if not is_manager(db, chat_id, workspace_id):
            logger.warning("Telegram callback from non-manager chat %s ignored", chat_id)
            await _answer_callback(callback, "This bot is not configured for your account.")
            return {"ok": False, "error": "unauthorized"}
        return await _handle_callback(db, callback)

    message = update.get("message") or {}
    text = (message.get("text") or "").strip()
    chat_id = (message.get("chat") or {}).get("id")
    if not text:
        return {"ok": True}

    # Strip the @botname suffix Telegram appends in groups (/help@my_bot).
    command = text.split(maxsplit=1)[0].split("@", 1)[0].lower() if text.startswith("/") else ""

    if chat_role(db, chat_id, workspace_id) == MANAGER:
        return await _handle_manager(db, message, text, command, chat_id, workspace_id)
    return await _handle_prospect(db, message, text, command, chat_id, workspace_id)


async def _handle_manager(db, message, text, command, chat_id, workspace_id) -> dict:
    """Full CRM capability. Every branch here is manager-only by construction:
    `handle_update` is the sole caller and it checks the role first."""
    if command == "/start":
        return await _reply(chat_id, "✅ Connected. " + HELP_TEXT)
    if command == "/help":
        return await _reply(chat_id, HELP_TEXT)
    if command == "/status":
        return await _reply(chat_id, _status_text(db, workspace_id))
    if command == "/note":
        return await _handle_note(db, message, text)
    if command == "/leads":
        return await _handle_leads(db, text, chat_id, workspace_id)
    if command == "/lead":
        return await _handle_lead_detail(db, text, chat_id, workspace_id)
    if command == "/stats":
        return await _handle_stats(db, chat_id, workspace_id)
    if command == "/setstatus":
        return await _handle_set_status(db, message, text, chat_id, workspace_id)
    if command:
        return await _reply(chat_id, f"Unknown command {html.escape(command)}.\n\n{HELP_TEXT}")
    # Free text becomes an assistant conversation in a later change. Until then
    # say so, rather than ignoring the manager silently.
    return await _reply(chat_id, "I only understand commands for now.\n\n" + HELP_TEXT)


# ── Lead commands (manager only) ──────────────────────────────────────────
def _fmt_budget(budget) -> str:
    return f"${budget:,.0f}" if budget else "—"


def _lead_line(lead) -> str:
    """One compact row: id, score, project, status."""
    name = lead.project_name or lead.client_name or "Untitled"
    return (
        f"<code>#{lead.id}</code> ⭐{lead.score:>3} · {html.escape(name[:38])}\n"
        f"     {html.escape(lead.status)} · {_fmt_budget(lead.budget)}"
    )


async def _handle_leads(db: Session, text: str, chat_id, workspace_id: int) -> dict:
    from sqlalchemy import select

    from app.models import Lead

    parts = text.split(maxsplit=1)
    wanted = parts[1].strip() if len(parts) > 1 else ""

    # Workspace scoping is the tenancy invariant, not an optimisation: without
    # it this command would read every tenant's leads.
    query = select(Lead).where(Lead.workspace_id == workspace_id)
    if wanted:
        statuses = runtime_settings.pipeline_statuses(db, workspace_id)
        match = next((s for s in statuses if s.lower() == wanted.lower()), None)
        if match is None:
            return await _reply(
                chat_id,
                f"Unknown status {html.escape(wanted)!r}.\nTry: {html.escape(', '.join(statuses))}",
            )
        query = query.where(Lead.status == match)

    leads = db.scalars(query.order_by(Lead.id.desc()).limit(10)).all()
    if not leads:
        scope = f" with status {html.escape(wanted)}" if wanted else ""
        return await _reply(chat_id, f"No leads{scope} yet.")

    header = f"<b>Recent leads{' · ' + html.escape(wanted) if wanted else ''}</b>"
    body = "\n".join(_lead_line(lead) for lead in leads)
    return await _reply(chat_id, f"{header}\n\n{body}\n\nUse /lead &lt;id&gt; for detail.")


def _parse_lead_id(text: str) -> int | None:
    parts = text.split()
    if len(parts) < 2 or not parts[1].lstrip("#").isdigit():
        return None
    return int(parts[1].lstrip("#"))


def _load_lead(db: Session, lead_id: int, workspace_id: int):
    """Scoped fetch. Returns None for another tenant's lead, so a manager
    cannot read across workspaces by guessing ids."""
    from app.models import Lead

    lead = db.get(Lead, lead_id)
    if lead is None or lead.workspace_id != workspace_id:
        return None
    return lead


async def _handle_lead_detail(db: Session, text: str, chat_id, workspace_id: int) -> dict:
    lead_id = _parse_lead_id(text)
    if lead_id is None:
        return await _reply(chat_id, "Usage: <code>/lead &lt;id&gt;</code>, e.g. <code>/lead 12</code>")

    lead = _load_lead(db, lead_id, workspace_id)
    if lead is None:
        return await _reply(chat_id, f"Lead #{lead_id} not found.")

    lines = [
        f"<b>Lead #{lead.id}</b> · ⭐ {lead.score}/100 · {html.escape(lead.priority)}",
        f"📌 {html.escape(lead.project_name or '—')}",
        f"🛠 {html.escape(lead.service or '—')}",
        f"💰 {_fmt_budget(lead.budget)}   ⏱ {html.escape(lead.timeline or '—')}",
        f"📊 {html.escape(lead.status)}",
        "",
        f"👤 {html.escape(lead.client_name or 'Anonymous')}",
        f"✉️ {html.escape(lead.client_email or '—')}",
        f"📞 {html.escape(lead.client_phone or '—')}",
    ]
    if lead.summary:
        # Telegram caps a message at 4096 characters; truncate the free-text
        # field rather than have the whole send rejected.
        lines += ["", "📝 " + html.escape(lead.summary[:700])]

    from app.services.notifications import lead_link

    return await _reply_with_keyboard(chat_id, "\n".join(lines), lead_keyboard(lead.id, lead_link(lead.id)))


async def _handle_stats(db: Session, chat_id, workspace_id: int) -> dict:
    from app.services import analytics

    data = analytics.summary(db, days=30, workspace_id=workspace_id)
    by_status = data.get("leads_by_status") or {}
    lines = [
        "<b>Pipeline · last 30 days</b>",
        "",
        f"Leads          {data.get('total_leads', 0)}",
        f"Conversations  {data.get('total_conversations', 0)}",
        f"Completion     {data.get('completion_rate', 0):.0f}%",
        f"Conversion     {data.get('conversion_rate', 0):.0f}%",
        f"Avg budget     {_fmt_budget(data.get('average_budget'))}",
        f"Avg score      {data.get('average_score', 0):.0f}/100",
    ]
    if by_status:
        lines += ["", "<b>By status</b>"]
        lines += [f"{html.escape(k):<14} {v}" for k, v in by_status.items()]
    return await _reply(chat_id, "\n".join(lines))


async def _handle_set_status(db: Session, message: dict, text: str, chat_id, workspace_id: int) -> dict:
    parts = text.split(maxsplit=2)
    statuses = runtime_settings.pipeline_statuses(db, workspace_id)
    usage = (
        "Usage: <code>/setstatus &lt;id&gt; &lt;status&gt;</code>\n"
        f"Statuses: {html.escape(', '.join(statuses))}"
    )
    if len(parts) < 3 or not parts[1].lstrip("#").isdigit():
        return await _reply(chat_id, usage)

    lead = _load_lead(db, int(parts[1].lstrip("#")), workspace_id)
    if lead is None:
        return await _reply(chat_id, f"Lead #{parts[1]} not found.")

    wanted = parts[2].strip()
    match = next((s for s in statuses if s.lower() == wanted.lower()), None)
    if match is None:
        return await _reply(chat_id, f"Unknown status {html.escape(wanted)!r}.\n\n{usage}")

    old_status = lead.status
    if old_status == match:
        return await _reply(chat_id, f"Lead #{lead.id} is already {html.escape(match)}.")

    actor = (message.get("from") or {}).get("first_name", "manager")
    lead.status = match
    db.add(
        ActivityLog(
            lead_id=lead.id,
            actor=f"telegram:{actor}",
            action="status_change",
            detail=f"Status → {match} (via Telegram)",
        )
    )
    db.commit()

    # Same fan-out as a dashboard change, so the in-app feed stays consistent.
    from app.services.notifications import notify_lead_status_change

    try:
        await notify_lead_status_change(db, lead, old_status, f"telegram:{actor}")
    except Exception:
        logger.exception("Status-change fan-out failed for lead %s", lead.id)

    return await _reply(
        chat_id, f"✅ Lead #{lead.id}: {html.escape(old_status)} → <b>{html.escape(match)}</b>"
    )


async def _handle_prospect(db, message, text, command, chat_id, workspace_id) -> dict:
    """A chat that is not a configured manager.

    No branch here may read or write CRM state, and none may reveal that the
    managerial commands exist. Intake replaces this greeting in a later change;
    the invariant that must survive it is that a prospect can only ever create
    a lead describing themselves.
    """
    logger.info("Telegram message from prospect chat %s", chat_id)
    return await _reply(chat_id, PROSPECT_WELCOME)


async def _reply(chat_id, text: str) -> dict:
    if chat_id:
        await _api("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
    return {"ok": True}


async def _reply_with_keyboard(chat_id, text: str, keyboard: dict) -> dict:
    if chat_id:
        await _api(
            "sendMessage",
            {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "reply_markup": keyboard},
        )
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
