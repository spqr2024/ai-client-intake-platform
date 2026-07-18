from fastapi import HTTPException, Request

from app.core.cache import get_cache
from app.core.config import get_settings

_WINDOW_SECONDS = 60


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request) -> None:
    """Sliding-window limiter keyed by client IP. Backed by the cache
    abstraction: cluster-wide when Redis is configured, per-process otherwise."""
    limit = get_settings().rate_limit_per_minute
    if limit <= 0:
        return
    count = get_cache().incr_window(f"rl:{client_ip(request)}", _WINDOW_SECONDS)
    if count > limit:
        raise HTTPException(status_code=429, detail="Too many requests, slow down.")


def login_throttle(email: str, ip: str) -> None:
    """Brute-force lockout for the login endpoint (per email+IP)."""
    settings = get_settings()
    if settings.login_max_attempts <= 0:
        return
    key = f"login:{email.lower()}:{ip}"
    count = get_cache().incr_window(key, settings.login_lockout_minutes * 60)
    if count > settings.login_max_attempts:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {settings.login_lockout_minutes} minutes.",
        )


def login_succeeded(email: str, ip: str) -> None:
    get_cache().delete(f"login:{email.lower()}:{ip}")
