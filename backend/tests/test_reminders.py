"""Daily digest and follow-up reminders.

These are driven by a coarse background tick, so the properties that matter are
idempotency and recovery: a restart, a missed window or a failed send must not
produce a duplicate, nor silently drop a reminder an operator is relying on.

Everything runs in a dedicated tenant. The digest summarises "every lead in the
last 24 hours" and is once-per-day by consulting the notification log — both of
which would otherwise read whatever the rest of the suite happened to create,
making these assertions order-dependent.
"""

from datetime import timedelta

import pytest

from app.models import Lead, Notification, utcnow
from app.services import reminders
from app.services import telegram as tg


@pytest.fixture
def ws(client, db_session):
    """A fresh tenant per test.

    A shared one is not enough: leads and digest rows persist between tests in
    the same session, so "was a digest already sent?" and "were there any leads
    today?" would answer from a previous test's leftovers.
    """
    import uuid

    from app.models import Workspace

    workspace = Workspace(name="Reminder Tenant", slug=f"reminders-{uuid.uuid4().hex[:8]}")
    db_session.add(workspace)
    db_session.commit()
    db_session.refresh(workspace)
    return workspace.id


@pytest.fixture
def sent(monkeypatch):
    """Capture outbound sends; each entry is (chat_id, text)."""
    calls: list[tuple[str, str]] = []

    async def fake_send(chat_id, text, reply_markup=None):
        calls.append((chat_id, text))

    monkeypatch.setattr(tg, "send_message", fake_send)
    monkeypatch.setattr(tg, "enabled", lambda db, workspace_id: True)
    monkeypatch.setattr(tg, "workspace_chat_id", lambda db, workspace_id: "42")
    return calls


@pytest.fixture
def failing_send(monkeypatch):
    async def boom(chat_id, text, reply_markup=None):
        raise tg.TelegramError("sendMessage: chat not found")

    monkeypatch.setattr(tg, "send_message", boom)
    monkeypatch.setattr(tg, "enabled", lambda db, workspace_id: True)
    monkeypatch.setattr(tg, "workspace_chat_id", lambda db, workspace_id: "42")


def make_lead(db, workspace_id, **kw):
    lead = Lead(workspace_id=workspace_id, project_name="Digest lead", status="New", score=70, **kw)
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


# ── Follow-up reminders ───────────────────────────────────────────────────
@pytest.mark.anyio
async def test_a_due_follow_up_is_reminded_once(client, db_session, sent, ws):
    lead = make_lead(db_session, ws, follow_up_at=utcnow() - timedelta(minutes=5))

    assert await reminders.send_follow_up_reminders(db_session, ws) == 1
    assert f"#{lead.id}" in sent[0][1]

    # The loop runs every 15 minutes; an unmarked lead would be re-sent forever.
    assert await reminders.send_follow_up_reminders(db_session, ws) == 0
    db_session.refresh(lead)
    assert lead.follow_up_notified_at is not None


@pytest.mark.anyio
async def test_a_future_follow_up_is_not_reminded(client, db_session, sent, ws):
    make_lead(db_session, ws, follow_up_at=utcnow() + timedelta(days=1))
    assert await reminders.send_follow_up_reminders(db_session, ws) == 0
    assert not sent


@pytest.mark.anyio
async def test_a_failed_reminder_is_retried_not_dropped(client, db_session, failing_send, ws):
    """Marking the lead after a failed send would lose the reminder silently."""
    lead = make_lead(db_session, ws, follow_up_at=utcnow() - timedelta(minutes=5))

    assert await reminders.send_follow_up_reminders(db_session, ws) == 0
    db_session.refresh(lead)
    assert lead.follow_up_notified_at is None  # still eligible on the next tick

    logged = (
        db_session.query(Notification)
        .filter(Notification.event == reminders.REMINDER_EVENT)
        .order_by(Notification.id.desc())
        .first()
    )
    assert logged.status == "failed"
    assert "chat not found" in logged.error


@pytest.mark.anyio
async def test_reminders_are_workspace_scoped(client, db_session, sent, ws):
    """A due lead in another tenant must not reach this tenant's manager."""
    from app.models import DEFAULT_WORKSPACE_ID

    other = Lead(
        workspace_id=DEFAULT_WORKSPACE_ID,
        project_name="Other tenant lead",
        follow_up_at=utcnow() - timedelta(minutes=5),
    )
    db_session.add(other)
    db_session.commit()

    await reminders.send_follow_up_reminders(db_session, ws)
    assert not any("Other tenant lead" in text for _chat, text in sent)


# ── Daily digest ──────────────────────────────────────────────────────────
@pytest.mark.anyio
async def test_digest_summarises_recent_leads(client, db_session, sent, ws):
    lead = make_lead(db_session, ws)

    assert await reminders.send_daily_digest(db_session, ws) is True
    body = sent[-1][1]
    assert "Daily digest" in body
    assert f"#{lead.id}" in body


@pytest.mark.anyio
async def test_digest_is_sent_once_per_day(client, db_session, sent, ws):
    make_lead(db_session, ws)

    assert await reminders.send_daily_digest(db_session, ws) is True
    # The scheduler ticks four times inside the digest hour; only the first sends.
    assert await reminders.send_daily_digest(db_session, ws) is False
    assert len(sent) == 1


@pytest.mark.anyio
async def test_quiet_days_send_nothing(client, db_session, sent, ws):
    """A digest that says "0 leads" every morning trains you to ignore it."""
    assert reminders.build_digest(db_session, ws) is None
    assert await reminders.send_daily_digest(db_session, ws) is False
    assert not sent


@pytest.mark.anyio
async def test_digest_counts_upcoming_follow_ups(client, db_session, sent, ws):
    make_lead(db_session, ws, follow_up_at=utcnow() + timedelta(hours=3))

    body = reminders.build_digest(db_session, ws)
    assert "follow-up" in body.lower()


@pytest.mark.anyio
async def test_digest_truncates_a_long_list(client, db_session, sent, ws):
    """Telegram caps a message at 4096 characters; a busy day must not push
    the digest past it."""
    for i in range(15):
        make_lead(db_session, ws, client_name=f"Client {i}")

    body = reminders.build_digest(db_session, ws)
    assert "more" in body
    assert len(body) < 4000


@pytest.mark.anyio
async def test_digest_is_skipped_when_telegram_is_off(client, db_session, monkeypatch, ws):
    make_lead(db_session, ws)
    monkeypatch.setattr(tg, "enabled", lambda db, workspace_id: False)
    monkeypatch.setattr(tg, "workspace_chat_id", lambda db, workspace_id: "42")

    assert await reminders.send_daily_digest(db_session, ws) is False
