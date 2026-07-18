"""Cache abstraction: Redis when REDIS_URL is configured and reachable,
in-process memory otherwise. Consumers never talk to Redis directly, so the
whole application keeps working when Redis is absent (single-instance mode).

Used for: rate limiting, login lockout counters, analytics caching, and
short-lived AI context. Multi-replica deployments should set REDIS_URL so
these become cluster-wide.
"""

import json
import logging
import threading
import time
from typing import Any, Protocol

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class CacheBackend(Protocol):
    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None: ...
    def delete(self, key: str) -> None: ...
    def incr_window(self, key: str, window_seconds: int) -> int:
        """Increment a counter that expires `window_seconds` after first hit;
        returns the new count. Basis for rate limiting / lockouts."""
        ...


class MemoryCache:
    def __init__(self) -> None:
        self._data: dict[str, tuple[Any, float | None]] = {}
        self._lock = threading.Lock()

    def _purge(self, key: str) -> None:
        item = self._data.get(key)
        if item and item[1] is not None and item[1] < time.monotonic():
            del self._data[key]

    def get(self, key: str) -> Any | None:
        with self._lock:
            self._purge(key)
            item = self._data.get(key)
            return item[0] if item else None

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        expires = time.monotonic() + ttl_seconds if ttl_seconds else None
        with self._lock:
            self._data[key] = (value, expires)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def incr_window(self, key: str, window_seconds: int) -> int:
        with self._lock:
            self._purge(key)
            item = self._data.get(key)
            if item is None:
                self._data[key] = (1, time.monotonic() + window_seconds)
                return 1
            count = int(item[0]) + 1
            self._data[key] = (count, item[1])
            return count


class RedisCache:
    def __init__(self, url: str) -> None:
        import redis  # imported lazily: optional dependency

        self._redis = redis.Redis.from_url(url, socket_timeout=2, decode_responses=True)
        self._redis.ping()

    def get(self, key: str) -> Any | None:
        raw = self._redis.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        self._redis.set(key, json.dumps(value), ex=ttl_seconds)

    def delete(self, key: str) -> None:
        self._redis.delete(key)

    def incr_window(self, key: str, window_seconds: int) -> int:
        pipe = self._redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_seconds, nx=True)
        count, _ = pipe.execute()
        return int(count)


_cache: CacheBackend | None = None
_cache_lock = threading.Lock()


def get_cache() -> CacheBackend:
    global _cache
    if _cache is not None:
        return _cache
    with _cache_lock:
        if _cache is not None:
            return _cache
        url = get_settings().redis_url
        if url:
            try:
                _cache = RedisCache(url)
                logger.info("Cache backend: Redis (%s)", url.split("@")[-1])
                return _cache
            except Exception as exc:  # noqa: BLE001 — any failure falls back
                logger.warning("Redis unavailable (%s); using in-memory cache", exc)
        _cache = MemoryCache()
        logger.info("Cache backend: in-memory (set REDIS_URL for multi-instance deployments)")
        return _cache


def reset_cache_for_tests() -> None:
    global _cache
    _cache = None
