"""Multi-tenant isolation: workspaces cannot see each other's data."""

import pytest

from app.core.security import hash_password
from app.models import Lead, User, Workspace


@pytest.fixture()
def second_workspace(client, db_session):
    workspace = db_session.query(Workspace).filter_by(slug="acme").first()
    if workspace is None:
        workspace = Workspace(name="Acme Corp", slug="acme")
        db_session.add(workspace)
        db_session.flush()
        db_session.add(
            User(
                workspace_id=workspace.id,
                name="Acme Admin",
                email="admin@acme-corp.com",
                password_hash=hash_password("acme-secret-1"),
                role="admin",
            )
        )
        db_session.add(Lead(workspace_id=workspace.id, project_name="Acme private lead"))
        db_session.commit()
    return workspace


@pytest.fixture()
def acme_headers(client, second_workspace):
    resp = client.post("/api/auth/login", json={"email": "admin@acme-corp.com", "password": "acme-secret-1"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_leads_are_workspace_isolated(client, auth_headers, acme_headers, second_workspace):
    default_leads = client.get("/api/leads", headers=auth_headers).json()
    acme_leads = client.get("/api/leads", headers=acme_headers).json()

    assert all(lead["project_name"] != "Acme private lead" for lead in default_leads)
    assert any(lead["project_name"] == "Acme private lead" for lead in acme_leads)
    assert all(lead["project_name"] == "Acme private lead" for lead in acme_leads)


def test_cross_workspace_lead_access_denied(client, auth_headers, acme_headers, db_session):
    acme_lead = db_session.query(Lead).filter_by(project_name="Acme private lead").first()
    resp = client.get(f"/api/leads/{acme_lead.id}", headers=auth_headers)
    assert resp.status_code == 404  # not 403: existence is not leaked


def test_settings_are_workspace_scoped(client, auth_headers, acme_headers):
    resp = client.put(
        "/api/settings",
        headers=acme_headers,
        json={"values": {"brand_company_name": "Acme Corp"}},
    )
    assert resp.status_code == 200
    assert resp.json()["values"]["brand_company_name"] == "Acme Corp"

    default_settings = client.get("/api/settings", headers=auth_headers).json()
    assert default_settings["values"]["brand_company_name"] != "Acme Corp"


def test_chat_start_resolves_workspace_slug(client, acme_headers, second_workspace):
    resp = client.post("/api/chat/start", json={"client_name": "Visitor", "workspace": "acme"})
    assert resp.status_code == 200
    conversation_id = resp.json()["conversation_id"]
    for answer in ["Website", "Small site", "$1000", "Flexible", "v@acme.io", "no"]:
        last = client.post(f"/api/chat/{conversation_id}/msg", json={"text": answer}).json()
    assert last["done"]

    acme_leads = client.get("/api/leads", headers=acme_headers).json()
    assert any(lead["client_name"] == "Visitor" for lead in acme_leads)


def test_public_branding_endpoint(client, auth_headers):
    client.put("/api/settings", headers=auth_headers, json={"values": {"brand_bot_name": "Helper Bot"}})
    resp = client.get("/api/public/branding", params={"workspace": "default"})
    assert resp.status_code == 200
    assert resp.json()["bot_name"] == "Helper Bot"


def test_users_listing_workspace_scoped(client, acme_headers):
    users = client.get("/api/users", headers=acme_headers).json()
    assert all(user["email"].endswith("@acme-corp.com") for user in users)
