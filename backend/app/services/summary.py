"""Lead summary generation: LLM-powered when a provider is configured,
with a deterministic rule-based fallback that always works offline."""

import logging

from sqlalchemy.orm import Session

from app.models import DEFAULT_WORKSPACE_ID
from app.services import llm, runtime_settings
from app.services import prompts as prompt_service

logger = logging.getLogger(__name__)

_LABELS = {
    "en": {
        "project": "Project",
        "client": "Client",
        "contact": "Contact",
        "service": "Service",
        "budget": "Budget",
        "timeline": "Timeline",
        "goals": "Goals",
        "notes": "Notes",
        "platform": "Platform",
    },
    "uk": {
        "project": "Проєкт",
        "client": "Клієнт",
        "contact": "Контакт",
        "service": "Послуга",
        "budget": "Бюджет",
        "timeline": "Термін",
        "goals": "Цілі",
        "notes": "Нотатки",
        "platform": "Платформа",
    },
}


def project_name_from(answers: dict) -> str:
    service = str(answers.get("service", "")).strip()
    client = str(answers.get("client_name", "")).strip()
    if service and client:
        return f"{service} — {client}"
    return service or (f"Inquiry from {client}" if client else "New inquiry")


def rule_based_summary(answers: dict, lang: str = "en") -> str:
    labels = _LABELS.get(lang, _LABELS["en"])
    budget = answers.get("budget")
    budget_text = f"${budget:,.0f}" if isinstance(budget, (int, float)) and budget else "—"
    contact_parts = [
        p
        for p in (answers.get("client_email"), answers.get("client_phone"), answers.get("contact_telegram"))
        if p
    ]
    lines = [
        f"- **{labels['project']}**: {project_name_from(answers)}",
        f"- **{labels['client']}**: {answers.get('client_name') or '—'}",
        f"- **{labels['contact']}**: {', '.join(contact_parts) or '—'}",
        f"- **{labels['service']}**: {answers.get('service') or '—'}",
    ]
    if answers.get("platform"):
        lines.append(f"- **{labels['platform']}**: {answers['platform']}")
    lines += [
        f"- **{labels['budget']}**: {budget_text}",
        f"- **{labels['timeline']}**: {answers.get('timeline') or '—'}",
        f"- **{labels['goals']}**: {answers.get('goals') or '—'}",
    ]
    if answers.get("extra_notes") and str(answers["extra_notes"]).lower() not in (
        "no",
        "ні",
        "no, that's all",
        "ні, це все",
    ):
        lines.append(f"- **{labels['notes']}**: {answers['extra_notes']}")
    return "\n".join(lines)


async def generate_summary(
    db: Session,
    transcript: list[dict],
    answers: dict,
    lang: str,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
    workflow_prompt_name: str = "",
) -> str:
    """Try LLM summarization; fall back to the deterministic template."""
    fallback = rule_based_summary(answers, lang)
    config = llm.resolve_config(runtime_settings.llm_overrides(db, workspace_id))
    if config.provider == "mock":
        return fallback
    prompt = prompt_service.resolve(db, workspace_id, "summary", workflow_prompt_name)
    conversation_text = "\n".join(f"{m['sender']}: {m['text']}" for m in transcript)
    try:
        result = await llm.complete(
            [{"role": "user", "content": f"{prompt}\n\nConversation:\n{conversation_text}"}],
            config=config,
        )
        return result or fallback
    except llm.LLMError:
        logger.warning("LLM summary failed, using rule-based fallback")
        return fallback
