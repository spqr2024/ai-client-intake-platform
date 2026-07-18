import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.core.config import get_settings

_WINDOW_SECONDS = 60
_hits: dict[str, deque[float]] = defaultdict(deque)


def rate_limit(request: Request) -> None:
    """Simple in-memory sliding-window limiter keyed by client IP.

    For multi-instance deployments swap this for a Redis-backed limiter.
    """
    limit = get_settings().rate_limit_per_minute
    if limit <= 0:
        return
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    bucket = _hits[ip]
    while bucket and now - bucket[0] > _WINDOW_SECONDS:
        bucket.popleft()
    if len(bucket) >= limit:
        raise HTTPException(status_code=429, detail="Too many requests, slow down.")
    bucket.append(now)
