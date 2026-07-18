import hashlib
import hmac
import os
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import RefreshToken, utcnow

_PBKDF2_ITERATIONS = 260_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


# ── Access tokens (JWT, short-lived) ─────────────────────────────────────
def create_access_token(user_id: int, role: str, workspace_id: int) -> str:
    settings = get_settings()
    payload = {
        "sub": str(user_id),
        "role": role,
        "ws": workspace_id,
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(minutes=settings.jwt_expires_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


# ── Refresh tokens (opaque, hashed at rest, rotated on use) ──────────────
def _hash_refresh(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_refresh_token(db: Session, user_id: int) -> str:
    token = secrets.token_urlsafe(48)
    db.add(
        RefreshToken(
            user_id=user_id,
            token_hash=_hash_refresh(token),
            expires_at=utcnow() + timedelta(days=get_settings().refresh_token_days),
        )
    )
    db.commit()
    return token


def rotate_refresh_token(db: Session, token: str) -> tuple[int, str] | None:
    """Validate + revoke the presented token, issue a replacement.
    Returns (user_id, new_token) or None if invalid/expired/revoked."""
    row = db.scalars(
        select(RefreshToken).where(RefreshToken.token_hash == _hash_refresh(token))
    ).first()
    if row is None or row.revoked:
        return None
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
    if expires < utcnow():
        return None
    row.revoked = 1
    db.commit()
    return row.user_id, issue_refresh_token(db, row.user_id)


def revoke_refresh_token(db: Session, token: str) -> bool:
    row = db.scalars(
        select(RefreshToken).where(RefreshToken.token_hash == _hash_refresh(token))
    ).first()
    if row is None:
        return False
    row.revoked = 1
    db.commit()
    return True


def revoke_all_user_tokens(db: Session, user_id: int) -> None:
    for row in db.scalars(select(RefreshToken).where(RefreshToken.user_id == user_id)).all():
        row.revoked = 1
    db.commit()
