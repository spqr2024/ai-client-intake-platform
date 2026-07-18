"""CRM provider registry, adapters, queued export and sync logging."""

import asyncio

import pytest

from app.core import queue
from app.models import Lead
from app.services import crm


class RecordingProvider(crm.CRMProvider):
    """Test double registered through the public registry API — proves a new
    integration needs no changes anywhere else."""

    name = "recording"
    label = "Recording (test)"
    option_keys = ("workspace_key",)

    def __init__(self):
        self.calls: list[dict] = []
        self.fail_times = 0

    async def export_lead(self, lead, config):
        self.calls.append({"lead_id": lead.id, "api_key": config.api_key,
                           "option": config.option("workspace_key")})
        if self.fail_times > 0:
            self.fail_times -= 1
            raise crm.CRMError("temporary upstream failure")
        return crm.CRMResult(external_id=f"ext-{lead.id}",
                             external_url=f"https://crm.example/{lead.id}")


@pytest.fixture()
def recording_provider():
    provider = RecordingProvider()
    crm.register_provider(provider)
    yield provider
    crm.PROVIDERS.pop(provider.name, None)


def test_builtin_providers_are_registered():
    names = {p["name"] for p in crm.available_providers()}
    assert {"hubspot", "pipedrive", "notion", "salesforce", "webhook"} <= names


def test_providers_endpoint(client, auth_headers):
    providers = client.get("/api/crm/providers", headers=auth_headers).json()
    labels = {p["name"]: p for p in providers}
    assert labels["notion"]["option_keys"] == ["database_id"]
    assert labels["hubspot"]["option_keys"] == []


def test_lead_payload_is_provider_independent():
    lead = Lead(id=7, project_name="Store build", client_name="Ada Lovelace",
                client_email="ada@example.com", service="Online store", budget=5000,
                timeline="ASAP", status="Qualified", priority="High", score=88,
                tags=["vip"], summary="Wants a store")
    payload = crm.CRMProvider.lead_payload(lead)
    assert payload["first_name"] == "Ada"
    assert payload["last_name"] == "Lovelace"
    assert payload["budget"] == 5000
    assert payload["tags"] == ["vip"]


def test_export_is_skipped_without_configuration(client, auth_headers, db_session):
    lead = Lead(workspace_id=1, project_name="No CRM configured", status="Qualified")
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    resp = client.post(f"/api/crm/leads/{lead.id}/export", headers=auth_headers)
    assert resp.status_code == 409
    assert "No CRM provider configured" in resp.json()["detail"]


def test_export_queues_and_records_sync(client, auth_headers, db_session, recording_provider):
    client.put("/api/settings", headers=auth_headers, json={"values": {
        "crm_provider": "recording", "crm_api_key": "secret-key",
        "crm_option_workspace_key": "ws-1", "crm_export_on": "qualified",
    }})

    lead = Lead(workspace_id=1, project_name="Export me", status="Qualified", score=90)
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    resp = client.post(f"/api/crm/leads/{lead.id}/export", headers=auth_headers)
    assert resp.status_code == 202
    assert resp.json()["status"] == "pending"

    asyncio.run(queue.drain_for_tests())

    syncs = client.get("/api/crm/syncs", headers=auth_headers).json()
    entry = next(s for s in syncs if s["lead_id"] == lead.id)
    assert entry["status"] == "synced"
    assert entry["external_id"] == f"ext-{lead.id}"
    assert entry["external_url"].endswith(str(lead.id))
    assert recording_provider.calls[0]["api_key"] == "secret-key"
    assert recording_provider.calls[0]["option"] == "ws-1"

    # Reset so later tests don't export.
    client.put("/api/settings", headers=auth_headers,
               json={"values": {"crm_provider": "", "crm_export_on": "off"}})


def test_failed_export_is_retried_then_marked_failed(client, auth_headers, db_session,
                                                     recording_provider):
    client.put("/api/settings", headers=auth_headers, json={"values": {
        "crm_provider": "recording", "crm_api_key": "k", "crm_export_on": "qualified",
    }})
    recording_provider.fail_times = 99  # always fail

    lead = Lead(workspace_id=1, project_name="Fails to export", status="Qualified")
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    client.post(f"/api/crm/leads/{lead.id}/export", headers=auth_headers)

    async def drain_with_retries():
        for _ in range(queue.MAX_ATTEMPTS):
            await queue.drain_for_tests()
            await asyncio.sleep(0)

    asyncio.run(drain_with_retries())

    syncs = client.get("/api/crm/syncs", headers=auth_headers).json()
    entry = next(s for s in syncs if s["lead_id"] == lead.id)
    assert entry["attempts"] >= 1
    assert entry["error"]

    client.put("/api/settings", headers=auth_headers,
               json={"values": {"crm_provider": "", "crm_export_on": "off"}})


def test_export_requires_admin(client, auth_headers, db_session):
    client.post("/api/users", headers=auth_headers,
                json={"name": "Cm", "email": "cm@example.org", "password": "secret123",
                      "role": "manager"})
    login = client.post("/api/auth/login",
                        json={"email": "cm@example.org", "password": "secret123"})
    manager_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    lead = Lead(workspace_id=1, project_name="RBAC check", status="Qualified")
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    assert client.post(f"/api/crm/leads/{lead.id}/export",
                       headers=manager_headers).status_code == 403
    # Managers may still read the sync log.
    assert client.get("/api/crm/syncs", headers=manager_headers).status_code == 200
