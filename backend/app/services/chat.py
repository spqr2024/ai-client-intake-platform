"""Chat orchestration: glues the workflow engine, KB retrieval, LLM layer,
memory, summarizer, scoring and the notification center into the
conversation lifecycle. Every message stores replay metadata (node,
event type) so managers can replay conversations step by step."""

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    DEFAULT_WORKSPACE_ID,
    ActivityLog,
    Conversation,
    Lead,
    Message,
    Workflow,
    utcnow,
)
from app.services import crm as crm_service
from app.services import kb as kb_service
from app.services import llm, runtime_settings
from app.services import memory as memory_service
from app.services import notifications as notification_service
from app.services import prompts as prompt_service
from app.services import summary as summary_service
from app.services import workflow as wf
from app.services.scoring import score_lead

logger = logging.getLogger(__name__)


@dataclass
class ChatReply:
    bot_message: str
    quick_replies: list[str] = field(default_factory=list)
    done: bool = False
    lead_id: int | None = None
    summary: str | None = None


HUMAN_KEYWORDS = (
    "talk to a person",
    "talk to a human",
    "speak to a human",
    "real person",
    "human please",
    "operator",
    "оператор",
    "жива людина",
    "людина",
    "менеджер",
)

TEXTS = {
    "thanks": {
        "en": "Thank you! I have everything I need. Here's a summary of your request:\n\n{summary}\n\nOur team will get back to you shortly. 🙌",
        "uk": "Дякую! У мене є вся потрібна інформація. Ось підсумок вашого запиту:\n\n{summary}\n\nНаша команда незабаром з вами зв'яжеться. 🙌",
    },
    "human": {
        "en": "Of course! I've notified our team — a real person will contact you as soon as possible. 👋",
        "uk": "Звісно! Я повідомив нашу команду — жива людина зв'яжеться з вами якнайшвидше. 👋",
    },
    "kb_prefix": {
        "en": "Here's what I found that might help:\n\n**{title}**\n{content}\n\nNow, back to my question: {question}",
        "uk": "Ось що я знайшов — можливо, це допоможе:\n\n**{title}**\n{content}\n\nПовернімося до мого запитання: {question}",
    },
    "error": {
        "en": "Sorry, I'm having trouble right now. Please try again in a moment.",
        "uk": "Вибачте, у мене виникли технічні труднощі. Спробуйте, будь ласка, ще раз за хвилину.",
    },
}


def _t(key: str, lang: str, **kwargs) -> str:
    template = TEXTS[key].get(lang) or TEXTS[key]["en"]
    return template.format(**kwargs) if kwargs else template


def _add_message(db: Session, conversation: Conversation, sender: str, text: str, **meta) -> Message:
    message = Message(
        conversation_id=conversation.id,
        sender=sender,
        text=text,
        meta={"node": (conversation.state or {}).get("current_node", ""), **meta},
    )
    db.add(message)
    return message


def get_default_workflow(db: Session, workspace_id: int = DEFAULT_WORKSPACE_ID) -> Workflow:
    scoped = select(Workflow).where(Workflow.workspace_id == workspace_id)
    workflow = db.scalars(scoped.where(Workflow.is_default == 1)).first()
    if workflow is None:
        workflow = db.scalars(scoped).first()
    if workflow is None:
        workflow = Workflow(
            workspace_id=workspace_id,
            name="Default intake",
            is_default=1,
            definition=wf.DEFAULT_WORKFLOW,
        )
        db.add(workflow)
        db.commit()
        db.refresh(workflow)
    return workflow


def start_conversation(
    db: Session,
    client_name: str = "",
    client_email: str = "",
    language: str = "",
    workflow_id: int | None = None,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> tuple[Conversation, ChatReply]:
    workflow = None
    if workflow_id is not None:
        workflow = db.get(Workflow, workflow_id)
        if workflow is not None and workflow.workspace_id != workspace_id:
            workflow = None  # tenant isolation: never run another workspace's flow
    if workflow is None:
        workflow = get_default_workflow(db, workspace_id)

    lang = language if language in ("en", "uk") else wf.detect_language(client_name)
    prefilled: dict = {}
    if client_name:
        prefilled["client_name"] = client_name
    if client_email:
        prefilled["client_email"] = client_email

    step = wf.start(workflow.definition, prefilled, lang)
    conversation = Conversation(
        workspace_id=workspace_id,
        workflow_id=workflow.id,
        language=lang,
        client_name=client_name,
        client_email=client_email,
        state=step.state,
        last_node=step.state.get("current_node", ""),
    )
    db.add(conversation)
    db.flush()

    greeting = step.reply or _t("thanks", lang, summary="")
    _add_message(db, conversation, "bot", greeting, event="greeting")
    db.commit()
    return conversation, ChatReply(bot_message=greeting, quick_replies=step.quick_replies)


async def process_message(db: Session, conversation: Conversation, text: str) -> ChatReply:
    text = text.strip()
    _add_message(db, conversation, "user", text, event="answer")

    # Pin the conversation language on the first meaningful user message.
    if conversation.language == "en" and wf.detect_language(text) == "uk":
        conversation.language = "uk"
    lang = conversation.language

    workflow = db.get(Workflow, conversation.workflow_id) or get_default_workflow(
        db, conversation.workspace_id
    )
    definition = workflow.definition

    # 1. Explicit human handoff.
    if any(k in text.lower() for k in HUMAN_KEYWORDS):
        reply_text = _t("human", lang)
        _add_message(db, conversation, "bot", reply_text, event="human_handoff")
        lead = await _finalize(db, conversation, human_requested=True)
        return ChatReply(bot_message=reply_text, done=True, lead_id=lead.id if lead else None)

    # 2. Off-script question → semantic KB lookup, then re-ask.
    state = dict(conversation.state or {})
    current_node = state.get("current_node", "")
    if kb_service.looks_like_question(text) and current_node:
        hits = await kb_service.search(db, text, workspace_id=conversation.workspace_id)
        if hits:
            article, kb_score = hits[0]
            question, options = _current_prompt(definition, current_node, lang)
            reply_text = _t(
                "kb_prefix", lang, title=article.title, content=article.content[:600], question=question
            )
            _add_message(
                db,
                conversation,
                "bot",
                reply_text,
                event="kb_answer",
                kb_article_id=article.id,
                kb_score=kb_score,
            )
            db.commit()
            return ChatReply(bot_message=reply_text, quick_replies=options)

    # 3. Normal workflow advance.
    step = wf.advance(definition, state, text, lang)
    conversation.state = step.state
    conversation.last_node = step.state.get("current_node", "") or conversation.last_node

    if step.done:
        lead = await _finalize(db, conversation, workflow=workflow)
        summary_text = lead.summary if lead else ""
        reply_text = _t("thanks", lang, summary=summary_text)
        _add_message(db, conversation, "bot", reply_text, event="summary")
        db.commit()
        return ChatReply(
            bot_message=reply_text, done=True, lead_id=lead.id if lead else None, summary=summary_text
        )

    reply_text = await _maybe_rephrase(db, conversation, workflow, step.reply)
    _add_message(
        db,
        conversation,
        "bot",
        reply_text,
        event="clarification" if step.needs_clarification else "question",
    )
    db.commit()
    return ChatReply(bot_message=reply_text, quick_replies=step.quick_replies)


def _current_prompt(definition: dict, node_id: str, lang: str) -> tuple[str, list[str]]:
    node = definition.get("nodes", {}).get(node_id, {})
    prompt = wf.localized(node.get("prompt", ""), lang)
    options = wf.localized(node.get("options", []), lang) or []
    return prompt, list(options)


async def _maybe_rephrase(db: Session, conversation: Conversation, workflow: Workflow, prompt: str) -> str:
    """With a real LLM configured, let it phrase the next question naturally
    while keeping the workflow's intent. Context comes from the memory module
    (short-term messages + compressed long-term summary, token-budgeted)."""
    config = llm.resolve_config(runtime_settings.llm_overrides(db, conversation.workspace_id))
    if config.provider == "mock" or not prompt:
        return prompt
    system = prompt_service.resolve(db, conversation.workspace_id, "system", workflow.prompt_name)
    context = await memory_service.build_context(db, conversation)
    instruction = (
        f"Ask the client the following question, rephrased naturally in the "
        f"conversation's language, in one short sentence. Keep the exact meaning. "
        f"Question: {prompt}"
    )
    try:
        result = await llm.complete(
            [*context.messages, {"role": "user", "content": instruction}],
            config=config,
            system=system,
        )
        return result or prompt
    except llm.LLMError:
        return prompt


async def _finalize(
    db: Session,
    conversation: Conversation,
    workflow: Workflow | None = None,
    human_requested: bool = False,
    abandoned: bool = False,
) -> Lead | None:
    """Create the Lead record, generate the summary and fan out notifications."""
    workspace_id = conversation.workspace_id
    answers = dict((conversation.state or {}).get("answers", {}))
    if conversation.client_name and not answers.get("client_name"):
        answers["client_name"] = conversation.client_name
    if conversation.client_email and not answers.get("client_email"):
        answers["client_email"] = conversation.client_email

    transcript = [{"sender": m.sender, "text": m.text} for m in conversation.messages]
    summary_text = await summary_service.generate_summary(
        db,
        transcript,
        answers,
        conversation.language,
        workspace_id,
        workflow_prompt_name=workflow.prompt_name if workflow else "",
    )
    score = score_lead(answers)
    threshold = int(runtime_settings.get(db, "qualified_score_threshold", workspace_id) or 40)

    if abandoned:
        status = "Incomplete"
    elif score >= threshold:
        status = "Qualified"
    else:
        status = "New"

    timeline = str(answers.get("timeline", "")).lower()
    if score >= 80 or any(k in timeline for k in ("asap", "urgent", "терміново", "якнайшвидше")):
        priority = "High"
    elif score >= 50:
        priority = "Medium"
    else:
        priority = "Low"

    budget = answers.get("budget")
    lead = Lead(
        workspace_id=workspace_id,
        project_name=summary_service.project_name_from(answers),
        client_name=str(answers.get("client_name", ""))[:255],
        client_email=str(answers.get("client_email", ""))[:255],
        client_phone=str(answers.get("client_phone", ""))[:64],
        service=str(answers.get("service", ""))[:255],
        budget=float(budget) if isinstance(budget, (int, float)) else None,
        timeline=str(answers.get("timeline", ""))[:255],
        summary=summary_text,
        status=status,
        priority=priority,
        tags=["human-requested"] if human_requested else [],
        score=score,
        language=conversation.language,
    )
    db.add(lead)
    db.flush()

    conversation.lead_id = lead.id
    conversation.status = "Abandoned" if abandoned else "Completed"
    conversation.ended_at = utcnow()

    detail = "Lead created from chat"
    if human_requested:
        detail += " (client requested a human)"
    if abandoned:
        detail = "Partial lead created from abandoned chat"
    db.add(ActivityLog(lead_id=lead.id, actor="system", action="created", detail=detail))
    db.commit()
    db.refresh(lead)

    # Notifications and CRM export are best-effort: never fail the chat.
    try:
        if not abandoned or human_requested:
            await notification_service.notify_new_lead(db, lead)
    except Exception:
        logger.exception("Notification fan-out failed for lead %s", lead.id)

    try:
        export_mode = runtime_settings.get(db, "crm_export_on", workspace_id)
        should_export = export_mode == "all" or (export_mode == "qualified" and status == "Qualified")
        if should_export and not abandoned:
            await crm_service.export_lead(db, lead)
    except Exception:
        logger.exception("CRM export failed to queue for lead %s", lead.id)
    return lead


async def close_stale_conversations(db: Session, max_age_hours: int = 24) -> int:
    """Mark active conversations older than the cutoff as Abandoned and keep
    their partial answers as Incomplete leads (so staff can follow up)."""
    cutoff = utcnow() - timedelta(hours=max_age_hours)
    stale = db.scalars(
        select(Conversation).where(Conversation.status == "Active", Conversation.started_at < cutoff)
    ).all()
    count = 0
    for conversation in stale:
        answers = (conversation.state or {}).get("answers", {})
        if any(str(v).strip() for v in answers.values()):
            await _finalize(db, conversation, abandoned=True)
        else:
            conversation.status = "Abandoned"
            conversation.ended_at = utcnow()
            db.commit()
        count += 1
    return count
