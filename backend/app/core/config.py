from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BASE_DIR.parent / ".env", BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI Client Intake Platform"
    # "production" turns the placeholder defaults below into boot-time errors
    # (see `production_config_errors`). Anything else is treated as dev.
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    # Auto-provisions a fully populated demo workspace on first start so a
    # fresh clone looks alive immediately. Disable in production.
    demo_mode: bool = False

    database_url: str = ""
    redis_url: str = ""  # e.g. redis://localhost:6379/0 — optional, graceful fallback
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 30
    refresh_token_days: int = 14
    login_max_attempts: int = 5  # per email+IP within the lockout window
    login_lockout_minutes: int = 15

    # Base URL of the admin app, used for deep links in notifications.
    public_app_url: str = "http://localhost:3000"

    cors_origins: str = "http://localhost:3000"

    admin_email: str = "admin@example.com"
    admin_password: str = "admin12345"

    # Inbox that receives "new lead" alerts. Seeds the per-workspace
    # `staff_notification_email` runtime setting; a value saved in the admin
    # UI still wins at runtime.
    staff_notification_email: str = ""

    ai_provider: str = "mock"
    ai_model: str = ""
    ai_temperature: float = 0.4
    ai_max_tokens: int = 1024

    # Embeddings for semantic KB retrieval: mock | openai | gemini | openrouter
    embedding_provider: str = "mock"
    embedding_model: str = ""

    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    openrouter_api_key: str = ""

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_webhook_secret: str = ""

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@example.com"
    smtp_tls: bool = True

    # Bootstrap values for the per-workspace CRM settings. The admin UI still
    # owns them at runtime; these only seed the default when nothing is stored.
    crm_provider: str = ""
    crm_api_key: str = ""

    rate_limit_per_minute: int = 60

    upload_dir: Path = BASE_DIR / "uploads"
    max_upload_mb: int = 10

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        data_dir = BASE_DIR / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{(data_dir / 'intake.sqlite3').as_posix()}"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() in ("production", "prod")

    def production_config_errors(self) -> list[str]:
        """Settings that are fine locally but unsafe on a public deployment.

        These defaults exist so a fresh clone runs with zero configuration. That
        convenience becomes the danger: nothing otherwise stops a deploy from
        booting with a signing secret published in this repository, which lets
        anyone mint a valid admin token. Checked at startup so a misconfigured
        deploy fails loudly instead of serving traffic while insecure.
        """
        errors: list[str] = []

        if self.jwt_secret == "change-me-in-production":
            errors.append("JWT_SECRET is still the documented placeholder - anyone can forge tokens.")
        elif len(self.jwt_secret) < 32:
            errors.append(
                f"JWT_SECRET is only {len(self.jwt_secret)} characters; use 32+ "
                'random bytes (python -c "import secrets; print(secrets.token_hex(32))").'
            )

        if self.admin_password == "admin12345":
            errors.append("ADMIN_PASSWORD is still the documented default.")

        if self.demo_mode:
            errors.append("DEMO_MODE=true seeds fake leads - turn it off in production.")

        if self.debug:
            errors.append("DEBUG=true leaks stack traces to clients.")

        # A wildcard or localhost origin on a public deploy means any site can
        # drive the API with a logged-in user's credentials.
        for origin in self.cors_origin_list:
            if origin == "*":
                errors.append("CORS_ORIGINS=* allows any website to call the API with user credentials.")
            elif "localhost" in origin or "127.0.0.1" in origin:
                errors.append(f"CORS_ORIGINS still contains a local origin ({origin}).")

        if self.public_app_url.startswith("http://"):
            errors.append(f"PUBLIC_APP_URL is not HTTPS ({self.public_app_url}) - notification links leak.")

        if self.telegram_bot_token and not self.telegram_webhook_secret:
            errors.append(
                "TELEGRAM_WEBHOOK_SECRET is empty while a bot token is set - "
                "the webhook fails closed, so manager actions will not work."
            )

        return errors


@lru_cache
def get_settings() -> Settings:
    return Settings()
