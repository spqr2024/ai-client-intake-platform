"""Background task queue with retry + exponential backoff.

Backends: Redis list (durable across restarts, shared between instances)
or an in-process asyncio queue (zero-dependency fallback). Producers call
`enqueue(kind, payload)`; a worker started in the app lifespan dispatches to
registered handlers. A task that raises is retried up to MAX_ATTEMPTS with
backoff, then dead-lettered to the log.

Used for email + Telegram delivery so a provider hiccup never loses a
notification and never blocks a chat response.
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable

from app.core.config import get_settings
from app.core.observability import Timer, metrics, report_error

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 2.0
QUEUE_KEY = "intake:tasks"

Handler = Callable[[dict], Awaitable[None]]

_handlers: dict[str, Handler] = {}
_memory_queue: asyncio.Queue[dict] | None = None
_redis = None
_worker_task: asyncio.Task | None = None
# Strong references to in-flight delayed retries. Without this, asyncio only
# holds a weak reference and the task can be garbage-collected before it runs,
# silently dropping a retry.
_pending_retries: set[asyncio.Task] = set()


def register_handler(kind: str, handler: Handler) -> None:
    _handlers[kind] = handler


def _get_redis():
    global _redis
    if _redis is not None:
        return _redis
    url = get_settings().redis_url
    if not url:
        return None
    try:
        import redis.asyncio as aioredis

        _redis = aioredis.Redis.from_url(url, socket_timeout=3, decode_responses=True)
        return _redis
    except Exception as exc:
        logger.warning("Redis queue unavailable (%s); using in-process queue", exc)
        return None


def _get_memory_queue() -> asyncio.Queue:
    global _memory_queue
    if _memory_queue is None:
        _memory_queue = asyncio.Queue()
    return _memory_queue


async def enqueue(kind: str, payload: dict, delay_seconds: float = 0) -> None:
    task = {"kind": kind, "payload": payload, "attempts": payload.pop("_attempts", 0)}
    if delay_seconds > 0:
        retry_payload = {**payload, "_attempts": task["attempts"]}

        async def _delayed() -> None:
            await asyncio.sleep(delay_seconds)
            await enqueue(kind, retry_payload)

        retry_task = asyncio.create_task(_delayed())
        _pending_retries.add(retry_task)
        retry_task.add_done_callback(_pending_retries.discard)
        return
    redis = _get_redis()
    if redis is not None:
        try:
            await redis.lpush(QUEUE_KEY, json.dumps(task))
            return
        except Exception as exc:
            logger.warning("Redis enqueue failed (%s); using in-process queue", exc)
    await _get_memory_queue().put(task)


async def _pop() -> dict | None:
    redis = _get_redis()
    if redis is not None:
        try:
            item = await redis.brpop(QUEUE_KEY, timeout=1)
            if item:
                return json.loads(item[1])
        except Exception as exc:
            logger.warning("Redis dequeue failed (%s)", exc)
            await asyncio.sleep(1)
        # Also drain the in-process queue in case enqueue fell back mid-flight.
    try:
        return _get_memory_queue().get_nowait()
    except asyncio.QueueEmpty:
        return None


async def _process(task: dict) -> None:
    kind = task.get("kind", "")
    handler = _handlers.get(kind)
    if handler is None:
        logger.error("No handler registered for task kind %r — dropping", kind)
        return
    attempts = int(task.get("attempts", 0)) + 1
    try:
        with Timer("task_duration_seconds", {"kind": kind}):
            await handler(task.get("payload", {}))
        metrics.counter(
            "tasks_processed_total",
            labels={"kind": kind, "result": "success"},
            help_text="Background tasks processed",
        )
    except Exception as exc:
        if attempts >= MAX_ATTEMPTS:
            logger.error("Task %s dead-lettered after %s attempts: %s", kind, attempts, exc)
            metrics.counter("tasks_processed_total", labels={"kind": kind, "result": "dead_letter"})
            report_error(exc, task_kind=kind, attempts=attempts)
            return
        metrics.counter("tasks_processed_total", labels={"kind": kind, "result": "retry"})
        delay = BACKOFF_BASE_SECONDS * (2 ** (attempts - 1))
        logger.warning(
            "Task %s failed (attempt %s/%s), retrying in %.0fs: %s", kind, attempts, MAX_ATTEMPTS, delay, exc
        )
        payload = dict(task.get("payload", {}))
        payload["_attempts"] = attempts
        await enqueue(kind, payload, delay_seconds=delay)


async def worker_loop() -> None:
    logger.info(
        "Task queue worker started (%s backend)", "redis" if _get_redis() is not None else "in-process"
    )
    while True:
        try:
            task = await _pop()
            if task is None:
                await asyncio.sleep(0.5)
                continue
            await _process(task)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Queue worker iteration failed")
            await asyncio.sleep(1)


async def drain_for_tests() -> None:
    """Synchronously process everything in the in-process queue (test helper)."""
    queue = _get_memory_queue()
    while not queue.empty():
        await _process(queue.get_nowait())
