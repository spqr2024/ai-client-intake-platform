def test_login_success(client):
    resp = client.post("/api/auth/login", json={"email": "admin@test.com", "password": "admin-test-pass"})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_login_wrong_password(client):
    resp = client.post("/api/auth/login", json={"email": "admin@test.com", "password": "wrong-password"})
    assert resp.status_code == 401


def test_me_requires_auth(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_returns_user(client, auth_headers):
    resp = client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "admin@test.com"
    assert body["role"] == "admin"


def test_leads_require_auth(client):
    assert client.get("/api/leads").status_code == 401


def test_manager_cannot_edit_settings(client, auth_headers):
    resp = client.post(
        "/api/users",
        headers=auth_headers,
        json={"name": "Mia", "email": "mia@test.com", "password": "secret123", "role": "manager"},
    )
    assert resp.status_code == 201

    login = client.post("/api/auth/login", json={"email": "mia@test.com", "password": "secret123"})
    manager_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = client.put("/api/settings", headers=manager_headers, json={"values": {"ai_provider": "openai"}})
    assert resp.status_code == 403
