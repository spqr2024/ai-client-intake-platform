"""Email architecture.

- `EmailProvider` abstraction (SMTP + console implemented; add SendGrid/SES
  by subclassing and extending `get_email_provider` — nothing else changes).
- Branded HTML template with automatic plain-text alternative.
- Delivery goes through the background queue (`notify.deliver` task) with
  retry + backoff; every send is logged as a Notification row (channel=email)
  whose status tracks pending → sent/failed with attempt counts.
"""

import asyncio
import html as html_lib
import logging
import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Lead
from app.services import runtime_settings

logger = logging.getLogger(__name__)


class EmailProvider(ABC):
    name: str = ""

    @abstractmethod
    def send(self, to: str, subject: str, text_body: str, html_body: str, sender: str) -> None:
        """Deliver one message. Raise on failure (the queue retries)."""


class ConsoleEmailProvider(EmailProvider):
    """Development fallback: logs the email instead of sending."""

    name = "console"

    def send(self, to: str, subject: str, text_body: str, html_body: str, sender: str) -> None:
        logger.info("EMAIL (console) from=%s to=%s subject=%r\n%s", sender, to, subject, text_body)


class SMTPEmailProvider(EmailProvider):
    name = "smtp"

    def send(self, to: str, subject: str, text_body: str, html_body: str, sender: str) -> None:
        settings = get_settings()
        msg = EmailMessage()
        msg["From"] = sender
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype="html")
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            if settings.smtp_tls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)


def get_email_provider() -> EmailProvider:
    return SMTPEmailProvider() if get_settings().smtp_host else ConsoleEmailProvider()


# ── Templating ────────────────────────────────────────────────────────────
def _render(template: str, context: dict) -> str:
    class _SafeDict(dict):
        def __missing__(self, key):  # leave unknown placeholders visible
            return "{" + key + "}"

    return template.format_map(_SafeDict(context))


HTML_LAYOUT = """\
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      <tr><td align="center" style="padding:32px 16px;">
        <table role="presentation" width="560" cellpadding="0" cellspacing="0"
               style="background:#ffffff;border-radius:12px;overflow:hidden;max-width:100%;">
          <tr><td style="background:{primary_color};padding:20px 32px;">
            <span style="color:#ffffff;font-size:18px;font-weight:bold;">{company_name}</span>
          </td></tr>
          <tr><td style="padding:32px;color:#1e293b;font-size:14px;line-height:1.7;">
            {content_html}
          </td></tr>
          <tr><td style="padding:16px 32px;background:#f8fafc;color:#94a3b8;font-size:12px;">
            Sent by {company_name} · powered by AI Client Intake Platform
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>
"""


def render_html(text_body: str, company_name: str, primary_color: str) -> str:
    paragraphs = html_lib.escape(text_body).replace("\n", "<br/>")
    return HTML_LAYOUT.format(
        content_html=paragraphs,
        company_name=html_lib.escape(company_name or "IntakeAI"),
        primary_color=primary_color or "#4f46e5",
    )


def build_message(
    db: Session, workspace_id: int, template_key_prefix: str, context: dict
) -> tuple[str, str, str]:
    """Render (subject, text, html) from workspace templates + branding."""
    brand = runtime_settings.branding(db, workspace_id)
    context = {**context, "company_name": brand["brand_company_name"]}
    subject = _render(runtime_settings.get(db, f"{template_key_prefix}_subject", workspace_id), context)
    text_body = _render(runtime_settings.get(db, f"{template_key_prefix}_body", workspace_id), context)
    html_body = render_html(text_body, brand["brand_company_name"], brand["brand_primary_color"])
    return subject, text_body, html_body


def lead_context(lead: Lead) -> dict:
    return {
        "client_name": lead.client_name or "there",
        "client_email": lead.client_email,
        "project_name": lead.project_name,
        "service": lead.service,
        "budget": f"${lead.budget:,.0f}" if lead.budget else "—",
        "timeline": lead.timeline or "—",
        "score": lead.score,
        "summary": lead.summary,
        "status": lead.status,
    }


async def send_raw(to: str, subject: str, text_body: str, html_body: str) -> None:
    """Direct provider send (used by the queue worker). Raises on failure."""
    provider = get_email_provider()
    sender = get_settings().smtp_from
    await asyncio.to_thread(provider.send, to, subject, text_body, html_body, sender)
