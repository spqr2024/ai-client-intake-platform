from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.models import ActivityLog, Conversation, Lead, User
from app.schemas import ActivityOut, LeadDetail, LeadListItem, LeadUpdate, NoteCreate

router = APIRouter(prefix="/api/leads", tags=["leads"])


@router.get("", response_model=list[LeadListItem])
def list_leads(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    status: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
):
    query = select(Lead).order_by(Lead.created_at.desc())
    if status:
        query = query.where(Lead.status == status)
    if search:
        pattern = f"%{search}%"
        query = query.where(
            or_(
                Lead.project_name.ilike(pattern),
                Lead.client_name.ilike(pattern),
                Lead.client_email.ilike(pattern),
                Lead.service.ilike(pattern),
            )
        )
    return db.scalars(query.limit(limit).offset(offset)).all()


@router.get("/{lead_id}", response_model=LeadDetail)
def get_lead(lead_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    conversation = db.scalars(select(Conversation).where(Conversation.lead_id == lead.id)).first()
    detail = LeadDetail.model_validate(lead)
    if conversation:
        detail.messages = [m for m in conversation.messages]  # type: ignore[assignment]
        detail.attachments = [a for a in conversation.attachments]  # type: ignore[assignment]
    return detail


@router.patch("/{lead_id}", response_model=LeadDetail)
def update_lead(
    lead_id: int,
    body: LeadUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")

    changes: list[str] = []
    if body.status is not None and body.status != lead.status:
        changes.append(f"status: {lead.status} → {body.status}")
        lead.status = body.status
    if body.assigned_to_id is not None:
        assignee = db.get(User, body.assigned_to_id)
        if assignee is None:
            raise HTTPException(status_code=404, detail="Assignee not found")
        lead.assigned_to_id = assignee.id
        changes.append(f"assigned to {assignee.name}")
    if body.project_name is not None:
        lead.project_name = body.project_name[:255]
        changes.append("project name updated")
    if body.score is not None:
        changes.append(f"score: {lead.score} → {body.score}")
        lead.score = body.score

    if changes:
        db.add(ActivityLog(lead_id=lead.id, actor=user.name, action="status_change",
                           detail="; ".join(changes)))
    db.commit()
    db.refresh(lead)
    return get_lead(lead_id, db, user)


@router.post("/{lead_id}/notes", response_model=ActivityOut, status_code=201)
def add_note(
    lead_id: int,
    body: NoteCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    note = ActivityLog(lead_id=lead.id, actor=user.name, action="note", detail=body.text)
    db.add(note)
    db.commit()
    db.refresh(note)
    return note
