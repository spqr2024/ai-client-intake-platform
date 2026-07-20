"""The Telegram operations CLI.

Worth real tests despite being a script: these guards are what stand between an
operator and a silently broken integration — a webhook registered without its
secret rejects every update, and the bot's own id as the chat id makes every
notification fail with a message nobody reads.
"""

import asyncio

import pytest

from app import telegram_bot as cli
from app.core.config import get_settings

BOT_ID = 8681592360


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setattr(get_settings(), "telegram_bot_token", f"{BOT_ID}:test-token")


@pytest.fixture
def api(monkeypatch):
    """Replace the Bot API transport; records calls as (method, payload)."""
    calls: list[tuple[str, dict]] = []
    responses: dict[str, object] = {}

    async def fake_api(method, payload, raise_on_error=False):
        calls.append((method, payload))
        return responses.get(method, {"ok": True, "result": {}})

    monkeypatch.setattr(cli.telegram_service, "_api", fake_api)
    fake_api.calls = calls  # type: ignore[attr-defined]
    fake_api.responses = responses  # type: ignore[attr-defined]
    return fake_api


def run(coro) -> int:
    return asyncio.run(coro)


# ── info ──────────────────────────────────────────────────────────────────
def test_info_reports_a_healthy_bot(token, api, monkeypatch, capsys):
    api.responses["getMe"] = {"ok": True, "result": {"id": BOT_ID, "username": "nora_bot"}}
    api.responses["getWebhookInfo"] = {"ok": True, "result": {"url": "", "pending_update_count": 0}}
    monkeypatch.setattr(cli.telegram_service, "authorized_chat_ids", lambda db, ws: {"5175461269"})

    assert run(cli.cmd_info()) == 0
    out = capsys.readouterr().out
    assert "nora_bot" in out
    assert "5175461269" in out


def test_info_flags_the_bots_own_id_used_as_the_chat_id(token, api, monkeypatch, capsys):
    """The failure that makes every notification 403. Telegram's own error
    ("the bot can't send messages to the bot") never reaches the operator, so
    the CLI has to name it."""
    api.responses["getMe"] = {"ok": True, "result": {"id": BOT_ID, "username": "nora_bot"}}
    api.responses["getWebhookInfo"] = {"ok": True, "result": {"url": "", "pending_update_count": 0}}
    monkeypatch.setattr(cli.telegram_service, "authorized_chat_ids", lambda db, ws: {str(BOT_ID)})

    assert run(cli.cmd_info()) == 1
    assert "OWN id" in capsys.readouterr().err


def test_info_fails_when_the_api_is_unreachable(token, api, capsys):
    api.responses["getMe"] = None
    assert run(cli.cmd_info()) == 1
    assert "Could not reach" in capsys.readouterr().err


def test_commands_require_a_token(monkeypatch):
    monkeypatch.setattr(get_settings(), "telegram_bot_token", "")
    with pytest.raises(SystemExit) as exc:
        cli._require_token()
    assert exc.value.code == 2


# ── set-webhook ───────────────────────────────────────────────────────────
def test_set_webhook_refuses_without_a_secret(token, api, monkeypatch, capsys):
    """The endpoint fails closed, so registering without the secret would
    produce a webhook that rejects 100% of updates."""
    monkeypatch.setattr(get_settings(), "telegram_webhook_secret", "")

    assert run(cli.cmd_set_webhook("https://api.example.com")) == 2
    assert "TELEGRAM_WEBHOOK_SECRET" in capsys.readouterr().err
    assert not api.calls  # nothing registered


def test_set_webhook_refuses_plaintext_http(token, api, monkeypatch, capsys):
    monkeypatch.setattr(get_settings(), "telegram_webhook_secret", "s" * 32)

    assert run(cli.cmd_set_webhook("http://api.example.com")) == 2
    assert "HTTPS" in capsys.readouterr().err
    assert not api.calls


def test_set_webhook_registers_url_secret_and_updates(token, api, monkeypatch):
    monkeypatch.setattr(get_settings(), "telegram_webhook_secret", "s" * 32)

    assert run(cli.cmd_set_webhook("https://api.example.com/")) == 0

    method, payload = api.calls[0]
    assert method == "setWebhook"
    assert payload["url"] == "https://api.example.com/api/webhook/telegram"
    assert payload["secret_token"] == "s" * 32
    # Omitting callback_query leaves the Accept/Reject buttons inert.
    assert "callback_query" in payload["allowed_updates"]
    assert "message" in payload["allowed_updates"]
    assert any(m == "setMyCommands" for m, _ in api.calls)


def test_set_webhook_reports_a_rejected_registration(token, api, monkeypatch, capsys):
    monkeypatch.setattr(get_settings(), "telegram_webhook_secret", "s" * 32)
    api.responses["setWebhook"] = None

    assert run(cli.cmd_set_webhook("https://api.example.com")) == 1
    assert "setWebhook failed" in capsys.readouterr().err


# ── delete-webhook / register-commands ────────────────────────────────────
def test_delete_webhook_keeps_queued_updates(token, api):
    """Dropping them would discard manager actions taken while switching modes."""
    assert run(cli.cmd_delete_webhook()) == 0
    method, payload = api.calls[0]
    assert method == "deleteWebhook"
    assert payload["drop_pending_updates"] is False


def test_register_commands_publishes_the_documented_menu(token, api, capsys):
    assert run(cli.cmd_register_commands()) == 0
    method, payload = api.calls[0]
    assert method == "setMyCommands"
    published = {c["command"] for c in payload["commands"]}
    assert {"start", "help", "status", "note"} <= published
    assert "/start" in capsys.readouterr().out


def test_register_commands_reports_failure(token, api, monkeypatch):
    async def failing(method, payload, raise_on_error=False):
        return None

    monkeypatch.setattr(cli.telegram_service, "_api", failing)
    assert run(cli.cmd_register_commands()) == 1


# ── poll ──────────────────────────────────────────────────────────────────
def test_poll_refuses_while_a_webhook_is_registered(token, api, capsys):
    """Telegram serves getUpdates only when no webhook is set; without this the
    poller would spin on 409s forever."""
    api.responses["getWebhookInfo"] = {"ok": True, "result": {"url": "https://api.example.com/hook"}}

    assert run(cli.cmd_poll()) == 2
    assert "delete-webhook" in capsys.readouterr().err


# ── argument dispatch ─────────────────────────────────────────────────────
def test_main_requires_a_subcommand(monkeypatch):
    monkeypatch.setattr("sys.argv", ["telegram_bot"])
    with pytest.raises(SystemExit):
        cli.main()


def test_main_dispatches_to_the_named_command(monkeypatch):
    called = {}

    async def fake_info():
        called["info"] = True
        return 0

    monkeypatch.setattr(cli, "cmd_info", fake_info)
    monkeypatch.setattr("sys.argv", ["telegram_bot", "info"])
    assert cli.main() == 0
    assert called["info"]
