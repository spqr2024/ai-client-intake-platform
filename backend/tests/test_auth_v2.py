"""Refresh-token rotation, logout and audit trail."""


def _login(client):
    resp = client.post(
        "/api/auth/login", json={"email": "admin@test.com", "password": "admin-test-pass"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_login_returns_refresh_token(client):
    body = _login(client)
    assert body["access_token"]
    assert body["refresh_token"]


def test_refresh_rotates_token(client):
    body = _login(client)
    old_refresh = body["refresh_token"]

    resp = client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
    assert resp.status_code == 200
    new_body = resp.json()
    assert new_body["access_token"]
    assert new_body["refresh_token"] != old_refresh

    # The old token is revoked after rotation — replay must fail.
    resp = client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
    assert resp.status_code == 401


def test_logout_revokes_refresh_token(client):
    body = _login(client)
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    resp = client.post("/api/auth/logout", headers=headers,
                       json={"refresh_token": body["refresh_token"]})
    assert resp.status_code == 204
    resp = client.post("/api/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert resp.status_code == 401


def test_invalid_refresh_rejected(client):
    resp = client.post("/api/auth/refresh", json={"refresh_token": "x" * 40})
    assert resp.status_code == 401


def test_login_is_audited(client, auth_headers):
    _login(client)
    resp = client.get("/api/audit", headers=auth_headers, params={"action": "login"})
    assert resp.status_code == 200
    entries = resp.json()
    assert any(e["actor"] == "admin@test.com" for e in entries)


def test_security_headers_present(client):
    resp = client.get("/health")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"


def test_audit_requires_admin(client, auth_headers):
    client.post(
        "/api/users",
        headers=auth_headers,
        json={"name": "Aud", "email": "aud@test.com", "password": "secret123", "role": "manager"},
    )
    login = client.post("/api/auth/login", json={"email": "aud@test.com", "password": "secret123"})
    manager_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/audit", headers=manager_headers).status_code == 403
