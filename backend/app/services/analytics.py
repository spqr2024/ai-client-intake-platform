from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Conversation, Lead, utcnow


def summary(db: Session, days: int = 30) -> dict:
    since = utcnow() - timedelta(days=days)

    total_conversations = db.scalar(select(func.count(Conversation.id))) or 0
    completed_conversations = db.scalar(
        select(func.count(Conversation.id)).where(Conversation.status == "Completed")
    ) or 0
    total_leads = db.scalar(select(func.count(Lead.id))) or 0
    converted = db.scalar(
        select(func.count(Lead.id)).where(Lead.status.in_(["Converted", "In Progress", "Qualified"]))
    ) or 0
    average_budget = db.scalar(select(func.avg(Lead.budget)).where(Lead.budget.is_not(None))) or 0
    average_score = db.scalar(select(func.avg(Lead.score))) or 0

    leads_by_status = dict(
        db.execute(select(Lead.status, func.count(Lead.id)).group_by(Lead.status)).all()
    )
    leads_by_service = dict(
        db.execute(
            select(Lead.service, func.count(Lead.id))
            .where(Lead.service != "")
            .group_by(Lead.service)
            .order_by(func.count(Lead.id).desc())
            .limit(10)
        ).all()
    )

    per_day_rows = db.execute(
        select(func.date(Lead.created_at), func.count(Lead.id))
        .where(Lead.created_at >= since)
        .group_by(func.date(Lead.created_at))
        .order_by(func.date(Lead.created_at))
    ).all()
    leads_per_day = [{"date": str(row[0]), "count": row[1]} for row in per_day_rows]

    return {
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
        "leads_per_day": leads_per_day,
    }
