"""Unauthenticated endpoints consumed by the widget / landing page."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import DEFAULT_WORKSPACE_ID, Workspace
from app.schemas import BrandingOut
from app.services import runtime_settings

router = APIRouter(prefix="/api/public", tags=["public"])


def resolve_workspace_id(db: Session, slug: str) -> int:
    workspace = db.scalars(select(Workspace).where(Workspace.slug == slug)).first()
    return workspace.id if workspace else DEFAULT_WORKSPACE_ID


@router.get("/branding", response_model=BrandingOut)
def branding(
    workspace: str = Query(default="default", max_length=64),
    db: Session = Depends(get_db),
):
    workspace_id = resolve_workspace_id(db, workspace)
    values = runtime_settings.branding(db, workspace_id)
    return BrandingOut(
        company_name=values["brand_company_name"],
        bot_name=values["brand_bot_name"],
        logo_url=values["brand_logo_url"],
        primary_color=values["brand_primary_color"],
        hero_title=values["landing_hero_title"],
        hero_subtitle=values["landing_hero_subtitle"],
    )
