from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.rate_limit import client_ip, login_succeeded, login_throttle, rate_limit
from app.core.security import (
    create_access_token,
    issue_refresh_token,
    revoke_refresh_token,
    rotate_refresh_token,
    verify_password,
)
from app.db import get_db
from app.models import User
from app.schemas import LoginRequest, RefreshRequest, TokenResponse, UserOut
from app.services import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    rate_limit(request)
    ip = client_ip(request)
    login_throttle(body.email, ip)

    user = db.scalars(select(User).where(User.email == body.email.lower())).first()
    if user is None or not verify_password(body.password, user.password_hash):
        if user is not None:
            audit.record(db, user.workspace_id, body.email, "login_failed", "user", user.id, request=request)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    login_succeeded(body.email, ip)
    audit.record(db, user.workspace_id, user.email, "login", "user", user.id, request=request)
    return TokenResponse(
        access_token=create_access_token(user.id, user.role, user.workspace_id),
        refresh_token=issue_refresh_token(db, user.id),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    rate_limit(request)
    rotated = rotate_refresh_token(db, body.refresh_token)
    if rotated is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    user_id, new_refresh = rotated
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return TokenResponse(
        access_token=create_access_token(user.id, user.role, user.workspace_id),
        refresh_token=new_refresh,
    )


@router.post("/logout", status_code=204)
def logout(
    body: RefreshRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    revoke_refresh_token(db, body.refresh_token)
    audit.record(db, user.workspace_id, user.email, "logout", "user", user.id, request=request)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
