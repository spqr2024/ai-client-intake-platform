"""Prompt management: versioning, activation, rollback, testing."""


def _create(client, headers, content, name="system", activate=True):
    resp = client.post("/api/prompts", headers=headers,
                       json={"name": name, "kind": "system", "content": content,
                             "activate": activate})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_versions_increment(client, auth_headers):
    v1 = _create(client, auth_headers, "You are a helpful intake bot. v1")
    v2 = _create(client, auth_headers, "You are a helpful intake bot. v2")
    assert v2["version"] == v1["version"] + 1
    assert v2["is_active"] == 1

    prompts = client.get("/api/prompts", headers=auth_headers).json()
    system_versions = [p for p in prompts if p["name"] == "system"]
    assert sum(p["is_active"] for p in system_versions) == 1  # single active version


def test_rollback_by_activating_older_version(client, auth_headers):
    prompts = client.get("/api/prompts", headers=auth_headers).json()
    system_versions = sorted((p for p in prompts if p["name"] == "system"),
                             key=lambda p: p["version"])
    oldest = system_versions[0]
    resp = client.post(f"/api/prompts/{oldest['id']}/activate", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["is_active"] == 1

    prompts = client.get("/api/prompts", headers=auth_headers).json()
    active = [p for p in prompts if p["name"] == "system" and p["is_active"]]
    assert len(active) == 1
    assert active[0]["version"] == oldest["version"]


def test_deactivate(client, auth_headers):
    prompt = _create(client, auth_headers, "Temporary prompt", name="experiment")
    resp = client.post(f"/api/prompts/{prompt['id']}/deactivate", headers=auth_headers)
    assert resp.json()["is_active"] == 0


def test_prompt_test_endpoint_mock(client, auth_headers):
    resp = client.post("/api/prompts/test", headers=auth_headers,
                       json={"content": "Be very formal.", "sample_input": "hi there"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "mock"
    assert "hi there" in body["output"]


def test_prompt_edits_are_audited(client, auth_headers):
    _create(client, auth_headers, "Audited prompt content", name="audited")
    entries = client.get("/api/audit", headers=auth_headers,
                         params={"action": "prompt_edited"}).json()
    assert any("audited" in e["detail"] for e in entries)


def test_prompts_require_admin(client, auth_headers):
    client.post("/api/users", headers=auth_headers,
                json={"name": "Pm", "email": "pm@test.com", "password": "secret123",
                      "role": "manager"})
    login = client.post("/api/auth/login",
                        json={"email": "pm@test.com", "password": "secret123"})
    manager_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/prompts", headers=manager_headers).status_code == 403
