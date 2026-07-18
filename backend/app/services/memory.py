"""Conversation memory for long chats.

Short-term memory: the most recent messages, verbatim.
Long-term memory: a rolling summary of everything older, compressed
incrementally and stored in conversation.state["memory"] so it survives
restarts and is shared across stateless API instances.

Compression uses the configured LLM when available and falls back to a
deterministic extractive strategy (first sentences + captured answers) in
mock/offline mode. Token budgeting is a chars/4 heuristic — good enough to
keep prompts bounded without a tokenizer dependency.
"""

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Conversation, utcnow
from app.services import llm, runtime_settings

logger = logging.getLogger(__name__)

SHORT_TERM_MESSAGES = 8       # most recent messages kept verbatim
TOKEN_BUDGET = 1600           # max estimated tokens for the whole context
MEMORY_TTL_HOURS = 48         # rolling summary is stale after this


@dataclass
class ConversationContext:
    messages: list[dict]      # [{role, content}] ready for the LLM
    summary: str              # long-term memory ("" when none)
    estimated_tokens: int


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _extractive_summary(messages: list, answers: dict) -> str:
    """Offline compression: captured answers + first user statements."""
    parts = [f"{k}: {v}" for k, v in answers.items() if str(v).strip()]
    for message in messages:
        if message.sender == "user" and len(message.text) > 40:
            parts.append(message.text.split(".")[0][:120])
    return "Known so far — " + "; ".join(parts[:12]) if parts else ""


async def _compress(db: Session, conversation: Conversation, older_messages: list) -> str:
    answers = (conversation.state or {}).get("answers", {})
    config = llm.resolve_config(runtime_settings.llm_overrides(db, conversation.workspace_id))
    if config.provider == "mock":
        return _extractive_summary(older_messages, answers)
    transcript = "\n".join(f"{m.sender}: {m.text}" for m in older_messages)
    previous = ((conversation.state or {}).get("memory") or {}).get("summary", "")
    prompt = (
        "Update this running summary of an intake conversation. Keep every "
        "concrete fact (names, budgets, dates, requirements), drop small talk. "
        f"Max 120 words.\n\nPrevious summary:\n{previous or '(none)'}\n\nNew messages:\n{transcript}"
    )
    try:
        return await llm.complete([{"role": "user", "content": prompt}], config=config)
    except llm.LLMError:
        logger.warning("Memory compression failed; using extractive fallback")
        return _extractive_summary(older_messages, answers)


async def build_context(db: Session, conversation: Conversation) -> ConversationContext:
    """Assemble short-term messages + long-term summary within TOKEN_BUDGET,
    refreshing the stored rolling summary when older messages accumulate."""
    messages = list(conversation.messages)
    recent = messages[-SHORT_TERM_MESSAGES:]
    older = messages[: -SHORT_TERM_MESSAGES] if len(messages) > SHORT_TERM_MESSAGES else []

    state = dict(conversation.state or {})
    memory = dict(state.get("memory") or {})
    summary = memory.get("summary", "")
    compressed_upto = int(memory.get("upto", 0))

    if older and older[-1].id > compressed_upto:
        summary = await _compress(db, conversation, [m for m in older if m.id > compressed_upto])
        state["memory"] = {
            "summary": summary,
            "upto": older[-1].id,
            "updated_at": utcnow().isoformat(),
            "expires_hours": MEMORY_TTL_HOURS,
        }
        conversation.state = state
        db.commit()

    context: list[dict] = []
    if summary:
        context.append({"role": "user", "content": f"[Conversation context so far: {summary}]"})
    context += [
        {"role": "assistant" if m.sender == "bot" else "user", "content": m.text} for m in recent
    ]

    # Enforce the token budget by dropping oldest short-term messages first
    # (the summary already covers them in spirit).
    def total() -> int:
        return sum(estimate_tokens(m["content"]) for m in context)

    while len(context) > 2 and total() > TOKEN_BUDGET:
        context.pop(1 if summary else 0)

    return ConversationContext(messages=context, summary=summary, estimated_tokens=total())
