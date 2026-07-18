def test_kb_crud_and_search(client, auth_headers):
    resp = client.post(
        "/api/kb",
        headers=auth_headers,
        json={
            "title": "Office locations",
            "content": "Our headquarters are in Kyiv, Ukraine. We also have a hub in Warsaw "
            "and work remotely with clients worldwide.",
        },
    )
    assert resp.status_code == 201
    article_id = resp.json()["id"]

    hits = client.get(
        "/api/kb/search", headers=auth_headers, params={"q": "where is your office located"}
    ).json()
    assert any(h["id"] == article_id for h in hits)

    resp = client.put(
        f"/api/kb/{article_id}",
        headers=auth_headers,
        json={"title": "Office locations", "content": "Kyiv only now.", "language": "en"},
    )
    assert resp.status_code == 200

    assert client.delete(f"/api/kb/{article_id}", headers=auth_headers).status_code == 204


def test_chat_answers_from_kb(client, auth_headers):
    client.post(
        "/api/kb",
        headers=auth_headers,
        json={
            "title": "How long does a website project take?",
            "content": "A typical website project takes 4-8 weeks from kickoff to launch.",
        },
    )
    resp = client.post("/api/chat/start", json={"client_name": "Gina"})
    conversation_id = resp.json()["conversation_id"]
    # Ask an off-script FAQ instead of answering the service question.
    body = client.post(
        f"/api/chat/{conversation_id}/msg",
        json={"text": "How long does a typical website project take?"},
    ).json()
    assert "4-8 weeks" in body["bot_message"]
    assert body["done"] is False  # the flow re-asks the pending question


def test_telegram_webhook_accept_flow(client, auth_headers, db_session):
    from app.models import Lead

    lead = Lead(project_name="TG test", client_name="Tess", status="New", score=50)
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    update = {
        "update_id": 1,
        "callback_query": {
            "id": "cb1",
            "from": {"first_name": "Manager"},
            "data": f"accept:{lead.id}",
            "message": {"chat": {"id": 42}},
        },
    }
    resp = client.post("/api/webhook/telegram", json=update)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    detail = client.get(f"/api/leads/{lead.id}", headers=auth_headers).json()
    assert detail["status"] == "In Progress"


def test_telegram_note_command(client, auth_headers, db_session):
    from app.models import Lead

    lead = Lead(project_name="TG note test", status="New")
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    update = {
        "update_id": 2,
        "message": {
            "chat": {"id": 42},
            "from": {"first_name": "Manager"},
            "text": f"/note {lead.id} Very promising, follow up Monday",
        },
    }
    resp = client.post("/api/webhook/telegram", json=update)
    assert resp.status_code == 200

    detail = client.get(f"/api/leads/{lead.id}", headers=auth_headers).json()
    assert any("follow up Monday" in a["detail"] for a in detail["activities"])


def test_telegram_webhook_bad_callback(client):
    update = {"update_id": 3, "callback_query": {"id": "cb2", "data": "accept:not-a-number"}}
    resp = client.post("/api/webhook/telegram", json=update)
    assert resp.status_code == 200
    assert resp.json()["ok"] is False
