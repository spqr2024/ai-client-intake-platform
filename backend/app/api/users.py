from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.security import hash_password, revoke_all_user_tokens
from app.db import get_db
from app.models import User
from app.schemas import UserCreate, UserOut, UserRoleUpdate
from app.services import audit

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(
        select(User).where(User.workspace_id == user.workspace_id).order_by(User.id)
    ).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    body: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    email = body.email.lower()
    if db.scalars(select(User).where(User.email == email)).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        workspace_id=admin.workspace_id, name=body.name, email=email,
        password_hash=hash_password(body.password), role=body.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    audit.record(db, admin.workspace_id, admin.email, "user_created", "user", user.id,
                 detail=f"{user.email} ({user.role})", request=request)
    return user


@router.patch("/{user_id}/role", response_model=UserOut)
def change_role(
    user_id: int,
    body: UserRoleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if user is None or user.workspace_id != admin.workspace_id:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot change your own role")
    old_role = user.role
    user.role = body.role
    db.commit()
    db.refresh(user)
    revoke_all_user_tokens(db, user.id)  # force re-login with the new role
    audit.record(db, admin.workspace_id, admin.email, "role_change", "user", user.id,
                 detail=f"{user.email}: {old_role} → {user.role}", request=request)
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    user = db.get(User, user_id)
    if user is None or user.workspace_id != admin.workspace_id:
        raise HTTPException(status_code=404, detail="User not found")
    revoke_all_user_tokens(db, user.id)
    email = user.email
    db.delete(user)
    db.commit()
    audit.record(db, admin.workspace_id, admin.email, "user_deleted", "user", user_id,
                 detail=email, request=request)
