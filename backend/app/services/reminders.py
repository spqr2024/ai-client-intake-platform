"""Scheduled nudges: the daily digest and follow-up reminders.

Both are idempotent by construction rather than by scheduling precision. The
loop that drives them wakes on a coarse interval and can run after a restart or
a missed window, so "have I already sent this?" is answered from persisted
state — a delivered reminder is recorded on the lead, and the digest checks the
notification log for one already sent today. Nothing here relies on the process
having been alive at a particular moment.
"""

import html
import logging
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import DEFAULT_WORKSPACE_ID, Lead, Notification, utcnow
from app.services import telegram as telegram_service

logger = logging.getLogger(__name__)

DIGEST_EVENT = "digest.daily"
REMINDER_EVENT = "lead.follow_up"

# Leads a digest will name individually before switching to a count.
_DIGEST_LIST_LIMIT = 8


def _fmt_budget(budget) -> str:
    return f"${budget:,.0f}" if budget else "—"


async def _send(db: Session, workspace_id: int, event: str, text: str, keyboard: dict | None = None) -> bool:
    """Deliver to the manager chat and record it in the delivery log.

    Written to the log even on failure: the log is what makes the digest
    idempotent, and a failed send that is not recorded would be retried on
    every tick of the loop.
    """
    chat_id = telegram_service.workspace_chat_id(db, workspace_id)
    if not chat_id or not telegram_service.enabled(db, workspace_id):
        return False

    notification = Notification(
        workspace_id=workspace_id,
        channel="telegram",
        event=event,
        title=event,
        body=text[:2000],
        recipient=str(chat_id)[:255],
        attempts=1,
    )
    try:
        await telegram_service.send_message(str(chat_id), text, keyboard)
        notification.status = "sent"
        delivered = True
    except telegram_service.TelegramError as exc:
        notification.status = "failed"
        notification.error = str(exc)[:1000]
        logger.error("Failed to deliver %s: %s", event, exc)
        delivered = False

    db.add(notification)
    db.commit()
    return delivered


# ── Follow-up reminders ───────────────────────────────────────────────────
def due_follow_ups(db: Session, workspace_id: int = DEFAULT_WORKSPACE_ID) -> list[Lead]:
    """Leads whose follow-up time has passed and that were never reminded."""
    return list(
        db.scalars(
            select(Lead)
            .where(
                Lead.workspace_id == workspace_id,
                Lead.follow_up_at.is_not(None),
                Lead.follow_up_at <= utcnow(),
                Lead.follow_up_notified_at.is_(None),
            )
            .order_by(Lead.follow_up_at)
            .limit(20)  # a backlog must not produce a burst of messages
        ).all()
    )


async def send_follow_up_reminders(db: Session, workspace_id: int = DEFAULT_WORKSPACE_ID) -> int:
    sent = 0
    for lead in due_follow_ups(db, workspace_id):
        name = lead.project_name or lead.client_name or f"Lead #{lead.id}"
        c_emoji, c_label, c_value = telegram_service.contact_display(lead)
        text = (
            f"⏰ <b>Follow-up due</b>\n"
            f"<code>#{lead.id}</code> {html.escape(name[:60])}\n"
            f"{html.escape(lead.status)} · {_fmt_budget(lead.budget)} · ⭐ {lead.score}/100\n"
            f"👤 {html.escape(lead.client_name or 'Anonymous')}\n"
            f"{c_emoji} {html.escape(c_label)}: {html.escape(c_value)}"
        )
        from app.services.notifications import lead_link

        delivered = await _send(
            db,
            workspace_id,
            REMINDER_EVENT,
            text,
            telegram_service.lead_keyboard(lead.id, lead_link(lead.id)),
        )
        if not delivered:
            # Leave the lead unmarked so the next tick retries it, rather than
            # silently dropping a reminder the operator is relying on.
            continue
        lead.follow_up_notified_at = utcnow()
        db.commit()
        sent += 1
    return sent


# ── Daily digest ──────────────────────────────────────────────────────────
def digest_already_sent_today(db: Session, workspace_id: int = DEFAULT_WORKSPACE_ID) -> bool:
    since = utcnow() - timedelta(hours=20)
    return (
        db.scalars(
            select(Notification).where(
                Notification.workspace_id == workspace_id,
                Notification.event == DIGEST_EVENT,
                Notification.created_at >= since,
            )
        ).first()
        is not None
    )


def build_digest(db: Session, workspace_id: int = DEFAULT_WORKSPACE_ID) -> str | None:
    """The last 24 hours. Returns None when there is nothing worth sending —
    a digest that arrives every day saying "0 leads" trains you to ignore it."""
    since = utcnow() - timedelta(hours=24)
    leads = list(
        db.scalars(
            select(Lead)
            .where(Lead.workspace_id == workspace_id, Lead.created_at >= since)
            .order_by(Lead.score.desc())
        ).all()
    )
    pending = db.scalar(
        select(func.count(Lead.id)).where(
            Lead.workspace_id == workspace_id,
            Lead.follow_up_at.is_not(None),
            Lead.follow_up_at <= utcnow() + timedelta(days=1),
            Lead.follow_up_notified_at.is_(None),
        )
    )
    if not leads and not pending:
        return None

    lines = [f"📊 <b>Daily digest</b> · {len(leads)} new lead(s) in 24h"]
    if leads:
        qualified = sum(1 for lead in leads if lead.status == "Qualified")
        best = leads[0]
        lines.append(f"Qualified: {qualified} · Top score: ⭐ {best.score}/100")
        lines.append("")
        for lead in leads[:_DIGEST_LIST_LIMIT]:
            name = lead.project_name or lead.client_name or "Untitled"
            lines.append(
                f"<code>#{lead.id}</code> ⭐{lead.score:>3} {html.escape(name[:34])}"
                f" · {_fmt_budget(lead.budget)}"
            )
        if len(leads) > _DIGEST_LIST_LIMIT:
            lines.append(f"…and {len(leads) - _DIGEST_LIST_LIMIT} more")
    if pending:
        lines += ["", f"⏰ {pending} follow-up(s) due within 24h"]
    lines += ["", "Use /leads or /lead &lt;id&gt; for detail."]
    return "\n".join(lines)


async def send_daily_digest(
    db: Session, workspace_id: int = DEFAULT_WORKSPACE_ID, force: bool = False
) -> bool:
    if not force and digest_already_sent_today(db, workspace_id):
        return False
    text = build_digest(db, workspace_id)
    if text is None:
        logger.debug("Nothing to report; skipping the daily digest")
        return False
    return await _send(db, workspace_id, DIGEST_EVENT, text)
