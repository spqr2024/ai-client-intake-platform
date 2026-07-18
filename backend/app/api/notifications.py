from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.models import Notification, User
from app.schemas import NotificationOut

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, le=200),
):
    query = (
        select(Notification)
        .where(
            Notification.workspace_id == user.workspace_id,
            Notification.channel == "inapp",
            Notification.user_id == user.id,
        )
        .order_by(Notification.created_at.desc(), Notification.id.desc())
    )
    if unread_only:
        query = query.where(Notification.read == 0)
    return db.scalars(query.limit(limit)).all()


@router.get("/deliveries", response_model=list[NotificationOut])
def list_deliveries(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    channel: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=50, le=200),
):
    """Outbound delivery log (email/telegram) with status and attempts."""
    query = (
        select(Notification)
        .where(Notification.workspace_id == user.workspace_id, Notification.channel != "inapp")
        .order_by(Notification.created_at.desc(), Notification.id.desc())
    )
    if channel:
        query = query.where(Notification.channel == channel)
    return db.scalars(query.limit(limit)).all()


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    notification = db.get(Notification, notification_id)
    if (
        notification is None
        or notification.workspace_id != user.workspace_id
        or notification.user_id != user.id
    ):
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.read = 1
    db.commit()
    db.refresh(notification)
    return notification


@router.post("/read-all", status_code=204)
def mark_all_read(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db.execute(
        update(Notification)
        .where(
            Notification.workspace_id == user.workspace_id,
            Notification.user_id == user.id,
            Notification.channel == "inapp",
        )
        .values(read=1)
    )
    db.commit()
