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
            "Email",
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
    assert detail["contact_method"] == "email"
    assert detail["contact_value"] == "alice@example.com"
    assert detail["budget"] == 5000
    assert detail["status"] == "Qualified"
    assert detail["score"] >= 60
    assert len(detail["messages"]) >= 10  # full transcript stored


def test_client_can_choose_telegram_as_the_channel(client, auth_headers):
    """Picking Telegram asks for a handle and records it as the preferred
    contact — with no email captured."""
    _, last = _run_chat(
        client,
        [
            "Dana",
            "Website",
            "A landing page for my studio",
            "$2000",
            "Flexible",
            "Telegram",
            "dana_dev",  # bare handle → normalized to @dana_dev
            "no",
        ],
    )
    detail = client.get(f"/api/leads/{last['lead_id']}", headers=auth_headers).json()
    assert detail["contact_method"] == "telegram"
    assert detail["contact_value"] == "@dana_dev"
    assert detail["client_email"] == ""


def test_client_can_choose_phone_as_the_channel(client, auth_headers):
    _, last = _run_chat(
        client,
        [
            "Sam",
            "Mobile app",
            "A fitness tracker",
            "$10000",
            "1-3 months",
            "Phone",
            "+1 415 555 0142",
            "no",
        ],
    )
    detail = client.get(f"/api/leads/{last['lead_id']}", headers=auth_headers).json()
    assert detail["contact_method"] == "phone"
    assert detail["contact_value"] == "+1 415 555 0142"
    assert detail["client_phone"] == "+1 415 555 0142"


def test_prefilled_contact_skips_questions(client):
    resp = client.post("/api/chat/start", json={"client_name": "Bob", "email": "bob@x.co"})
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
            "Email",
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
    with client.stream("GET", f"/api/chat/{conversation_id}/stream", params={"text": "Mobile app"}) as stream:
        assert stream.status_code == 200
        content = "".join(chunk for chunk in stream.iter_text())
    assert "event: delta" in content
    assert "event: meta" in content


def test_unknown_conversation_404(client):
    assert client.post("/api/chat/nope/msg", json={"text": "hi"}).status_code == 404


def test_upgrade_default_workflow_patches_unmodified_seed(client, db_session, other_workspace_id):
    """An existing database seeded before the contact step gets upgraded in
    place, and the migration is idempotent."""
    import copy

    from app.models import Workflow
    from app.services import chat as chat_service
    from app.services import workflow as wf

    legacy = copy.deepcopy(wf.SUPERSEDED_DEFAULTS[0])
    assert "contact_method" not in legacy["nodes"]  # sanity: the old shape
    row = Workflow(workspace_id=other_workspace_id, name="Seeded default", is_default=1, definition=legacy)
    db_session.add(row)
    db_session.commit()

    assert chat_service.upgrade_default_workflows(db_session) >= 1
    db_session.refresh(row)
    assert "contact_method" in row.definition["nodes"]
    assert chat_service.upgrade_default_workflows(db_session) == 0  # idempotent


def test_upgrade_leaves_a_customised_default_untouched(client, db_session, other_workspace_id):
    from app.models import Workflow
    from app.services import chat as chat_service

    custom = {
        "start": "name",
        "nodes": {
            "name": {"field": "client_name", "type": "text", "prompt": {"en": "Your name?"}, "next": ""}
        },
    }
    row = Workflow(
        workspace_id=other_workspace_id,
        name="Customised flow",
        is_default=1,
        definition=copy_def(custom),
    )
    db_session.add(row)
    db_session.commit()

    chat_service.upgrade_default_workflows(db_session)
    db_session.refresh(row)
    assert row.definition == custom  # never clobbered


def copy_def(d):
    import copy

    return copy.deepcopy(d)


def test_html_is_sanitized(client, auth_headers):
    _, last = _run_chat(
        client,
        [
            "<script>alert(1)</script>Eve",
            "Website",
            "Simple portfolio",
            "$1000",
            "Flexible",
            "Email",
            "eve@example.com",
            "no",
        ],
    )
    detail = client.get(f"/api/leads/{last['lead_id']}", headers=auth_headers).json()
    assert "<script>" not in detail["client_name"]
    assert "Eve" in detail["client_name"]
