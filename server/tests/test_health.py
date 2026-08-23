from fastapi.testclient import TestClient

import server.app as app_mod


def test_health_endpoint(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test-dummy")
    # Clear settings cache so new env is picked up
    from server.config.env import get_settings
    get_settings.cache_clear()
    client = TestClient(app_mod.app)
    r = client.get("/api/health")
    assert r.status_code == 200
    j = r.json()
    assert "ok" in j
    assert "presence" in j
    # Ensure no secret leaks
    body = r.text
    assert "sk-test-dummy" not in body
    assert "sarvam-test-dummy" not in body
    get_settings.cache_clear()

def test_config_check_does_not_leak(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret123")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-secret-xyz")
    from server.config.env import get_settings
    get_settings.cache_clear()
    client = TestClient(app_mod.app)
    r = client.get("/api/config-check")
    assert r.status_code == 200
    assert "sk-secret123" not in r.text
    assert "sarvam-secret-xyz" not in r.text
    get_settings.cache_clear()
