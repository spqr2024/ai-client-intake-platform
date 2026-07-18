"""Runtime key-value settings stored in the DB (editable from the admin UI,
no redeploy needed). Values fall back to sensible defaults / .env config."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AppSetting

DEFAULTS: dict[str, str] = {
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
    "telegram_enabled": "true",
    "email_enabled": "true",
    "client_email_subject": "Thank you — we received your request",
    "client_email_body": (
        "Hi {client_name},\n\nThank you for reaching out! We received your request "
        "and our team will get back to you shortly.\n\nHere is a summary of what "
        "we discussed:\n\n{summary}\n\nBest regards,\nThe Team"
    ),
    "staff_email_subject": "New lead: {project_name}",
    "staff_email_body": (
        "A new lead just arrived.\n\nProject: {project_name}\nClient: {client_name} "
        "({client_email})\nBudget: {budget}\nTimeline: {timeline}\nScore: {score}/100"
        "\n\nSummary:\n{summary}"
    ),
    "staff_notification_email": "",
    "qualified_score_threshold": "40",
}

EDITABLE_KEYS = set(DEFAULTS)


def get_all(db: Session) -> dict[str, str]:
    stored = {s.key: s.value for s in db.scalars(select(AppSetting)).all()}
    return {key: stored.get(key, default) for key, default in DEFAULTS.items()}


def get(db: Session, key: str) -> str:
    setting = db.get(AppSetting, key)
    if setting is not None and setting.value != "":
        return setting.value
    return DEFAULTS.get(key, "")


def set_many(db: Session, values: dict[str, str]) -> dict[str, str]:
    for key, value in values.items():
        if key not in EDITABLE_KEYS:
            continue
        setting = db.get(AppSetting, key)
        if setting is None:
            db.add(AppSetting(key=key, value=value))
        else:
            setting.value = value
    db.commit()
    return get_all(db)


def llm_overrides(db: Session) -> dict[str, str]:
    return {
        "ai_provider": get(db, "ai_provider"),
        "ai_model": get(db, "ai_model"),
        "ai_temperature": get(db, "ai_temperature"),
        "ai_max_tokens": get(db, "ai_max_tokens"),
    }
