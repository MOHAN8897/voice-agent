"""Agent CRUD API tests — Phase 2."""
from fastapi.testclient import TestClient

import server.app as app_mod
from server.config.env import get_settings


def _client(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    get_settings.cache_clear()
    return TestClient(app_mod.app)


def _dev_headers(c: TestClient) -> dict[str, str]:
    login = c.post("/api/dev/login", json={"username": "dev", "password": "devpass"})
    assert login.status_code == 200
    csrf = login.json()["csrf_token"]
    return {"X-CSRF-Token": csrf}


def test_list_agents_has_default(monkeypatch):
    monkeypatch.setenv("DEV_PORTAL_USERNAME", "dev")
    monkeypatch.setenv("DEV_PORTAL_PASSWORD", "devpass")
    c = _client(monkeypatch)
    r = c.get("/api/agents")
    assert r.status_code == 200
    agents = r.json()["agents"]
    assert len(agents) >= 1
    get_settings.cache_clear()


def test_create_agent_respects_language(monkeypatch):
    monkeypatch.setenv("DEV_PORTAL_USERNAME", "dev")
    monkeypatch.setenv("DEV_PORTAL_PASSWORD", "devpass")
    c = _client(monkeypatch)
    created = c.post("/api/agents", json={"name": "Priya", "languages": ["en-IN"]})
    assert created.status_code == 200
    agent = created.json()["agent"]
    assert agent["languages"] == ["en-IN"]
    patched = c.patch(f"/api/agents/{agent['agent_id']}", json={"languages": ["hi-IN"]})
    assert patched.status_code == 200
    assert patched.json()["agent"]["languages"] == ["hi-IN"]
    deleted = c.delete(f"/api/agents/{agent['agent_id']}")
    assert deleted.status_code == 200
    listed = c.get("/api/agents")
    ids = [a["agent_id"] for a in listed.json()["agents"]]
    assert agent["agent_id"] not in ids
    get_settings.cache_clear()


def test_create_and_patch_agent(monkeypatch):
    monkeypatch.setenv("DEV_PORTAL_USERNAME", "dev")
    monkeypatch.setenv("DEV_PORTAL_PASSWORD", "devpass")
    c = _client(monkeypatch)
    created = c.post("/api/agents", json={"name": "sales-bot"})
    assert created.status_code == 200
    agent_id = created.json()["agent"]["agent_id"]
    patched = c.patch(f"/api/agents/{agent_id}", json={"defaultTier": "low"})
    assert patched.status_code == 200
    assert patched.json()["agent"]["default_tier"] == "low"
    get_settings.cache_clear()


def test_platform_brain_requires_dev_session(monkeypatch):
    monkeypatch.setenv("DEV_PORTAL_USERNAME", "dev")
    monkeypatch.setenv("DEV_PORTAL_PASSWORD", "devpass")
    c = _client(monkeypatch)
    denied = c.get("/api/platform-brain/draft")
    assert denied.status_code == 401
    headers = _dev_headers(c)
    preview = c.get("/api/platform-brain", headers=headers)
    assert preview.status_code == 200
    saved = c.put(
        "/api/platform-brain/draft",
        headers=headers,
        json={"body": "Platform rules for testing draft retrieval. Keep this long enough."},
    )
    assert saved.status_code == 200
    draft = c.get("/api/platform-brain/draft", headers=headers)
    assert draft.status_code == 200
    body = draft.json()["draft"]
    assert body["status"] == "draft"
    assert "Platform rules for testing" in body["body"]
    get_settings.cache_clear()
