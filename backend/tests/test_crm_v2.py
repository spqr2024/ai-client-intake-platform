"""CRM upgrade: pipeline/kanban, tags, priority, follow-ups, custom statuses,
comments and conversation replay."""

import pytest


@pytest.fixture()
def lead_id(client):
    resp = client.post("/api/chat/start", json={"client_name": "Kim", "email": "kim@x.co"})
    conversation_id = resp.json()["conversation_id"]
    for answer in ["Website", "Portfolio refresh for my studio", "$3500", "ASAP", "no"]:
        last = client.post(f"/api/chat/{conversation_id}/msg", json={"text": answer}).json()
    return last["lead_id"]


def test_pipeline_endpoint_groups_by_status(client, auth_headers, lead_id):
    resp = client.get("/api/leads/pipeline", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "New" in body["statuses"] and "Qualified" in body["statuses"]
    all_ids = [lead["id"] for column in body["columns"].values() for lead in column]
    assert lead_id in all_ids


def test_tags_priority_followup(client, auth_headers, lead_id):
    resp = client.patch(
        f"/api/leads/{lead_id}", headers=auth_headers,
        json={
            "tags": ["vip", "design"],
            "priority": "Urgent",
            "follow_up_at": "2026-08-01T10:00:00Z",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tags"] == ["vip", "design"]
    assert body["priority"] == "Urgent"
    assert body["follow_up_at"] is not None

    filtered = client.get("/api/leads", headers=auth_headers, params={"tag": "vip"}).json()
    assert any(lead["id"] == lead_id for lead in filtered)
    filtered = client.get("/api/leads", headers=auth_headers, params={"priority": "Urgent"}).json()
    assert any(lead["id"] == lead_id for lead in filtered)

    resp = client.patch(f"/api/leads/{lead_id}", headers=auth_headers,
                        json={"clear_follow_up": True})
    assert resp.json()["follow_up_at"] is None


def test_custom_pipeline_statuses(client, auth_headers, lead_id):
    # Add a custom stage to the workspace pipeline, then use it.
    client.put(
        "/api/settings", headers=auth_headers,
        json={"values": {"pipeline_statuses":
                         "New,Qualified,In Progress,Proposal Sent,Converted,Rejected,Closed,Incomplete"}},
    )
    resp = client.patch(f"/api/leads/{lead_id}", headers=auth_headers,
                        json={"status": "Proposal Sent"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "Proposal Sent"

    resp = client.patch(f"/api/leads/{lead_id}", headers=auth_headers,
                        json={"status": "Not A Stage"})
    assert resp.status_code == 422


def test_internal_comment(client, auth_headers, lead_id):
    resp = client.post(
        f"/api/leads/{lead_id}/notes", headers=auth_headers,
        json={"text": "Discussed scope on call", "kind": "comment"},
    )
    assert resp.status_code == 201
    assert resp.json()["action"] == "comment"


def test_replay_timeline(client, auth_headers, lead_id):
    resp = client.get(f"/api/leads/{lead_id}/replay", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["conversation_id"]
    events = body["events"]
    assert len(events) >= 10
    # Chronological order with metadata for replay.
    timestamps = [e["at"] for e in events]
    assert timestamps == sorted(timestamps)
    message_events = [e for e in events if e["type"] == "message"]
    assert any(e["meta"].get("event") == "summary" for e in message_events)
    assert any(e["meta"].get("node") for e in message_events)
    assert any(e["type"] == "activity" for e in events)


def test_search_includes_summary(client, auth_headers, lead_id):
    hits = client.get("/api/leads", headers=auth_headers,
                      params={"search": "Portfolio refresh"}).json()
    assert any(lead["id"] == lead_id for lead in hits)
