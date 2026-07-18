def _run_chat(client, answers, start_body=None):
    resp = client.post("/api/chat/start", json=start_body or {})
    assert resp.status_code == 200, resp.text
    conversation_id = resp.json()["conversation_id"]
    last = resp.json()
    for answer in answers:
        resp = client.post(f"/api/chat/{conversation_id}/msg", json={"text": answer})
        assert resp.status_code == 200, resp.text
        last = resp.json()
    return conversation_id, last


def test_full_chat_creates_qualified_lead(client, auth_headers):
    _, last = _run_chat(
        client,
        [
            "Alice Johnson",
            "Online store",
            "Shopify",
            "I want to sell handmade jewelry across Europe, around 200 products",
            "$5000",
            "1-3 months",
            "alice@example.com",
            "No, that's all",
        ],
    )
    assert last["done"] is True
    assert last["lead_id"] is not None
    assert "$5,000" in last["summary"] or "5000" in last["summary"].replace(",", "")

    detail = client.get(f"/api/leads/{last['lead_id']}", headers=auth_headers).json()
    assert detail["client_name"] == "Alice Johnson"
    assert detail["client_email"] == "alice@example.com"
    assert detail["budget"] == 5000
    assert detail["status"] == "Qualified"
    assert detail["score"] >= 60
    assert len(detail["messages"]) >= 10  # full transcript stored


def test_prefilled_contact_skips_questions(client):
    resp = client.post(
        "/api/chat/start", json={"client_name": "Bob", "email": "bob@x.co"}
    )
    body = resp.json()
    # Name question skipped, goes straight to service selection.
    assert "service" in body["bot_message"].lower()
    assert body["quick_replies"]


def test_ukrainian_conversation(client, auth_headers):
    _, last = _run_chat(
        client,
        [
            "Катерина",
            "Вебсайт",
            "Сайт для салону краси з онлайн-записом",
            "$2000",
            "Якнайшвидше",
            "kate@example.ua",
            "Ні, це все",
        ],
    )
    assert last["done"] is True
    detail = client.get(f"/api/leads/{last['lead_id']}", headers=auth_headers).json()
    assert detail["language"] == "uk"
    assert detail["budget"] == 2000


def test_human_handoff_ends_chat(client, auth_headers):
    conversation_id, last = _run_chat(client, ["Charlie", "talk to a person please"])
    assert last["done"] is True
    assert last["lead_id"] is not None
    # Conversation is finished; further messages are rejected.
    resp = client.post(f"/api/chat/{conversation_id}/msg", json={"text": "hello?"})
    assert resp.status_code == 409


def test_sse_stream_endpoint(client):
    resp = client.post("/api/chat/start", json={"client_name": "Dana"})
    conversation_id = resp.json()["conversation_id"]
    with client.stream(
        "GET", f"/api/chat/{conversation_id}/stream", params={"text": "Mobile app"}
    ) as stream:
        assert stream.status_code == 200
        content = "".join(chunk for chunk in stream.iter_text())
    assert "event: delta" in content
    assert "event: meta" in content


def test_unknown_conversation_404(client):
    assert client.post("/api/chat/nope/msg", json={"text": "hi"}).status_code == 404


def test_html_is_sanitized(client, auth_headers):
    _, last = _run_chat(
        client,
        [
            "<script>alert(1)</script>Eve",
            "Website",
            "Simple portfolio",
            "$1000",
            "Flexible",
            "eve@example.com",
            "no",
        ],
    )
    detail = client.get(f"/api/leads/{last['lead_id']}", headers=auth_headers).json()
    assert "<script>" not in detail["client_name"]
    assert "Eve" in detail["client_name"]
