"""Manager lead commands: /leads, /lead, /stats, /setstatus.

Every test drives `handle_update`, the same entry point the webhook and poller
use, so role enforcement is exercised rather than bypassed.
"""

import pytest

from app.models import DEFAULT_WORKSPACE_ID as WS
from app.models import Lead
from app.services import telegram as tg

MANAGER = 42  # conftest pins TELEGRAM_CHAT_ID to this
PROSPECT = 999999


@pytest.fixture
def sent(monkeypatch):
    """Capture outbound sendMessage payloads instead of calling Telegram."""
    calls: list[dict] = []

    async def fake_api(method, payload, raise_on_error=False):
        calls.append({"method": method, **payload})
        return {"ok": True, "result": {}}

    monkeypatch.setattr(tg, "_api", fake_api)
    return calls


@pytest.fixture
def other_workspace(client, db_session):
    """A genuine second tenant. Foreign keys are enforced in the suite, so a
    made-up workspace id would fail insertion rather than test isolation."""
    from app.models import Workspace

    existing = db_session.query(Workspace).filter(Workspace.slug == "tg-other").first()
    if existing:
        return existing
    row = Workspace(name="Other Tenant", slug="tg-other")
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


@pytest.fixture
def lead(client, db_session):  # `client` creates the schema

    row = Lead(
        workspace_id=WS,
        project_name="Neon rebrand",
        client_name="Ada Lovelace",
        client_email="ada@example.com",
        service="Brand identity",
        budget=18000,
        timeline="4 weeks",
        status="New",
        score=77,
        priority="High",
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def update(chat, text):
    return {"update_id": 1, "message": {"chat": {"id": chat}, "from": {"first_name": "M"}, "text": text}}


async def run(db, chat, text):
    return await tg.handle_update(db, update(chat, text), WS)


def last(sent) -> str:
    return sent[-1]["text"]


# ── /leads ────────────────────────────────────────────────────────────────
@pytest.mark.anyio
async def test_leads_lists_recent(db_session, sent, lead):
    await run(db_session, MANAGER, "/leads")
    assert f"#{lead.id}" in last(sent)
    assert "Neon rebrand" in last(sent)


@pytest.mark.anyio
async def test_leads_filters_by_status(db_session, sent, lead):
    await run(db_session, MANAGER, "/leads Qualified")
    assert f"#{lead.id}" not in last(sent)  # the fixture lead is "New"

    await run(db_session, MANAGER, "/leads New")
    assert f"#{lead.id}" in last(sent)


@pytest.mark.anyio
async def test_leads_rejects_an_unknown_status_with_guidance(db_session, sent, lead):
    await run(db_session, MANAGER, "/leads Nonsense")
    reply = last(sent)
    assert "Unknown status" in reply
    assert "New" in reply  # lists the valid ones


# ── /lead ─────────────────────────────────────────────────────────────────
@pytest.mark.anyio
async def test_lead_detail_includes_contact_and_actions(db_session, sent, lead):
    await run(db_session, MANAGER, f"/lead {lead.id}")
    payload = sent[-1]
    assert "ada@example.com" in payload["text"]
    assert "Neon rebrand" in payload["text"]
    labels = [b["text"] for row in payload["reply_markup"]["inline_keyboard"] for b in row]
    assert any("Accept" in t for t in labels)


@pytest.mark.anyio
async def test_lead_detail_handles_missing_and_malformed_ids(db_session, sent, lead):
    await run(db_session, MANAGER, "/lead 999999")
    assert "not found" in last(sent).lower()

    await run(db_session, MANAGER, "/lead")
    assert "usage" in last(sent).lower()


@pytest.mark.anyio
async def test_lead_detail_is_workspace_scoped(client, db_session, sent, other_workspace):
    """Guessing an id must not read another tenant's lead."""
    other = Lead(workspace_id=other_workspace.id, project_name="Other tenant", status="New")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)

    await run(db_session, MANAGER, f"/lead {other.id}")
    assert "not found" in last(sent).lower()
    assert "Other tenant" not in last(sent)


# ── /stats ────────────────────────────────────────────────────────────────
@pytest.mark.anyio
async def test_stats_reports_the_pipeline(db_session, sent, lead):
    await run(db_session, MANAGER, "/stats")
    assert "Pipeline" in last(sent)


# ── /setstatus ────────────────────────────────────────────────────────────
@pytest.mark.anyio
async def test_setstatus_moves_a_lead_and_logs_it(db_session, sent, lead):
    await run(db_session, MANAGER, f"/setstatus {lead.id} Qualified")
    db_session.refresh(lead)
    assert lead.status == "Qualified"
    assert "Qualified" in last(sent)

    from app.models import ActivityLog

    logs = db_session.query(ActivityLog).filter(ActivityLog.lead_id == lead.id).all()
    assert any("Qualified" in entry.detail for entry in logs)


@pytest.mark.anyio
async def test_setstatus_rejects_an_unknown_status(db_session, sent, lead):
    await run(db_session, MANAGER, f"/setstatus {lead.id} Bogus")
    db_session.refresh(lead)
    assert lead.status == "New"
    assert "Unknown status" in last(sent)


@pytest.mark.anyio
async def test_setstatus_needs_both_arguments(db_session, sent, lead):
    await run(db_session, MANAGER, "/setstatus")
    assert "usage" in last(sent).lower()


@pytest.mark.anyio
async def test_setstatus_is_workspace_scoped(client, db_session, sent, other_workspace):
    other = Lead(workspace_id=other_workspace.id, project_name="Other tenant", status="New")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)

    await run(db_session, MANAGER, f"/setstatus {other.id} Converted")
    db_session.refresh(other)
    assert other.status == "New"


# ── Role enforcement ──────────────────────────────────────────────────────
@pytest.mark.anyio
@pytest.mark.parametrize("command", ["/leads", "/lead 1", "/stats", "/setstatus 1 Converted"])
async def test_prospect_cannot_reach_any_lead_command(db_session, sent, lead, command):
    """Each new command must inherit the role gate, not re-implement it."""
    await run(db_session, PROSPECT, command)
    assert last(sent) == tg.PROSPECT_WELCOME

    db_session.refresh(lead)
    assert lead.status == "New"
