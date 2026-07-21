"""Prospect intake over Telegram.

A non-manager chat is interviewed by the same workflow state machine the web
widget uses, and a completed interview produces a real scored lead.
"""

import pytest
from sqlalchemy import select

from app.models import DEFAULT_WORKSPACE_ID as WS
from app.models import Conversation, Lead
from app.services import telegram as tg

MANAGER = 42
PROSPECT = 555001


@pytest.fixture
def sent(monkeypatch):
    calls: list[dict] = []

    async def fake_api(method, payload, raise_on_error=False):
        calls.append({"method": method, **payload})
        return {"ok": True, "result": {}}

    monkeypatch.setattr(tg, "_api", fake_api)
    return calls


def update(chat, text, **sender):
    return {
        "update_id": 1,
        "message": {
            "chat": {"id": chat},
            "from": {"first_name": "Dana", **sender},
            "text": text,
        },
    }


def texts(sent):
    return [c["text"] for c in sent if c["method"] == "sendMessage"]


def conversation_for(db, chat) -> Conversation | None:
    return db.scalars(select(Conversation).where(Conversation.external_ref == tg._external_ref(chat))).first()


@pytest.mark.anyio
async def test_first_message_starts_an_interview(client, db_session, sent):
    await tg.handle_update(db_session, update(PROSPECT, "Hi, I need a website"), WS)

    convo = conversation_for(db_session, PROSPECT)
    assert convo is not None
    assert convo.status == "Active"
    assert convo.workspace_id == WS
    assert texts(sent)  # the prospect got a question back


@pytest.mark.anyio
async def test_the_conversation_is_resumed_not_restarted(client, db_session, sent):
    """State is keyed on the chat id in the database, so an interview survives
    a process restart rather than looping on the first question forever."""
    await tg.handle_update(db_session, update(PROSPECT + 1, "Hello"), WS)
    first = conversation_for(db_session, PROSPECT + 1)

    await tg.handle_update(db_session, update(PROSPECT + 1, "A marketing site"), WS)
    again = conversation_for(db_session, PROSPECT + 1)

    assert first.id == again.id
    all_for_chat = db_session.scalars(
        select(Conversation).where(Conversation.external_ref == tg._external_ref(PROSPECT + 1))
    ).all()
    assert len(all_for_chat) == 1


@pytest.mark.anyio
async def test_start_abandons_the_previous_interview(client, db_session, sent):
    await tg.handle_update(db_session, update(PROSPECT + 2, "Hello"), WS)
    first = conversation_for(db_session, PROSPECT + 2)
    first_id = first.id

    await tg.handle_update(db_session, update(PROSPECT + 2, "/start"), WS)
    db_session.expire_all()

    old = db_session.get(Conversation, first_id)
    assert old.status == "Abandoned"
    fresh = tg._find_intake_conversation(db_session, PROSPECT + 2, WS)
    assert fresh is not None and fresh.id != first_id


@pytest.mark.anyio
async def test_quick_replies_become_a_keyboard(client, db_session, sent):
    await tg.handle_update(db_session, update(PROSPECT + 3, "Hi"), WS)
    markup = [c for c in sent if c["method"] == "sendMessage"][-1]["reply_markup"]
    # Either tappable options, or an explicit removal of a stale keyboard.
    assert "keyboard" in markup or markup.get("remove_keyboard") is True


@pytest.mark.anyio
async def test_a_failed_turn_does_not_strand_the_prospect(client, db_session, sent, monkeypatch):
    await tg.handle_update(db_session, update(PROSPECT + 4, "Hi"), WS)

    from app.services import chat as chat_service

    async def boom(*a, **k):
        raise RuntimeError("workflow exploded")

    monkeypatch.setattr(chat_service, "process_message", boom)
    await tg.handle_update(db_session, update(PROSPECT + 4, "anything"), WS)

    assert "something went wrong" in texts(sent)[-1].lower()


@pytest.mark.anyio
async def test_rate_limit_stops_a_flood(client, db_session, sent, monkeypatch):
    """The bot is publicly reachable and every completed interview writes a
    lead row, so an unthrottled chat is a spam vector."""
    monkeypatch.setattr(tg, "INTAKE_MAX_MESSAGES_PER_MINUTE", 3)

    results = [await tg.handle_update(db_session, update(PROSPECT + 5, f"msg {i}"), WS) for i in range(6)]
    assert any(r.get("throttled") for r in results)


@pytest.mark.anyio
async def test_managerial_commands_are_not_acknowledged(client, db_session, sent):
    """A prospect probing for commands must learn nothing about them."""
    for probe in ("/leads", "/stats", "/setstatus 1 Converted", "/note 1 x"):
        await tg.handle_update(db_session, update(PROSPECT + 6, probe), WS)
        assert texts(sent)[-1] == tg.PROSPECT_WELCOME


@pytest.mark.anyio
async def test_intake_never_touches_another_lead(client, db_session, sent):
    """The one CRM write a prospect may cause is a lead describing themselves."""
    victim = Lead(workspace_id=WS, project_name="Someone else", status="New")
    db_session.add(victim)
    db_session.commit()
    db_session.refresh(victim)

    for text in ("Hi", f"/setstatus {victim.id} Converted", "delete lead 1"):
        await tg.handle_update(db_session, update(PROSPECT + 7, text), WS)

    db_session.refresh(victim)
    assert victim.status == "New"
    assert victim.project_name == "Someone else"


@pytest.mark.anyio
async def test_manager_free_text_is_not_intake(client, db_session, sent):
    """A manager talking to the assistant must never create a lead."""
    await tg.handle_update(db_session, update(MANAGER, "what's the pipeline looking like?"), WS)
    assert conversation_for(db_session, MANAGER) is None


def test_lead_notification_shows_the_chosen_channel():
    """The new-lead alert reflects the client's picked channel, not just email."""
    tg_lead = Lead(
        workspace_id=WS,
        client_name="Dana",
        service="Website",
        contact_method="telegram",
        contact_value="@dana_dev",
        score=50,
        priority="Medium",
    )
    text = tg.build_lead_text(tg_lead)
    assert "Telegram: @dana_dev" in text
    assert "no email" not in text

    phone_lead = Lead(
        workspace_id=WS,
        client_name="Sam",
        service="Mobile app",
        contact_method="phone",
        contact_value="+1 415 555 0142",
        client_phone="+1 415 555 0142",
        score=70,
        priority="High",
    )
    assert "Phone: +1 415 555 0142" in tg.build_lead_text(phone_lead)

    # A lead created before the picker existed still renders via its email.
    legacy = Lead(
        workspace_id=WS,
        client_name="Old",
        service="Branding",
        client_email="old@example.com",
        score=0,
        priority="Low",
    )
    assert "old@example.com" in tg.build_lead_text(legacy)
