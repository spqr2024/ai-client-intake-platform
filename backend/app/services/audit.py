"""Audit trail: one call site (`record`) used by every security- or
configuration-relevant mutation. Kept synchronous and in-transaction so an
audited action and its audit row commit together."""

import logging

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rate_limit import client_ip
from app.models import AuditLog

logger = logging.getLogger(__name__)


def record(
    db: Session,
    workspace_id: int,
    actor: str,
    action: str,
    entity: str = "",
    entity_id: str | int = "",
    detail: str = "",
    request: Request | None = None,
    commit: bool = True,
) -> None:
    db.add(
        AuditLog(
            workspace_id=workspace_id,
            actor=actor,
            action=action,
            entity=entity,
            entity_id=str(entity_id),
            detail=detail[:2000],
            ip=client_ip(request) if request else "",
        )
    )
    if commit:
        db.commit()


def query(
    db: Session,
    workspace_id: int,
    action: str | None = None,
    actor: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditLog]:
    stmt = (
        select(AuditLog)
        .where(AuditLog.workspace_id == workspace_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    )
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if actor:
        stmt = stmt.where(AuditLog.actor.ilike(f"%{actor}%"))
    return list(db.scalars(stmt.limit(limit).offset(offset)).all())
