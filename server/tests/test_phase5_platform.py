"""Phase 5 tests — auth, transcode, exotel, campaigns."""
from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from server.config.env import get_settings
from server.services.audio_transcode import mulaw_to_pcm16, pcm16_to_mulaw


def _client(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-phase5")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test-phase5")
    monkeypatch.setenv("DEV_PORTAL_USERNAME", "dev")
    monkeypatch.setenv("DEV_PORTAL_PASSWORD", "devpass")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    get_settings.cache_clear()
    import server.app as app_mod

    return TestClient(app_mod.app)


def test_audio_transcode_roundtrip():
    pcm = b"\x00\x01" * 160
    mulaw = pcm16_to_mulaw(pcm, 16000)
    back = mulaw_to_pcm16(mulaw, 16000)
    assert len(back) > 0


def test_dev_login_and_stack(monkeypatch):
    c = _client(monkeypatch)
    r = c.post("/api/dev/login", json={"username": "dev", "password": "devpass"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    csrf = r.json()["csrf_token"]
    r2 = c.get("/api/dev/stack/tiers", headers={"X-CSRF-Token": csrf})
    assert r2.status_code == 200
    assert "tiers" in r2.json()
    get_settings.cache_clear()


def test_exotel_passthru(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("APP_ENVIRONMENT", "development")
    get_settings.cache_clear()
    import server.app as app_mod

    c = TestClient(app_mod.app)
    r = c.post("/api/exotel/passthru?CallSid=test-sid&From=%2B911234567890")
    assert r.status_code == 200
    get_settings.cache_clear()


def test_exotel_status(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    get_settings.cache_clear()
    import server.app as app_mod

    c = TestClient(app_mod.app)
    r = c.get("/api/exotel/status")
    assert r.status_code == 200
    body = r.json()
    assert "enabled" in body
    assert "handshake_ok" in body
    get_settings.cache_clear()
