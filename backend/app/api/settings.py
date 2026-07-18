from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db import get_db
from app.models import User
from app.schemas import SettingsOut, SettingsUpdate
from app.services import runtime_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsOut)
def get_settings_values(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return SettingsOut(values=runtime_settings.get_all(db))


@router.put("", response_model=SettingsOut)
def update_settings_values(
    body: SettingsUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)
):
    return SettingsOut(values=runtime_settings.set_many(db, body.values))
