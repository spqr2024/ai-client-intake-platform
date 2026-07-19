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


@lru_cache
def get_settings() -> Settings:
    return Settings()
