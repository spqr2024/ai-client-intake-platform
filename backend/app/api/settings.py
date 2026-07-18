from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db import get_db
from app.models import User, Workspace
from app.schemas import SettingsOut, SettingsUpdate, WorkspaceOut
from app.services import audit, runtime_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsOut)
def get_settings_values(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return SettingsOut(values=runtime_settings.get_all(db, admin.workspace_id))


@router.put("", response_model=SettingsOut)
def update_settings_values(
    body: SettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    changed = sorted(key for key in body.values if runtime_settings.is_editable(key))
    result = runtime_settings.set_many(db, body.values, admin.workspace_id)
    audit.record(db, admin.workspace_id, admin.email, "settings_updated", "settings", "",
                 detail=f"keys: {', '.join(changed)}", request=request)
    return SettingsOut(values=result)


@router.get("/workspace", response_model=WorkspaceOut)
def get_workspace(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return db.get(Workspace, admin.workspace_id)
