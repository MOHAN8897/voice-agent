"""Phase 1 API contract regression fixtures — §4.8."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import server.app as app_mod
from server.config.env import get_settings


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from server.call.audio_archive import audio_archive
    from server.call.call_context import clear_all
    from server.call.call_ledger import call_ledger
    from server.call.call_store import call_store

    clear_all()
    call_ledger.reset_for_tests()
    audio_archive.reset_for_tests()
    call_store.reset_for_tests()
    get_settings.cache_clear()
    yield TestClient(app_mod.app)
    get_settings.cache_clear()


def test_settings_catalog_backward_compat(client):
    r = client.get("/api/settings/catalog")
    assert r.status_code == 200
    j = r.json()
    assert "stt" in j and "tts" in j and "openai" in j
    assert "providers" in j
    assert "config" in j
    assert j["config"]["mode"] in ("env", "frontend")


def test_providers_catalog_shape(client):
    r = client.get("/api/providers/catalog")
    assert r.status_code == 200
    j = r.json()
    assert "providers" in j and "pricing_metadata" in j
    ids = {p["id"] for p in j["providers"]}
    assert "sarvam" in ids and "openai" in ids


def test_stack_preview_endpoint(client):
    r = client.get("/api/settings/stack/preview", params={"sessionId": "default"})
    assert r.status_code == 200
    assert "stack" in r.json()
    assert r.json()["stack"]["stt"]["provider"] == "sarvam"


def test_validate_selection_endpoint(client):
    r = client.post(
        "/api/providers/sarvam/validate-selection",
        json={
            "stt": {"provider": "sarvam", "model": "saaras:v3"},
            "llm": {"provider": "openai", "model": "gpt-5.6-luna"},
            "tts": {"provider": "sarvam", "model": "bulbul:v3"},
            "language": "te-IN",
        },
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_health_includes_database(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    j = r.json()
    assert "database" in j
    assert "configured" in j["database"]


def test_providers_status_safe_metadata(client):
    r = client.get("/api/providers/status")
    assert r.status_code == 200
    j = r.json()
    assert "providers" in j
    ids = {p["id"] for p in j["providers"]}
    assert "sarvam" in ids and "openai" in ids
    for p in j["providers"]:
        assert "configured" in p and "healthy" in p and "enabled" in p
        assert "api_key" not in p


def test_call_start_contract(client):
    r = client.post("/api/call/start", json={"sessionId": "contract", "channel": "browser"})
    assert r.status_code == 200
    j = r.json()
    assert "call_id" in j
    assert "locked_versions" in j
    assert "resolved_stack" in j
    assert r.json()["resolved_stack"]["stt"]["provider"]
