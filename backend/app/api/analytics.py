from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.models import User
from app.schemas import AIAnalytics, AnalyticsSummary
from app.services import analytics as analytics_service

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/summary", response_model=AnalyticsSummary)
def get_summary(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return analytics_service.summary(db, days=days, workspace_id=user.workspace_id)


@router.get("/ai", response_model=AIAnalytics)
def get_ai_analytics(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return analytics_service.ai_summary(db, workspace_id=user.workspace_id)
