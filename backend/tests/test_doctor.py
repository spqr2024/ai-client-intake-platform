"""The credential preflight.

`make doctor` is meant to be usable as a deploy gate, so what matters is the
grading: a real misconfiguration must FAIL (non-zero exit), an unconfigured
integration must SKIP rather than fail, and a working-but-imperfect setup must
WARN without blocking the deploy. Network calls are stubbed; the provider
behaviour is not under test here, the verdicts are.
"""

import httpx
import pytest

from app import doctor
from app.core.config import get_settings

BOT_ID = 1234567890


def statuses(results) -> dict[str, str]:
    return {name: status for status, name, _detail in results}


def details(results) -> str:
    return " ".join(detail for _s, _n, detail in results)


# ── Grading ───────────────────────────────────────────────────────────────
def test_report_exits_non_zero_only_on_failure():
    """Warnings must not break a deploy pipeline; failures must."""
    assert doctor._report([(doctor.OK, "a", ""), (doctor.WARN, "b", "")]) == 0
    assert doctor._report([(doctor.SKIP, "a", "")]) == 0
    assert doctor._report([(doctor.OK, "a", ""), (doctor.FAIL, "b", "")]) == 1


# ── Secrets ───────────────────────────────────────────────────────────────
def test_placeholder_jwt_secret_fails(monkeypatch):
    monkeypatch.setattr(get_settings(), "jwt_secret", "change-me-in-production")
    assert statuses(doctor.check_secrets())["JWT_SECRET"] == doctor.FAIL


def test_short_jwt_secret_only_warns(monkeypatch):
    """It is weak, not forgeable-by-anyone-reading-the-repo."""
    monkeypatch.setattr(get_settings(), "jwt_secret", "short-but-not-the-placeholder")
    assert statuses(doctor.check_secrets())["JWT_SECRET"] == doctor.WARN


def test_strong_secret_and_custom_password_pass(monkeypatch):
    monkeypatch.setattr(get_settings(), "jwt_secret", "x" * 64)
    monkeypatch.setattr(get_settings(), "admin_password", "a-real-password")
    result = statuses(doctor.check_secrets())
    assert result["JWT_SECRET"] == doctor.OK
    assert result["ADMIN_PASSWORD"] == doctor.OK


def test_default_admin_password_warns(monkeypatch):
    monkeypatch.setattr(get_settings(), "admin_password", "admin12345")
    assert statuses(doctor.check_secrets())["ADMIN_PASSWORD"] == doctor.WARN


# ── Telegram ──────────────────────────────────────────────────────────────
@pytest.fixture
def telegram_configured(monkeypatch):
    monkeypatch.setattr(get_settings(), "telegram_bot_token", f"{BOT_ID}:test-token")
    monkeypatch.setattr(get_settings(), "telegram_webhook_secret", "s" * 32)
    monkeypatch.setattr(get_settings(), "telegram_chat_id", "9876543210")


def _stub_telegram(monkeypatch, payload, status_code=200):
    class FakeResponse:
        def json(self):
            return payload

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, **kw):
            return FakeResponse()

        async def post(self, url, **kw):
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: FakeClient())


@pytest.mark.anyio
async def test_unconfigured_telegram_skips_rather_than_fails(monkeypatch):
    """A zero-key install must still be able to run the preflight."""
    monkeypatch.setattr(get_settings(), "telegram_bot_token", "")
    results = await doctor.check_telegram(send_test=False)
    assert statuses(results)["Telegram"] == doctor.SKIP


@pytest.mark.anyio
async def test_rejected_token_fails(monkeypatch, telegram_configured):
    _stub_telegram(monkeypatch, {"ok": False, "description": "Unauthorized"})
    results = await doctor.check_telegram(send_test=False)
    assert doctor.FAIL in statuses(results).values()
    assert "Unauthorized" in details(results)


@pytest.mark.anyio
async def test_bot_id_used_as_chat_id_fails(monkeypatch, telegram_configured):
    """The mistake that silently delivers nothing: a bot cannot message itself,
    so this has to be a hard failure rather than a warning."""
    monkeypatch.setattr(get_settings(), "telegram_chat_id", str(BOT_ID))
    _stub_telegram(monkeypatch, {"ok": True, "result": {"id": BOT_ID, "username": "nora_bot"}})

    results = await doctor.check_telegram(send_test=False)
    assert doctor.FAIL in statuses(results).values()


@pytest.mark.anyio
async def test_missing_webhook_secret_warns_but_does_not_fail(monkeypatch, telegram_configured):
    """Sending alerts still works without it; only inbound updates break."""
    monkeypatch.setattr(get_settings(), "telegram_webhook_secret", "")
    _stub_telegram(monkeypatch, {"ok": True, "result": {"id": BOT_ID, "username": "nora_bot"}})

    results = await doctor.check_telegram(send_test=False)
    assert statuses(results)["Telegram webhook"] == doctor.WARN
    assert doctor.FAIL not in statuses(results).values()


@pytest.mark.anyio
async def test_transport_failure_is_reported_not_raised(monkeypatch, telegram_configured):
    class ExplodingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, **kw):
            raise httpx.ConnectError("dns failure")

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: ExplodingClient())

    results = await doctor.check_telegram(send_test=False)
    assert doctor.FAIL in statuses(results).values()


# ── Other providers ───────────────────────────────────────────────────────
@pytest.mark.anyio
async def test_mock_provider_skips(monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_provider", "mock")
    status, _name, _detail = await doctor.check_llm()
    assert status == doctor.SKIP


@pytest.mark.anyio
async def test_unconfigured_crm_skips(monkeypatch):
    monkeypatch.setattr(get_settings(), "crm_provider", "")
    status, _name, _detail = await doctor.check_crm()
    assert status == doctor.SKIP


def test_unconfigured_smtp_skips(monkeypatch):
    monkeypatch.setattr(get_settings(), "smtp_host", "")
    results = doctor.check_smtp(send_test=False)
    assert doctor.SKIP in statuses(results).values()
