"""The boot-time guard against deploying with placeholder credentials.

The defaults that make a fresh clone run with zero configuration are exactly
the ones that must never reach a public deployment — most critically a
JWT_SECRET published in this repository, which lets anyone mint an admin token.
"""

from pathlib import Path

from app.core.config import Settings

# Fields intentionally left out of the template: internal knobs with no
# deployment story, or values a deployment should never hand-set.
UNDOCUMENTED_BY_DESIGN = {
    "app_name",
    "debug",
    "jwt_algorithm",
    "upload_dir",
}

SAFE = {
    "environment": "production",
    "jwt_secret": "a" * 64,
    "admin_password": "a-real-chosen-password",
    "demo_mode": False,
    "debug": False,
    "cors_origins": "https://app.example.com",
    "public_app_url": "https://app.example.com",
}


def _settings(**overrides) -> Settings:
    # _env_file=None keeps a developer's real .env out of the assertions.
    return Settings(_env_file=None, **{**SAFE, **overrides})


def test_a_correctly_configured_production_deploy_has_no_errors():
    assert _settings().production_config_errors() == []


def test_placeholder_jwt_secret_is_rejected():
    errors = _settings(jwt_secret="change-me-in-production").production_config_errors()
    assert any("JWT_SECRET" in e for e in errors)


def test_short_jwt_secret_is_rejected():
    errors = _settings(jwt_secret="tooshort").production_config_errors()
    assert any("JWT_SECRET" in e for e in errors)


def test_default_admin_password_is_rejected():
    errors = _settings(admin_password="admin12345").production_config_errors()
    assert any("ADMIN_PASSWORD" in e for e in errors)


def test_demo_mode_is_rejected():
    errors = _settings(demo_mode=True).production_config_errors()
    assert any("DEMO_MODE" in e for e in errors)


def test_wildcard_and_localhost_cors_are_rejected():
    assert any("CORS_ORIGINS" in e for e in _settings(cors_origins="*").production_config_errors())
    errors = _settings(cors_origins="http://localhost:3000").production_config_errors()
    assert any("CORS_ORIGINS" in e for e in errors)


def test_plaintext_public_url_is_rejected():
    errors = _settings(public_app_url="http://app.example.com").production_config_errors()
    assert any("PUBLIC_APP_URL" in e for e in errors)


def test_bot_token_without_webhook_secret_is_rejected():
    """The webhook fails closed, so this combination silently breaks every
    manager action rather than erroring anywhere visible."""
    errors = _settings(telegram_bot_token="123:abc", telegram_webhook_secret="").production_config_errors()
    assert any("TELEGRAM_WEBHOOK_SECRET" in e for e in errors)

    ok = _settings(telegram_bot_token="123:abc", telegram_webhook_secret="s" * 32)
    assert ok.production_config_errors() == []


def test_env_example_documents_every_setting():
    """`config.py` uses extra="ignore", so a setting missing from the template
    is invisible: the deploy silently runs on the default instead of erroring.
    """
    template = Path(__file__).resolve().parents[2] / ".env.example"
    documented = {
        line.split("=", 1)[0].strip().lower()
        for line in template.read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    missing = sorted(set(Settings.model_fields) - documented - UNDOCUMENTED_BY_DESIGN)
    assert not missing, f".env.example does not document: {missing}"


def test_development_keeps_the_zero_config_defaults_usable():
    """The same placeholders must stay warnings locally, or a fresh clone
    cannot start."""
    dev = Settings(_env_file=None, environment="development")
    assert dev.is_production is False
    # Still reported, just not fatal — main.py logs them as warnings.
    assert dev.production_config_errors()
