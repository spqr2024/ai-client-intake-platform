import pytest


@pytest.fixture()
def lead_id(client, auth_headers):
    resp = client.post("/api/chat/start", json={"client_name": "Frank", "email": "frank@x.co"})
    conversation_id = resp.json()["conversation_id"]
    for answer in ["Website", "Company site for a bakery", "$3000", "Within 1 month", "no"]:
        last = client.post(f"/api/chat/{conversation_id}/msg", json={"text": answer}).json()
    return last["lead_id"]


def test_list_and_filter_leads(client, auth_headers, lead_id):
    all_leads = client.get("/api/leads", headers=auth_headers).json()
    assert any(lead["id"] == lead_id for lead in all_leads)

    filtered = client.get("/api/leads", headers=auth_headers, params={"search": "Frank"}).json()
    assert all("frank" in (lead["client_name"] + lead["project_name"]).lower() for lead in filtered)
    assert filtered


def test_update_status_logs_activity(client, auth_headers, lead_id):
    resp = client.patch(f"/api/leads/{lead_id}", headers=auth_headers, json={"status": "In Progress"})
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["status"] == "In Progress"
    assert any("In Progress" in a["detail"] for a in detail["activities"])


def test_add_note(client, auth_headers, lead_id):
    resp = client.post(
        f"/api/leads/{lead_id}/notes", headers=auth_headers, json={"text": "Called, very interested"}
    )
    assert resp.status_code == 201
    assert resp.json()["action"] == "note"


def test_invalid_status_rejected(client, auth_headers, lead_id):
    resp = client.patch(f"/api/leads/{lead_id}", headers=auth_headers, json={"status": "TotallyBogus"})
    assert resp.status_code == 422


def test_analytics_summary(client, auth_headers):
    resp = client.get("/api/analytics/summary", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_leads"] >= 1
    assert "leads_by_status" in body
    assert 0 <= body["conversion_rate"] <= 1
