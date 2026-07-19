import os
import tempfile

import pytest
from fastapi.testclient import TestClient

# Isolated temp SQLite DB per test session, configured before app imports.
_tmpdir = tempfile.mkdtemp(prefix="intake-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_tmpdir, 'test.sqlite3').replace(os.sep, '/')}"
os.environ["AI_PROVIDER"] = "mock"
os.environ["EMBEDDING_PROVIDER"] = "mock"
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["SMTP_HOST"] = ""
# A developer's real .env must never leak into the suite: these would
# otherwise reach live providers (and CRM export would create real contacts).
for _key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY"):
    os.environ[_key] = ""
os.environ["CRM_PROVIDER"] = ""
os.environ["CRM_API_KEY"] = ""
os.environ["RATE_LIMIT_PER_MINUTE"] = "0"
os.environ["ADMIN_EMAIL"] = "admin@test.com"
os.environ["ADMIN_PASSWORD"] = "admin-test-pass"

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app, bootstrap  # noqa: E402


@pytest.fixture(scope="session")
def client():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        bootstrap(db)
    finally:
        db.close()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def admin_token(client):
    resp = client.post("/api/auth/login", json={"email": "admin@test.com", "password": "admin-test-pass"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture(scope="session")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture()
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
