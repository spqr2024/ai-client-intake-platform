"""Workspace-scoped key/value runtime settings (editable from the admin UI,
no redeploy needed). Values fall back to sensible defaults / .env config."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DEFAULT_WORKSPACE_ID, AppSetting

DEFAULTS: dict[str, str] = {
    # ── AI ────────────────────────────────────────────────────────────
    "system_prompt": (
        "You are an intelligent intake assistant. Your job is to collect project "
        "details from a new client. Ask one question at a time, using friendly "
        "language. If the client is unclear, ask for clarification. At the end, "
        "confirm all gathered info. Be polite, helpful, and precise."
    ),
    "summary_prompt": (
        "Summarize the project details from this conversation into a structured "
        "report. Include: Project name, Client name, Contact info, Services needed, "
        "Budget, Timeline, and any other key notes. Format it as bullet points."
    ),
    "ai_provider": "",
    "ai_model": "",
    "ai_temperature": "",
    "ai_max_tokens": "",
    # ── Notifications ─────────────────────────────────────────────────
    "telegram_enabled": "true",
    "telegram_chat_id": "",  # per-workspace override of the env default
    "email_enabled": "true",
    "client_email_subject": "Thank you — we received your request",
    "client_email_body": (
        "Hi {client_name},\n\nThank you for reaching out! We received your request "
        "and our team will get back to you shortly.\n\nHere is a summary of what "
        "we discussed:\n\n{summary}\n\nBest regards,\n{company_name}"
    ),
    "staff_email_subject": "New lead: {project_name}",
    "staff_email_body": (
        "A new lead just arrived.\n\nProject: {project_name}\nClient: {client_name} "
        "({client_email})\nBudget: {budget}\nTimeline: {timeline}\nScore: {score}/100"
        "\n\nSummary:\n{summary}"
    ),
    "staff_notification_email": "",
    # ── CRM ───────────────────────────────────────────────────────────
    "qualified_score_threshold": "40",
    "pipeline_statuses": "New,Qualified,In Progress,Converted,Rejected,Closed,Incomplete",
    # ── CRM export integration (provider registry: services/crm.py) ───
    "crm_provider": "",  # "" = disabled | hubspot | pipedrive | notion | salesforce | webhook
    "crm_api_key": "",
    "crm_export_on": "qualified",  # qualified | all | off
    "crm_option_company_domain": "",  # Pipedrive
    "crm_option_database_id": "",  # Notion
    "crm_option_instance_url": "",  # Salesforce
    "crm_option_url": "",  # Generic webhook
    # ── White label / branding ────────────────────────────────────────
    "brand_company_name": "IntakeAI",
    "brand_bot_name": "AI Intake Assistant",
    "brand_logo_url": "",
    "brand_primary_color": "#4f46e5",
    "brand_domain": "",
    "landing_hero_title": "",
    "landing_hero_subtitle": "",
}

EDITABLE_KEYS = set(DEFAULTS)

# Key prefixes that accept dynamic names. The CRM provider registry is
# extensible at runtime (a new adapter declares its own `option_keys`), so the
# settings whitelist cannot be a fixed list without re-coupling the two.
DYNAMIC_KEY_PREFIXES = ("crm_option_",)


def is_editable(key: str) -> bool:
    return key in EDITABLE_KEYS or key.startswith(DYNAMIC_KEY_PREFIXES)


BRANDING_KEYS = (
    "brand_company_name",
    "brand_bot_name",
    "brand_logo_url",
    "brand_primary_color",
    "brand_domain",
    "landing_hero_title",
    "landing_hero_subtitle",
)


def get_all(db: Session, workspace_id: int = DEFAULT_WORKSPACE_ID) -> dict[str, str]:
    stored = {
        s.key: s.value
        for s in db.scalars(select(AppSetting).where(AppSetting.workspace_id == workspace_id)).all()
    }
    values = {key: stored.get(key, default) for key, default in DEFAULTS.items()}
    # Surface dynamically-named keys (e.g. a new CRM adapter's options).
    values.update({key: value for key, value in stored.items() if key.startswith(DYNAMIC_KEY_PREFIXES)})
    return values


def get(db: Session, key: str, workspace_id: int = DEFAULT_WORKSPACE_ID) -> str:
    setting = db.scalars(
        select(AppSetting).where(AppSetting.workspace_id == workspace_id, AppSetting.key == key)
    ).first()
    if setting is not None and setting.value != "":
        return setting.value
    return DEFAULTS.get(key, "")


def set_many(db: Session, values: dict[str, str], workspace_id: int = DEFAULT_WORKSPACE_ID) -> dict[str, str]:
    for key, value in values.items():
        if not is_editable(key):
            continue
        setting = db.scalars(
            select(AppSetting).where(AppSetting.workspace_id == workspace_id, AppSetting.key == key)
        ).first()
        if setting is None:
            db.add(AppSetting(workspace_id=workspace_id, key=key, value=value))
        else:
            setting.value = value
    db.commit()
    return get_all(db, workspace_id)


def llm_overrides(db: Session, workspace_id: int = DEFAULT_WORKSPACE_ID) -> dict[str, str]:
    return {
        "ai_provider": get(db, "ai_provider", workspace_id),
        "ai_model": get(db, "ai_model", workspace_id),
        "ai_temperature": get(db, "ai_temperature", workspace_id),
        "ai_max_tokens": get(db, "ai_max_tokens", workspace_id),
    }


def branding(db: Session, workspace_id: int = DEFAULT_WORKSPACE_ID) -> dict[str, str]:
    return {key: get(db, key, workspace_id) for key in BRANDING_KEYS}


def pipeline_statuses(db: Session, workspace_id: int = DEFAULT_WORKSPACE_ID) -> list[str]:
    raw = get(db, "pipeline_statuses", workspace_id)
    statuses = [s.strip() for s in raw.split(",") if s.strip()]
    return statuses or ["New", "Qualified", "In Progress", "Converted", "Rejected", "Closed", "Incomplete"]
