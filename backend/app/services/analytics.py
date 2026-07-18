"""Analytics: CRM KPIs + AI conversation analytics.

Results are cached (60s) through the cache abstraction — Redis-backed when
configured — because these aggregations run on every dashboard load.
"""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.cache import get_cache
from app.models import DEFAULT_WORKSPACE_ID, Conversation, Lead, Message, utcnow

CACHE_TTL_SECONDS = 60

# Core fields a "confident" intake should have captured.
CONFIDENCE_FIELDS = ("client_name", "client_email", "service", "budget", "timeline", "goals")


def summary(db: Session, days: int = 30, workspace_id: int = DEFAULT_WORKSPACE_ID) -> dict:
    cache_key = f"analytics:{workspace_id}:{days}"
    cached = get_cache().get(cache_key)
    if isinstance(cached, dict):
        return cached

    since = utcnow() - timedelta(days=days)
    ws_conversations = select(Conversation).where(Conversation.workspace_id == workspace_id)
    ws_leads = select(Lead).where(Lead.workspace_id == workspace_id)

    total_conversations = db.scalar(
        select(func.count()).select_from(ws_conversations.subquery())
    ) or 0
    completed_conversations = db.scalar(
        select(func.count(Conversation.id)).where(
            Conversation.workspace_id == workspace_id, Conversation.status == "Completed"
        )
    ) or 0
    total_leads = db.scalar(select(func.count()).select_from(ws_leads.subquery())) or 0
    converted = db.scalar(
        select(func.count(Lead.id)).where(
            Lead.workspace_id == workspace_id,
            Lead.status.in_(["Converted", "In Progress", "Qualified"]),
        )
    ) or 0
    average_budget = db.scalar(
        select(func.avg(Lead.budget)).where(
            Lead.workspace_id == workspace_id, Lead.budget.is_not(None)
        )
    ) or 0
    average_score = db.scalar(
        select(func.avg(Lead.score)).where(Lead.workspace_id == workspace_id)
    ) or 0

    leads_by_status = dict(
        db.execute(
            select(Lead.status, func.count(Lead.id))
            .where(Lead.workspace_id == workspace_id)
            .group_by(Lead.status)
        ).all()
    )
    leads_by_service = dict(
        db.execute(
            select(Lead.service, func.count(Lead.id))
            .where(Lead.workspace_id == workspace_id, Lead.service != "")
            .group_by(Lead.service)
            .order_by(func.count(Lead.id).desc())
            .limit(10)
        ).all()
    )
    per_day_rows = db.execute(
        select(func.date(Lead.created_at), func.count(Lead.id))
        .where(Lead.workspace_id == workspace_id, Lead.created_at >= since)
        .group_by(func.date(Lead.created_at))
        .order_by(func.date(Lead.created_at))
    ).all()

    result = {
        "total_conversations": total_conversations,
        "total_leads": total_leads,
        "completion_rate": round(completed_conversations / total_conversations, 3)
        if total_conversations
        else 0.0,
        "conversion_rate": round(converted / total_leads, 3) if total_leads else 0.0,
        "average_budget": round(float(average_budget), 2),
        "average_score": round(float(average_score), 1),
        "leads_by_status": leads_by_status,
        "leads_by_service": leads_by_service,
        "leads_per_day": [{"date": str(row[0]), "count": row[1]} for row in per_day_rows],
    }
    get_cache().set(cache_key, result, CACHE_TTL_SECONDS)
    return result


def ai_summary(db: Session, workspace_id: int = DEFAULT_WORKSPACE_ID) -> dict:
    """AI conversation analytics: funnel, drop-off, lengths, confidence."""
    cache_key = f"analytics:ai:{workspace_id}"
    cached = get_cache().get(cache_key)
    if isinstance(cached, dict):
        return cached

    conversations = db.scalars(
        select(Conversation).where(Conversation.workspace_id == workspace_id)
    ).all()
    total = len(conversations)
    completed = [c for c in conversations if c.status == "Completed"]
    abandoned = [c for c in conversations if c.status == "Abandoned"]

    # Average conversation length (messages) and duration (seconds).
    message_counts = db.execute(
        select(Message.conversation_id, func.count(Message.id))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Conversation.workspace_id == workspace_id)
        .group_by(Message.conversation_id)
    ).all()
    counts_by_conv = dict(message_counts)
    avg_messages = (
        round(sum(counts_by_conv.values()) / len(counts_by_conv), 1) if counts_by_conv else 0.0
    )
    durations = [
        (c.ended_at - c.started_at).total_seconds()
        for c in conversations
        if c.ended_at is not None and c.started_at is not None
    ]
    avg_duration = round(sum(durations) / len(durations), 1) if durations else 0.0

    # Drop-off points: where do abandoned/active conversations sit?
    dropoff: dict[str, int] = {}
    for c in conversations:
        if c.status != "Completed":
            node = c.last_node or (c.state or {}).get("current_node", "") or "(start)"
            dropoff[node] = dropoff.get(node, 0) + 1

    # Most common off-script questions answered from the KB.
    kb_messages = db.scalars(
        select(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Conversation.workspace_id == workspace_id, Message.sender == "user")
        .order_by(Message.id.desc())
        .limit(2000)
    ).all()
    question_counts: dict[str, int] = {}
    for m in kb_messages:
        text = m.text.strip()
        if "?" in text and len(text) >= 10:
            key = text.lower()[:80]
            question_counts[key] = question_counts.get(key, 0) + 1
    common_questions = sorted(question_counts.items(), key=lambda i: i[1], reverse=True)[:10]

    # Lead quality & AI confidence (field-capture completeness per lead).
    leads = db.scalars(select(Lead).where(Lead.workspace_id == workspace_id)).all()
    quality_bands = {"high (70+)": 0, "medium (40-69)": 0, "low (<40)": 0}
    confidences: list[float] = []
    for lead in leads:
        if lead.score >= 70:
            quality_bands["high (70+)"] += 1
        elif lead.score >= 40:
            quality_bands["medium (40-69)"] += 1
        else:
            quality_bands["low (<40)"] += 1
        captured = sum(
            1 for f in (lead.client_name, lead.client_email, lead.service, lead.timeline) if f
        ) + (1 if lead.budget else 0)
        confidences.append(captured / 5)
    avg_confidence = round(sum(confidences) / len(confidences), 3) if confidences else 0.0

    funnel = {
        "started": total,
        "completed": len(completed),
        "leads": len(leads),
        "qualified": sum(1 for lead in leads if lead.status in ("Qualified", "In Progress", "Converted")),
        "converted": sum(1 for lead in leads if lead.status == "Converted"),
    }

    result = {
        "avg_messages_per_conversation": avg_messages,
        "avg_conversation_seconds": avg_duration,
        "abandonment_rate": round(len(abandoned) / total, 3) if total else 0.0,
        "dropoff_by_node": dict(sorted(dropoff.items(), key=lambda i: i[1], reverse=True)),
        "common_questions": [{"question": q, "count": n} for q, n in common_questions],
        "lead_quality": quality_bands,
        "avg_ai_confidence": avg_confidence,
        "funnel": funnel,
    }
    get_cache().set(cache_key, result, CACHE_TTL_SECONDS)
    return result
