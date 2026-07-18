from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.db import get_db
from app.models import Lead, User
from app.schemas import CRMProviderOut, CRMSyncOut
from app.services import audit
from app.services import crm as crm_service

router = APIRouter(prefix="/api/crm", tags=["crm-integrations"])


@router.get("/providers", response_model=list[CRMProviderOut])
def list_providers(_: User = Depends(get_current_user)):
    """Registered CRM adapters and the extra settings each one needs."""
    return crm_service.available_providers()


@router.get("/syncs", response_model=list[CRMSyncOut])
def list_syncs(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return crm_service.recent_syncs(db, user.workspace_id)


@router.post("/leads/{lead_id}/export", response_model=CRMSyncOut, status_code=202)
async def export_lead(
    lead_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Manually queue a lead export to the configured CRM."""
    lead = db.get(Lead, lead_id)
    if lead is None or lead.workspace_id != admin.workspace_id:
        raise HTTPException(status_code=404, detail="Lead not found")
    entry = await crm_service.export_lead(db, lead)
    if entry is None:
        raise HTTPException(
            status_code=409,
            detail="No CRM provider configured for this workspace (Settings → Integrations).",
        )
    audit.record(db, admin.workspace_id, admin.email, "crm_export", "lead", lead.id,
                 detail=f"queued export to {entry.provider}", request=request)
    return entry
