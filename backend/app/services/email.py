"""Transactional email. Uses SMTP when configured; otherwise logs the email
to the console so local development works without a mail server."""

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ActivityLog, Lead
from app.services import runtime_settings

logger = logging.getLogger(__name__)


def _render(template: str, context: dict) -> str:
    class _SafeDict(dict):
        def __missing__(self, key):  # leave unknown placeholders visible
            return "{" + key + "}"

    return template.format_map(_SafeDict(context))


def _send_sync(to: str, subject: str, body: str) -> bool:
    settings = get_settings()
    if not settings.smtp_host:
        logger.info("EMAIL (console fallback) to=%s subject=%r\n%s", to, subject, body)
        return True
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            if settings.smtp_tls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError) as exc:
        logger.error("SMTP send failed: %s", exc)
        return False


async def send(to: str, subject: str, body: str) -> bool:
    return await asyncio.to_thread(_send_sync, to, subject, body)


def _lead_context(lead: Lead) -> dict:
    return {
        "client_name": lead.client_name or "there",
        "client_email": lead.client_email,
        "project_name": lead.project_name,
        "service": lead.service,
        "budget": f"${lead.budget:,.0f}" if lead.budget else "—",
        "timeline": lead.timeline or "—",
        "score": lead.score,
        "summary": lead.summary,
    }


async def send_lead_emails(db: Session, lead: Lead) -> None:
    """Client confirmation + staff notification for a new lead."""
    if runtime_settings.get(db, "email_enabled").lower() == "false":
        return
    context = _lead_context(lead)

    if lead.client_email:
        sent = await send(
            lead.client_email,
            _render(runtime_settings.get(db, "client_email_subject"), context),
            _render(runtime_settings.get(db, "client_email_body"), context),
        )
        if sent:
            db.add(ActivityLog(lead_id=lead.id, actor="system", action="email_sent",
                               detail=f"Confirmation email sent to {lead.client_email}"))

    staff_email = runtime_settings.get(db, "staff_notification_email")
    if staff_email:
        await send(
            staff_email,
            _render(runtime_settings.get(db, "staff_email_subject"), context),
            _render(runtime_settings.get(db, "staff_email_body"), context),
        )
    db.commit()
