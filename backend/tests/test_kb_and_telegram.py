# The Telegram webhook fails closed; conftest configures this secret so the
# suite exercises the authenticated path.
WEBHOOK_HEADERS = {"X-Telegram-Bot-Api-Secret-Token": "test-webhook-secret"}


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
    resp = client.post("/api/webhook/telegram", json=update, headers=WEBHOOK_HEADERS)
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
    resp = client.post("/api/webhook/telegram", json=update, headers=WEBHOOK_HEADERS)
    assert resp.status_code == 200

    detail = client.get(f"/api/leads/{lead.id}", headers=auth_headers).json()
    assert any("follow up Monday" in a["detail"] for a in detail["activities"])


def test_telegram_webhook_bad_callback(client):
    update = {"update_id": 3, "callback_query": {"id": "cb2", "data": "accept:not-a-number"}}
    resp = client.post("/api/webhook/telegram", json=update, headers=WEBHOOK_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["ok"] is False


def test_telegram_webhook_rejects_missing_and_wrong_secret(client, db_session):
    """The webhook mutates lead state, so it must reject anyone who cannot prove
    Telegram sent the update."""
    from app.models import Lead

    lead = Lead(project_name="TG auth test", status="New")
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    update = {
        "update_id": 4,
        "callback_query": {
            "id": "cb3",
            "from": {"first_name": "Attacker"},
            "data": f"accept:{lead.id}",
            "message": {"chat": {"id": 42}},
        },
    }

    assert client.post("/api/webhook/telegram", json=update).status_code == 403
    bad = {"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"}
    assert client.post("/api/webhook/telegram", json=update, headers=bad).status_code == 403

    # The rejected calls must not have touched the lead.
    db_session.refresh(lead)
    assert lead.status == "New"


def test_lead_card_survives_an_unreachable_public_app_url():
    """Regression: PUBLIC_APP_URL=http://localhost:3000 (the shipped default)
    put a localhost link on the "Open in CRM" button. Telegram rejects such a
    URL and refuses the *entire* sendMessage, so managers silently received no
    lead card at all — the Accept/Reject/Call actions went down with the link.
    """
    from app.services import telegram as tg

    for bad in (
        "http://localhost:3000/admin/leads/16",
        "http://127.0.0.1:3000/admin/leads/16",
        "http://backend/admin/leads/16",  # container hostname
        "ftp://example.com/x",
        "not-a-url",
    ):
        assert tg.is_valid_button_url(bad) is False, bad

    for good in (
        "https://app.example.com/admin/leads/16",
        "http://app.example.com/admin/leads/16",
    ):
        assert tg.is_valid_button_url(good) is True, good

    # The actions must survive a bad link...
    degraded = tg.lead_keyboard(16, "http://localhost:3000/admin/leads/16")
    labels = [b["text"] for row in degraded["inline_keyboard"] for b in row]
    assert any("Accept" in t for t in labels)
    assert any("Reject" in t for t in labels)
    assert any("Call" in t for t in labels)
    assert not any("CRM" in t for t in labels)
    # ...and no button may carry a URL Telegram would reject.
    assert all("url" not in b for row in degraded["inline_keyboard"] for b in row)

    # ...and a good link still gets the deep-link button.
    full = tg.lead_keyboard(16, "https://app.example.com/admin/leads/16")
    assert any("CRM" in b["text"] for row in full["inline_keyboard"] for b in row)


def test_prospect_chat_cannot_touch_crm_state(client, auth_headers, db_session):
    """A valid webhook secret proves the update came from Telegram — not that it
    came from our manager. Anyone can DM a public bot.

    A non-manager chat is a *prospect*, not an intruder: it gets a friendly
    reply rather than a rejection, so the intake flow can use the same door.
    What must hold is that no prospect branch reads or writes CRM state. This
    asserts that invariant rather than the response shape, which intake changes.
    """
    from app.models import Lead

    lead = Lead(project_name="TG stranger test", status="New")
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    stranger = 999999  # not the configured chat (42)

    note = {
        "update_id": 10,
        "message": {
            "chat": {"id": stranger},
            "from": {"first_name": "Stranger"},
            "text": f"/note {lead.id} injected by an outsider",
        },
    }
    client.post("/api/webhook/telegram", json=note, headers=WEBHOOK_HEADERS)

    accept = {
        "update_id": 11,
        "callback_query": {
            "id": "cb-stranger",
            "from": {"first_name": "Stranger"},
            "data": f"accept:{lead.id}",
            "message": {"chat": {"id": stranger}},
        },
    }
    # A callback can only originate from a lead card, which prospects never
    # receive, so this one stays an outright rejection.
    resp = client.post("/api/webhook/telegram", json=accept, headers=WEBHOOK_HEADERS)
    assert resp.json()["ok"] is False

    # The invariant: neither call may have mutated the lead.
    detail = client.get(f"/api/leads/{lead.id}", headers=auth_headers).json()
    assert detail["status"] == "New"
    assert not any("outsider" in a["detail"] for a in detail["activities"])


def test_prospect_reply_does_not_disclose_the_crm_surface(db_session):
    """The greeting a stranger gets must not advertise managerial commands —
    otherwise the bot hands an attacker a map of what to try next."""
    from app.services import telegram as tg

    text = tg.PROSPECT_WELCOME.lower()
    for leaked in ("/note", "/leads", "/status", "lead id", "crm", "accept", "reject"):
        assert leaked not in text, f"prospect greeting mentions {leaked!r}"


def test_roles_resolve_correctly(db_session):
    from app.services import telegram as tg

    assert tg.chat_role(db_session, 42, 1) == tg.MANAGER
    assert tg.chat_role(db_session, 999999, 1) == tg.PROSPECT
    assert tg.is_manager(db_session, 42, 1) is True
    assert tg.is_manager(db_session, 999999, 1) is False


def test_unconfigured_integration_grants_nobody_manager(db_session, monkeypatch):
    """An empty allowlist must not promote whoever messages first."""
    from app.core.config import get_settings
    from app.services import telegram as tg

    monkeypatch.setattr(get_settings(), "telegram_chat_id", "")
    assert tg.chat_role(db_session, 42, 1) == tg.PROSPECT
    assert tg.is_manager(db_session, 42, 1) is False


def test_telegram_authorization_does_not_fall_open_when_unset(client, db_session, monkeypatch):
    """An empty allowlist means "not configured", not "allow everyone"."""
    from app.core.config import get_settings
    from app.services import telegram as telegram_service

    monkeypatch.setattr(get_settings(), "telegram_chat_id", "")
    assert telegram_service._is_authorized(db_session, 42, 1) is False
    assert telegram_service._is_authorized(db_session, 999, 1) is False


def test_telegram_start_and_help_commands(client):
    """/start used to fall through silently, so a correctly wired bot looked
    dead to the operator."""
    for command in ("/start", "/help", "/status", "/help@aiclient_intake_bot"):
        update = {
            "update_id": 20,
            "message": {"chat": {"id": 42}, "from": {"first_name": "Manager"}, "text": command},
        }
        resp = client.post("/api/webhook/telegram", json=update, headers=WEBHOOK_HEADERS)
        assert resp.status_code == 200, command
        assert resp.json()["ok"] is True, command


def test_telegram_webhook_fails_closed_when_unconfigured(client, monkeypatch):
    """An unset secret disables the endpoint rather than disabling the check —
    a misconfigured deploy must not become world-writable."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "telegram_webhook_secret", "")
    update = {"update_id": 5, "message": {"chat": {"id": 42}, "text": "/note 1 hello"}}

    assert client.post("/api/webhook/telegram", json=update).status_code == 403
    # Not even a caller who guesses the (empty) value gets in.
    empty = {"X-Telegram-Bot-Api-Secret-Token": ""}
    assert client.post("/api/webhook/telegram", json=update, headers=empty).status_code == 403
