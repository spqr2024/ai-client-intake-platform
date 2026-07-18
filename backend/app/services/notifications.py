"""Notification center: one dispatch API fanning out to channels.

Channels: `inapp` (dashboard bell, always synchronous), `email` and
`telegram` (delivered through the background queue with retry/backoff and a
per-row delivery log), plus registry slots for future `slack` / `discord`
senders — registering a sender function is the only change needed to add a
channel.

Every outbound row lives in the `notifications` table, which doubles as the
delivery log (status pending → sent/failed, attempts, error).
"""

import logging
from collections.abc import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import queue
from app.core.config import get_settings
from app.db import SessionLocal
from app.models import Lead, Notification, User
from app.services import email as email_service
from app.services import runtime_settings
from app.services import telegram as telegram_service

logger = logging.getLogger(__name__)

# channel -> async sender(db, notification, payload). Raise to trigger retry.
ChannelSender = Callable[[Session, Notification, dict], Awaitable[None]]
CHANNEL_SENDERS: dict[str, ChannelSender] = {}


def register_channel(name: str, sender: ChannelSender) -> None:
    CHANNEL_SENDERS[name] = sender


def lead_link(lead_id: int) -> str:
    return f"{get_settings().public_app_url.rstrip('/')}/admin/leads/{lead_id}"


def create_inapp(
    db: Session,
    workspace_id: int,
    event: str,
    title: str,
    body: str,
    link: str = "",
    user_id: int | None = None,
) -> None:
    """In-app rows: one per targeted user, or one per workspace member."""
    if user_id is not None:
        targets = [user_id]
    else:
        targets = list(db.scalars(select(User.id).where(User.workspace_id == workspace_id)).all())
    for target in targets:
        db.add(
            Notification(
                workspace_id=workspace_id,
                user_id=target,
                channel="inapp",
                event=event,
                title=title[:255],
                body=body,
                link=link,
                status="sent",
            )
        )
    db.commit()


async def dispatch_channel(
    db: Session,
    workspace_id: int,
    channel: str,
    event: str,
    title: str,
    body: str,
    recipient: str,
    link: str = "",
    extra: dict | None = None,
) -> Notification:
    """Create a delivery-log row and enqueue the actual send."""
    notification = Notification(
        workspace_id=workspace_id,
        channel=channel,
        event=event,
        title=title[:255],
        body=body,
        link=link,
        recipient=recipient[:255],
    )
    if channel not in CHANNEL_SENDERS:
        notification.status = "skipped"
        notification.error = f"No sender registered for channel '{channel}'"
    db.add(notification)
    db.commit()
    db.refresh(notification)
    if notification.status != "skipped":
        await queue.enqueue("notify.deliver", {"notification_id": notification.id, **(extra or {})})
    return notification


# ── Queue delivery handler ────────────────────────────────────────────────
async def _deliver(payload: dict) -> None:
    db = SessionLocal()
    try:
        notification = db.get(Notification, int(payload.get("notification_id", 0)))
        if notification is None or notification.status == "sent":
            return
        sender = CHANNEL_SENDERS.get(notification.channel)
        if sender is None:
            notification.status = "skipped"
            db.commit()
            return
        notification.attempts += 1
        try:
            await sender(db, notification, payload)
            notification.status = "sent"
            notification.error = ""
            db.commit()
        except Exception as exc:
            notification.error = str(exc)[:1000]
            if notification.attempts >= queue.MAX_ATTEMPTS:
                notification.status = "failed"
            db.commit()
            raise  # let the queue retry / dead-letter
    finally:
        db.close()


queue.register_handler("notify.deliver", _deliver)


# ── Built-in channel senders ─────────────────────────────────────────────
async def _send_email(db: Session, notification: Notification, payload: dict) -> None:
    brand = runtime_settings.branding(db, notification.workspace_id)
    html_body = email_service.render_html(
        notification.body, brand["brand_company_name"], brand["brand_primary_color"]
    )
    await email_service.send_raw(notification.recipient, notification.title, notification.body, html_body)


async def _send_telegram(db: Session, notification: Notification, payload: dict) -> None:
    keyboard = None
    lead_id = payload.get("lead_id")
    if lead_id and payload.get("with_actions"):
        keyboard = telegram_service.lead_keyboard(int(lead_id), notification.link)
    await telegram_service.send_message(notification.recipient, notification.body, keyboard)


register_channel("email", _send_email)
register_channel("telegram", _send_telegram)


# ── High-level domain events ─────────────────────────────────────────────
async def notify_new_lead(db: Session, lead: Lead) -> None:
    workspace_id = lead.workspace_id
    title = f"New lead: {lead.project_name or f'#{lead.id}'}"
    link = lead_link(lead.id)
    budget = f"${lead.budget:,.0f}" if lead.budget else "—"

    create_inapp(
        db,
        workspace_id,
        "lead.created",
        title,
        f"{lead.client_name or 'Anonymous'} · {lead.service or '—'} · {budget} · score {lead.score}",
        link,
    )

    if runtime_settings.get(db, "email_enabled", workspace_id).lower() != "false":
        if lead.client_email:
            subject, text_body, _ = email_service.build_message(
                db, workspace_id, "client_email", email_service.lead_context(lead)
            )
            await dispatch_channel(
                db, workspace_id, "email", "lead.created", subject, text_body, lead.client_email, link
            )
        staff_email = runtime_settings.get(db, "staff_notification_email", workspace_id)
        if staff_email:
            subject, text_body, _ = email_service.build_message(
                db, workspace_id, "staff_email", email_service.lead_context(lead)
            )
            await dispatch_channel(
                db, workspace_id, "email", "lead.created", subject, text_body, staff_email, link
            )

    chat_id = telegram_service.workspace_chat_id(db, workspace_id)
    if chat_id and telegram_service.enabled(db, workspace_id):
        await dispatch_channel(
            db,
            workspace_id,
            "telegram",
            "lead.created",
            title,
            telegram_service.build_lead_text(lead),
            chat_id,
            link,
            extra={"lead_id": lead.id, "with_actions": True},
        )


async def notify_lead_status_change(db: Session, lead: Lead, old_status: str, actor: str) -> None:
    workspace_id = lead.workspace_id
    title = f"Lead #{lead.id}: {old_status} → {lead.status}"
    body = f"{lead.project_name or f'Lead #{lead.id}'} moved to {lead.status} by {actor}."
    link = lead_link(lead.id)

    create_inapp(db, workspace_id, "lead.status_changed", title, body, link)

    chat_id = telegram_service.workspace_chat_id(db, workspace_id)
    if chat_id and telegram_service.enabled(db, workspace_id):
        await dispatch_channel(
            db, workspace_id, "telegram", "lead.status_changed", title, f"🔁 {body}\n{link}", chat_id, link
        )
