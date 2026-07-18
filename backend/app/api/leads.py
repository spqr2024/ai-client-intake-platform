from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.models import ActivityLog, Conversation, Lead, User
from app.schemas import (
    ActivityOut,
    LeadDetail,
    LeadListItem,
    LeadUpdate,
    NoteCreate,
    ReplayEvent,
    ReplayOut,
)
from app.services import audit, runtime_settings
from app.services import notifications as notification_service

router = APIRouter(prefix="/api/leads", tags=["leads"])


def _get_lead(db: Session, lead_id: int, user: User) -> Lead:
    lead = db.get(Lead, lead_id)
    if lead is None or lead.workspace_id != user.workspace_id:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.get("", response_model=list[LeadListItem])
def list_leads(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    status: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    tag: str | None = Query(default=None, max_length=60),
    priority: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=200, le=500),
    offset: int = Query(default=0, ge=0),
):
    query = (
        select(Lead)
        .where(Lead.workspace_id == user.workspace_id)
        .order_by(Lead.created_at.desc())
    )
    if status:
        query = query.where(Lead.status == status)
    if priority:
        query = query.where(Lead.priority == priority)
    if search:
        pattern = f"%{search}%"
        query = query.where(
            or_(
                Lead.project_name.ilike(pattern),
                Lead.client_name.ilike(pattern),
                Lead.client_email.ilike(pattern),
                Lead.service.ilike(pattern),
                Lead.summary.ilike(pattern),
            )
        )
    leads = db.scalars(query.limit(limit).offset(offset)).all()
    if tag:  # tags live in a JSON column; filter in Python (portable across DBs)
        leads = [lead for lead in leads if tag in (lead.tags or [])]
    return leads


@router.get("/pipeline")
def pipeline(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Kanban data: workspace pipeline stages + leads grouped by status."""
    statuses = runtime_settings.pipeline_statuses(db, user.workspace_id)
    leads = db.scalars(
        select(Lead)
        .where(Lead.workspace_id == user.workspace_id)
        .order_by(Lead.created_at.desc())
        .limit(500)
    ).all()
    columns = {status: [] for status in statuses}
    for lead in leads:
        columns.setdefault(lead.status, []).append(
            LeadListItem.model_validate(lead).model_dump(mode="json")
        )
    return {"statuses": statuses, "columns": columns}


@router.get("/{lead_id}", response_model=LeadDetail)
def get_lead(lead_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    lead = _get_lead(db, lead_id, user)
    conversation = db.scalars(select(Conversation).where(Conversation.lead_id == lead.id)).first()
    detail = LeadDetail.model_validate(lead)
    if conversation:
        detail.messages = [m for m in conversation.messages]  # type: ignore[assignment]
        detail.attachments = [a for a in conversation.attachments]  # type: ignore[assignment]
    return detail


@router.get("/{lead_id}/replay", response_model=ReplayOut)
def replay(lead_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Full conversation replay: messages with node/event metadata,
    attachments and CRM activity merged on one timeline."""
    lead = _get_lead(db, lead_id, user)
    conversation = db.scalars(select(Conversation).where(Conversation.lead_id == lead.id)).first()

    events: list[ReplayEvent] = []
    if conversation:
        for m in conversation.messages:
            events.append(ReplayEvent(at=m.created_at, type="message", sender=m.sender,
                                      text=m.text, meta=m.meta or {}))
        for a in conversation.attachments:
            events.append(ReplayEvent(at=a.created_at, type="attachment", sender="user",
                                      text=a.filename, meta={"size": a.size}))
    for activity in lead.activities:
        events.append(ReplayEvent(at=activity.created_at, type="activity", sender=activity.actor,
                                  text=activity.detail, meta={"action": activity.action}))
    events.sort(key=lambda e: e.at)
    return ReplayOut(
        conversation_id=conversation.id if conversation else None,
        started_at=conversation.started_at if conversation else None,
        ended_at=conversation.ended_at if conversation else None,
        language=conversation.language if conversation else lead.language,
        events=events,
    )


@router.patch("/{lead_id}", response_model=LeadDetail)
async def update_lead(
    lead_id: int,
    body: LeadUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    lead = _get_lead(db, lead_id, user)

    changes: list[str] = []
    old_status = lead.status
    if body.status is not None and body.status != lead.status:
        allowed = runtime_settings.pipeline_statuses(db, user.workspace_id)
        if body.status not in allowed:
            raise HTTPException(
                status_code=422,
                detail=f"Status must be one of the workspace pipeline: {', '.join(allowed)}",
            )
        changes.append(f"status: {lead.status} → {body.status}")
        lead.status = body.status
    if body.assigned_to_id is not None:
        assignee = db.get(User, body.assigned_to_id)
        if assignee is None or assignee.workspace_id != user.workspace_id:
            raise HTTPException(status_code=404, detail="Assignee not found")
        lead.assigned_to_id = assignee.id
        changes.append(f"assigned to {assignee.name}")
    if body.project_name is not None:
        lead.project_name = body.project_name[:255]
        changes.append("project name updated")
    if body.score is not None:
        changes.append(f"score: {lead.score} → {body.score}")
        lead.score = body.score
    if body.priority is not None and body.priority != lead.priority:
        changes.append(f"priority: {lead.priority} → {body.priority}")
        lead.priority = body.priority
    if body.tags is not None:
        lead.tags = [t.strip()[:60] for t in body.tags if t.strip()][:20]
        changes.append(f"tags: {', '.join(lead.tags) or '(none)'}")
    if body.clear_follow_up:
        lead.follow_up_at = None
        changes.append("follow-up cleared")
    elif body.follow_up_at is not None:
        lead.follow_up_at = body.follow_up_at
        changes.append(f"follow-up set to {body.follow_up_at:%Y-%m-%d %H:%M}")

    if changes:
        db.add(ActivityLog(lead_id=lead.id, actor=user.name, action="status_change",
                           detail="; ".join(changes)))
        audit.record(db, user.workspace_id, user.email, "lead_updated", "lead", lead.id,
                     detail="; ".join(changes), request=request, commit=False)
    db.commit()
    db.refresh(lead)

    if old_status != lead.status:
        try:
            await notification_service.notify_lead_status_change(db, lead, old_status, user.name)
        except Exception:  # noqa: BLE001 — notifications must not fail the update
            pass
    return get_lead(lead_id, db, user)


@router.post("/{lead_id}/notes", response_model=ActivityOut, status_code=201)
def add_note(
    lead_id: int,
    body: NoteCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    lead = _get_lead(db, lead_id, user)
    note = ActivityLog(lead_id=lead.id, actor=user.name, action=body.kind, detail=body.text)
    db.add(note)
    db.commit()
    db.refresh(note)
    return note
