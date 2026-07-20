"""Systemic access control over the whole API surface.

The per-endpoint tests elsewhere check specific routes. These walk every route
the app actually registers, so a new router that forgets its auth dependency
fails here instead of shipping. The backend is the real boundary — the admin UI
guard only decides what to paint.
"""

import pytest

from app.main import app

# Routes that are unauthenticated on purpose.
PUBLIC_PREFIXES = (
    "/api/auth/login",
    "/api/auth/refresh",
    "/api/public",  # branding for the embeddable widget
    "/api/chat",  # the prospect-facing intake conversation
    "/api/webhook",  # authenticated by the Telegram secret, not a user session
    "/health",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
)

# (path, method) pairs that must refuse an anonymous caller.
#
# Enumerated from the OpenAPI schema rather than `app.routes`: recent FastAPI
# keeps included routers nested rather than flattening them into APIRoute, so
# walking `app.routes` yields nothing and the sweep silently passes on zero
# routes.
PROTECTED_ROUTES = sorted(
    {
        (path, method.upper())
        for path, operations in app.openapi()["paths"].items()
        for method in operations
        if method.upper() not in ("HEAD", "OPTIONS") and not path.startswith(PUBLIC_PREFIXES)
    }
)


def _concrete(path: str) -> str:
    """Fill path params with a plausible value; auth is checked before lookup."""
    return path.replace("{lead_id}", "1").replace("{user_id}", "1").replace("{article_id}", "1")


@pytest.mark.parametrize("path,method", PROTECTED_ROUTES)
def test_every_admin_route_refuses_anonymous_callers(client, path, method):
    """No token, no data — including via a directly typed URL."""
    resp = client.request(method, _concrete(path))
    assert resp.status_code in (401, 403), f"{method} {path} answered {resp.status_code} without credentials"


def test_route_inventory_is_not_empty():
    """Guards the guard: a bad filter silently making the sweep vacuous."""
    assert len(PROTECTED_ROUTES) > 20


def test_metrics_endpoints_expose_no_lead_content(client):
    """/metrics is intentionally unauthenticated for Prometheus scraping, so it
    must stay aggregate-only — never client names, emails or lead text."""
    body = client.get("/metrics").text
    for leaked in ("@", "client_name", "client_email"):
        assert leaked not in body, f"/metrics exposed {leaked!r}"
