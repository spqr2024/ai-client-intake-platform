"""Vendor-neutral observability primitives.

Two deliberately small abstractions so the application never imports a
monitoring vendor:

* `metrics` — an in-process registry of counters/gauges/histograms with a
  Prometheus *text exposition* renderer. Prometheus/Grafana can scrape
  `/metrics` today with zero dependencies; swapping in `prometheus_client`,
  StatsD or OpenTelemetry means reimplementing this one class.
* `report_error` — an error-reporting seam. The default sink logs; wiring
  Sentry (or any other service) is `set_error_reporter(fn)` in one place,
  with no call-site changes.
"""

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

# Buckets in seconds — HTTP and LLM latencies both land inside this range.
DEFAULT_BUCKETS = (0.005, 0.025, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

Labels = tuple[tuple[str, str], ...]


def _freeze(labels: dict[str, str] | None) -> Labels:
    return tuple(sorted((labels or {}).items()))


class MetricsRegistry:
    """Minimal, thread-safe metrics registry with Prometheus rendering."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[tuple[str, Labels], float] = {}
        self._gauges: dict[tuple[str, Labels], float] = {}
        self._histograms: dict[tuple[str, Labels], list[float]] = {}
        self._help: dict[str, str] = {}

    def counter(self, name: str, value: float = 1, labels: dict[str, str] | None = None,
                help_text: str = "") -> None:
        with self._lock:
            self._help.setdefault(name, help_text or name)
            self._counters[(name, _freeze(labels))] = (
                self._counters.get((name, _freeze(labels)), 0.0) + value
            )

    def gauge(self, name: str, value: float, labels: dict[str, str] | None = None,
              help_text: str = "") -> None:
        with self._lock:
            self._help.setdefault(name, help_text or name)
            self._gauges[(name, _freeze(labels))] = value

    def observe(self, name: str, value: float, labels: dict[str, str] | None = None,
                help_text: str = "") -> None:
        with self._lock:
            self._help.setdefault(name, help_text or name)
            self._histograms.setdefault((name, _freeze(labels)), []).append(value)

    def snapshot(self) -> dict[str, Any]:
        """Machine-readable view (used by tests and the ops dashboard)."""
        with self._lock:
            return {
                "counters": {f"{n}{dict(lbl) or ''}": v for (n, lbl), v in self._counters.items()},
                "gauges": {f"{n}{dict(lbl) or ''}": v for (n, lbl), v in self._gauges.items()},
                "histograms": {
                    f"{n}{dict(lbl) or ''}": {
                        "count": len(v),
                        "sum": round(sum(v), 6),
                        "avg": round(sum(v) / len(v), 6) if v else 0.0,
                    }
                    for (n, lbl), v in self._histograms.items()
                },
            }

    def render_prometheus(self) -> str:
        """Prometheus text exposition format (v0.0.4)."""
        lines: list[str] = []
        with self._lock:
            for metric_type, store in (("counter", self._counters), ("gauge", self._gauges)):
                names = {name for name, _ in store}
                for name in sorted(names):
                    lines.append(f"# HELP {name} {self._help.get(name, name)}")
                    lines.append(f"# TYPE {name} {metric_type}")
                    for (metric_name, labels), value in sorted(store.items()):
                        if metric_name == name:
                            lines.append(f"{name}{_render_labels(labels)} {value}")

            histogram_names = {name for name, _ in self._histograms}
            for name in sorted(histogram_names):
                lines.append(f"# HELP {name} {self._help.get(name, name)}")
                lines.append(f"# TYPE {name} histogram")
                for (metric_name, labels), values in sorted(self._histograms.items()):
                    if metric_name != name:
                        continue
                    cumulative = 0
                    ordered = sorted(values)
                    for bucket in DEFAULT_BUCKETS:
                        cumulative = sum(1 for v in ordered if v <= bucket)
                        lines.append(
                            f"{name}_bucket{_render_labels(labels, le=str(bucket))} {cumulative}"
                        )
                    lines.append(f"{name}_bucket{_render_labels(labels, le='+Inf')} {len(ordered)}")
                    lines.append(f"{name}_sum{_render_labels(labels)} {round(sum(ordered), 6)}")
                    lines.append(f"{name}_count{_render_labels(labels)} {len(ordered)}")
        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()


def _render_labels(labels: Labels, **extra: str) -> str:
    items = list(labels) + list(extra.items())
    if not items:
        return ""
    rendered = ",".join(f'{k}="{str(v)}"' for k, v in items)
    return "{" + rendered + "}"


metrics = MetricsRegistry()


class Timer:
    """Context manager recording elapsed seconds into a histogram."""

    def __init__(self, name: str, labels: dict[str, str] | None = None):
        self._name = name
        self._labels = labels
        self._start = 0.0

    def __enter__(self) -> "Timer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc_info) -> None:
        metrics.observe(self._name, time.perf_counter() - self._start, self._labels)


# ── Error reporting seam ─────────────────────────────────────────────────
ErrorReporter = Callable[[BaseException, dict], None]


def _default_reporter(exc: BaseException, context: dict) -> None:
    logger.error("Unhandled error: %s", exc, exc_info=exc, extra={"error_context": context})


_reporter: ErrorReporter = _default_reporter


def set_error_reporter(reporter: ErrorReporter) -> None:
    """Install an external reporter, e.g.:

        import sentry_sdk
        set_error_reporter(lambda exc, ctx: sentry_sdk.capture_exception(exc))
    """
    global _reporter
    _reporter = reporter


def report_error(exc: BaseException, **context) -> None:
    try:
        _reporter(exc, context)
    except Exception:  # noqa: BLE001 — reporting must never raise into request flow
        logger.exception("Error reporter itself failed")
