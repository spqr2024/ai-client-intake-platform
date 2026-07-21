"""Visual workflow builder support, demo provisioning, pagination and attachments."""

import io

from app.demo import provision_demo_workspace
from app.models import Lead, Workspace
from app.services import workflow_templates


# ── Workflow builder ─────────────────────────────────────────────────────
def test_templates_endpoint_offers_starters_and_library(client, auth_headers):
    body = client.get("/api/workflows/templates", headers=auth_headers).json()
    keys = {t["key"] for t in body["templates"]}
    assert {"agency", "law", "clinic", "saas_demo", "blank"} <= keys
    assert all(t["definition"]["nodes"] for t in body["templates"])
    assert any(n["key"] == "budget" for n in body["node_library"])
    assert "email" in body["field_types"]


def test_analyze_detects_unreachable_and_missing_end():
    definition = {
        "start": "a",
        "nodes": {
            "a": {"field": "a", "prompt": {"en": "A?"}, "next": "b"},
            "b": {"field": "b", "prompt": {"en": "B?"}, "next": ""},
            "orphan": {"field": "o", "prompt": {"en": "Never asked?"}, "next": ""},
        },
    }
    report = workflow_templates.analyze(definition)
    assert report["unreachable"] == ["orphan"]
    assert "b" in report["terminal_nodes"]
    assert not report["has_cycle"]
    assert any("never be reached" in w for w in report["warnings"])


def test_analyze_detects_cycles_and_missing_prompt():
    definition = {
        "start": "a",
        "nodes": {
            "a": {"field": "a", "prompt": {"en": "A?"}, "next": "b"},
            "b": {"field": "b", "prompt": {"en": ""}, "next": "a"},
        },
    }
    report = workflow_templates.analyze(definition)
    assert report["has_cycle"] is True
    assert any("loop" in w for w in report["warnings"])
    assert any("no question text" in w for w in report["warnings"])


def test_analyze_endpoint(client, auth_headers):
    resp = client.post(
        "/api/workflows/analyze",
        headers=auth_headers,
        json={"definition": workflow_templates.TEMPLATES[0]["definition"]},
    )
    assert resp.status_code == 200
    assert resp.json()["unreachable"] == []


def test_simulate_replays_a_flow(client, auth_headers):
    definition = workflow_templates.TEMPLATES[0]["definition"]
    resp = client.post(
        "/api/workflows/simulate",
        headers=auth_headers,
        json={
            "definition": definition,
            "answers": [
                "Alice",
                "Online store",
                "Shopify",
                "Sell candles across the EU",
                "$5000",
                "1-3 months",
                "Email",
                "alice@example.com",
                "no",
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["done"] is True
    assert body["collected"]["budget"] == 5000
    assert body["collected"]["client_email"] == "alice@example.com"
    assert any(m["sender"] == "bot" for m in body["transcript"])


def test_simulate_rejects_broken_definition(client, auth_headers):
    resp = client.post(
        "/api/workflows/simulate",
        headers=auth_headers,
        json={"definition": {"start": "missing", "nodes": {}}, "answers": []},
    )
    assert resp.status_code == 422


def test_builder_can_save_a_template_flow(client, auth_headers):
    template = next(t for t in workflow_templates.TEMPLATES if t["key"] == "clinic")
    resp = client.post(
        "/api/workflows",
        headers=auth_headers,
        json={
            "name": "Clinic intake (test)",
            "definition": template["definition"],
            "is_default": False,
            "prompt_name": "",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Clinic intake (test)"


# ── Demo provisioning ────────────────────────────────────────────────────
def test_demo_provisioning_populates_and_is_idempotent(db_session):
    workspace = Workspace(name="Demo Co", slug="demo-co")
    db_session.add(workspace)
    db_session.commit()
    db_session.refresh(workspace)

    assert provision_demo_workspace(db_session, workspace.id) is True
    leads = db_session.query(Lead).filter_by(workspace_id=workspace.id).all()
    assert len(leads) >= 10
    assert {lead.status for lead in leads} >= {"Qualified", "Converted", "New"}
    assert any(lead.tags and "vip" in lead.tags for lead in leads)
    assert all(lead.summary for lead in leads if lead.status != "Incomplete")
    assert any(lead.language == "uk" for lead in leads)
    assert any(lead.follow_up_at is not None for lead in leads)
    # The seeded pipeline showcases all three intake contact channels.
    assert {lead.contact_method for lead in leads} >= {"email", "telegram", "phone"}
    assert all(lead.contact_value for lead in leads if lead.contact_method)

    # Running again must not duplicate anything.
    assert provision_demo_workspace(db_session, workspace.id) is False
    assert len(db_session.query(Lead).filter_by(workspace_id=workspace.id).all()) == len(leads)


# ── Pagination ───────────────────────────────────────────────────────────
def test_lead_list_is_paginated_with_total_header(client, auth_headers):
    resp = client.get("/api/leads", headers=auth_headers, params={"limit": 2, "offset": 0})
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)  # contract preserved: still a plain array
    assert len(body) <= 2
    total = int(resp.headers["X-Total-Count"])
    assert total >= len(body)

    if total > 2:
        page_two = client.get("/api/leads", headers=auth_headers, params={"limit": 2, "offset": 2}).json()
        assert {lead["id"] for lead in page_two}.isdisjoint({lead["id"] for lead in body})


def test_total_count_respects_filters(client, auth_headers):
    filtered = client.get("/api/leads", headers=auth_headers, params={"status": "Qualified", "limit": 1})
    total = int(filtered.headers["X-Total-Count"])
    unfiltered_total = int(
        client.get("/api/leads", headers=auth_headers, params={"limit": 1}).headers["X-Total-Count"]
    )
    assert total <= unfiltered_total


# ── Attachments ──────────────────────────────────────────────────────────
def test_attachment_upload_and_authenticated_download(client, auth_headers):
    start = client.post("/api/chat/start", json={"client_name": "Attach Tester"}).json()
    conversation_id = start["conversation_id"]

    upload = client.post(
        f"/api/chat/{conversation_id}/upload",
        files={"file": ("brief.txt", io.BytesIO(b"Project brief contents"), "text/plain")},
    )
    assert upload.status_code == 201
    attachment_id = upload.json()["id"]

    # Staff-only: anonymous access is rejected.
    assert client.get(f"/api/chat/attachments/{attachment_id}").status_code == 401

    download = client.get(f"/api/chat/attachments/{attachment_id}", headers=auth_headers)
    assert download.status_code == 200
    assert download.content == b"Project brief contents"
    assert download.headers["X-Content-Type-Options"] == "nosniff"


def test_attachment_download_is_workspace_scoped(client, auth_headers, db_session):
    from app.core.security import hash_password
    from app.models import User

    other = db_session.query(Workspace).filter_by(slug="other-ws").first()
    if other is None:
        other = Workspace(name="Other", slug="other-ws")
        db_session.add(other)
        db_session.flush()
        db_session.add(
            User(
                workspace_id=other.id,
                name="Other Admin",
                email="admin@other-ws.example",
                password_hash=hash_password("other-pass-1"),
                role="admin",
            )
        )
        db_session.commit()

    start = client.post("/api/chat/start", json={"client_name": "Scoped"}).json()
    upload = client.post(
        f"/api/chat/{start['conversation_id']}/upload",
        files={"file": ("secret.txt", io.BytesIO(b"tenant data"), "text/plain")},
    ).json()

    login = client.post(
        "/api/auth/login", json={"email": "admin@other-ws.example", "password": "other-pass-1"}
    )
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get(f"/api/chat/attachments/{upload['id']}", headers=other_headers).status_code == 404
