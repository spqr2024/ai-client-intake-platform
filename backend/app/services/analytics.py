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

    total_conversations = db.scalar(select(func.count()).select_from(ws_conversations.subquery())) or 0
    completed_conversations = (
        db.scalar(
            select(func.count(Conversation.id)).where(
                Conversation.workspace_id == workspace_id, Conversation.status == "Completed"
            )
        )
        or 0
    )
    total_leads = db.scalar(select(func.count()).select_from(ws_leads.subquery())) or 0
    converted = (
        db.scalar(
            select(func.count(Lead.id)).where(
                Lead.workspace_id == workspace_id,
                Lead.status.in_(["Converted", "In Progress", "Qualified"]),
            )
        )
        or 0
    )
    average_budget = (
        db.scalar(
            select(func.avg(Lead.budget)).where(Lead.workspace_id == workspace_id, Lead.budget.is_not(None))
        )
        or 0
    )
    average_score = db.scalar(select(func.avg(Lead.score)).where(Lead.workspace_id == workspace_id)) or 0

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

    # Conversation counts by status — aggregated in SQL, not in Python.
    status_counts = dict(
        db.execute(
            select(Conversation.status, func.count(Conversation.id))
            .where(Conversation.workspace_id == workspace_id)
            .group_by(Conversation.status)
        ).all()
    )
    total = sum(status_counts.values())
    completed_count = status_counts.get("Completed", 0)
    abandoned_count = status_counts.get("Abandoned", 0)

    # Average messages per conversation: two scalar aggregates, no row loading.
    message_total = (
        db.scalar(
            select(func.count(Message.id))
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.workspace_id == workspace_id)
        )
        or 0
    )
    avg_messages = round(message_total / total, 1) if total else 0.0

    # Durations: only finished conversations, only the two timestamp columns.
    duration_rows = db.execute(
        select(Conversation.started_at, Conversation.ended_at).where(
            Conversation.workspace_id == workspace_id, Conversation.ended_at.is_not(None)
        )
    ).all()
    durations = [
        (ended - started).total_seconds()
        for started, ended in duration_rows
        if started is not None and ended is not None
    ]
    avg_duration = round(sum(durations) / len(durations), 1) if durations else 0.0

    # Drop-off points: group unfinished conversations by their last node.
    dropoff_rows = db.execute(
        select(Conversation.last_node, func.count(Conversation.id))
        .where(Conversation.workspace_id == workspace_id, Conversation.status != "Completed")
        .group_by(Conversation.last_node)
    ).all()
    dropoff = {(node or "(start)"): count for node, count in dropoff_rows}

    # Most common client questions — bounded scan of recent user messages.
    question_rows = db.execute(
        select(Message.text)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Conversation.workspace_id == workspace_id, Message.sender == "user", Message.text.like("%?%"))
        .order_by(Message.id.desc())
        .limit(1000)
    ).all()
    question_counts: dict[str, int] = {}
    for (text,) in question_rows:
        stripped = (text or "").strip()
        if len(stripped) >= 10:
            key = stripped.lower()[:80]
            question_counts[key] = question_counts.get(key, 0) + 1
    common_questions = sorted(question_counts.items(), key=lambda i: i[1], reverse=True)[:10]

    # Lead quality bands and funnel — SQL aggregates over indexed columns.
    quality_bands = {
        "high (70+)": db.scalar(
            select(func.count(Lead.id)).where(Lead.workspace_id == workspace_id, Lead.score >= 70)
        )
        or 0,
        "medium (40-69)": db.scalar(
            select(func.count(Lead.id)).where(
                Lead.workspace_id == workspace_id, Lead.score >= 40, Lead.score < 70
            )
        )
        or 0,
        "low (<40)": db.scalar(
            select(func.count(Lead.id)).where(Lead.workspace_id == workspace_id, Lead.score < 40)
        )
        or 0,
    }
    total_leads = sum(quality_bands.values())

    # AI capture confidence: share of the five core fields captured per lead,
    # computed as five COUNTs rather than by materializing every lead.
    captured = 0
    for column in (Lead.client_name, Lead.client_email, Lead.service, Lead.timeline):
        captured += (
            db.scalar(select(func.count(Lead.id)).where(Lead.workspace_id == workspace_id, column != "")) or 0
        )
    captured += (
        db.scalar(
            select(func.count(Lead.id)).where(Lead.workspace_id == workspace_id, Lead.budget.is_not(None))
        )
        or 0
    )
    avg_confidence = round(captured / (total_leads * 5), 3) if total_leads else 0.0

    funnel = {
        "started": total,
        "completed": completed_count,
        "leads": total_leads,
        "qualified": db.scalar(
            select(func.count(Lead.id)).where(
                Lead.workspace_id == workspace_id,
                Lead.status.in_(["Qualified", "In Progress", "Converted"]),
            )
        )
        or 0,
        "converted": db.scalar(
            select(func.count(Lead.id)).where(Lead.workspace_id == workspace_id, Lead.status == "Converted")
        )
        or 0,
    }

    result = {
        "avg_messages_per_conversation": avg_messages,
        "avg_conversation_seconds": avg_duration,
        "abandonment_rate": round(abandoned_count / total, 3) if total else 0.0,
        "dropoff_by_node": dict(sorted(dropoff.items(), key=lambda i: i[1], reverse=True)),
        "common_questions": [{"question": q, "count": n} for q, n in common_questions],
        "lead_quality": quality_bands,
        "avg_ai_confidence": avg_confidence,
        "funnel": funnel,
    }
    get_cache().set(cache_key, result, CACHE_TTL_SECONDS)
    return result
