"""Structured logging, health/readiness probes, metrics and error reporting."""

import io
import json
import logging

from app.core.logging import JsonFormatter, request_id_var
from app.core.observability import MetricsRegistry, report_error, set_error_reporter


def _capture(record_factory) -> str:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("test.json")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    record_factory(logger)
    return stream.getvalue().strip()


def test_log_line_with_quotes_is_valid_json():
    """Regression: the previous format string produced invalid JSON whenever a
    message contained a double quote (every httpx access log does)."""
    line = _capture(lambda log: log.info('HTTP Request: POST /api/kb "HTTP/1.1 201 Created"'))
    payload = json.loads(line)  # would raise before the fix
    assert payload["message"] == 'HTTP Request: POST /api/kb "HTTP/1.1 201 Created"'
    assert payload["level"] == "INFO"


def test_log_includes_extra_fields_and_request_id():
    request_id_var.set("req-123")
    try:
        line = _capture(lambda log: log.info("Lead created", extra={"lead_id": 42}))
    finally:
        request_id_var.set("")
    payload = json.loads(line)
    assert payload["lead_id"] == 42
    assert payload["request_id"] == "req-123"


def test_log_serializes_exceptions():
    def emit(log):
        try:
            raise ValueError('boom "quoted"')
        except ValueError:
            log.exception("Something failed")

    payload = json.loads(_capture(emit))
    assert "ValueError" in payload["exception"]


def test_metrics_registry_counters_and_histograms():
    registry = MetricsRegistry()
    registry.counter("http_requests_total", labels={"status": "200"})
    registry.counter("http_requests_total", labels={"status": "200"})
    registry.counter("http_requests_total", labels={"status": "500"})
    registry.observe("latency_seconds", 0.05)
    registry.observe("latency_seconds", 0.5)
    registry.gauge("uptime_seconds", 12.5)

    snapshot = registry.snapshot()
    assert snapshot["counters"]["http_requests_total{'status': '200'}"] == 2
    assert snapshot["histograms"]["latency_seconds"]["count"] == 2

    exposition = registry.render_prometheus()
    assert "# TYPE http_requests_total counter" in exposition
    assert 'http_requests_total{status="200"} 2' in exposition
    assert "latency_seconds_bucket" in exposition
    assert "latency_seconds_count" in exposition


def test_error_reporter_seam():
    captured = []
    set_error_reporter(lambda exc, ctx: captured.append((str(exc), ctx)))
    try:
        report_error(ValueError("kaboom"), component="test")
        assert captured[0][0] == "kaboom"
        assert captured[0][1]["component"] == "test"

        # A broken reporter must never propagate into request handling.
        def broken(exc, ctx):
            raise RuntimeError("reporter is down")

        set_error_reporter(broken)
        report_error(ValueError("still fine"))
    finally:
        from app.core.observability import _default_reporter

        set_error_reporter(_default_reporter)


def test_liveness_is_dependency_free(client):
    resp = client.get("/health/live")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "alive"
    assert body["uptime_seconds"] >= 0


def test_readiness_reports_dependencies(client):
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"]["ok"] is True
    assert "cache" in body["checks"]


def test_health_backwards_compatible(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["database"] is True


def test_metrics_endpoint_exposes_request_metrics(client):
    client.get("/api/public/branding")
    exposition = client.get("/metrics").text
    assert "http_requests_total" in exposition
    assert "http_request_duration_seconds_bucket" in exposition


def test_request_id_header_roundtrip(client):
    resp = client.get("/health", headers={"X-Request-ID": "trace-me-42"})
    assert resp.headers["X-Request-ID"] == "trace-me-42"
    # Absent header → generated id.
    assert client.get("/health").headers["X-Request-ID"]
