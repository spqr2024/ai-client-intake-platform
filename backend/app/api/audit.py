from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db import get_db
from app.models import User
from app.schemas import AuditOut
from app.services import audit as audit_service

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=list[AuditOut])
def list_audit(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
    action: str | None = Query(default=None, max_length=60),
    actor: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
):
    return audit_service.query(db, admin.workspace_id, action=action, actor=actor,
                               limit=limit, offset=offset)
