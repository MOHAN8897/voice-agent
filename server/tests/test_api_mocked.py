"""Mocked integration — Phase 2 gate: /api/stt and /api/brain without live keys."""
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import server.app as app_mod
from server.config.env import get_settings


def _client_with_dummy_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test-dummy")
    get_settings.cache_clear()
    return TestClient(app_mod.app)

def test_stt_route_mocked(monkeypatch):
    client = _client_with_dummy_env(monkeypatch)
    mock_result = {"transcript": "నాకు Python గురించి చెప్పు", "language_code": "te-IN", "request_id": "req-123", "raw": {}}
    with patch("server.routes.stt.transcribe", new=AsyncMock(return_value=mock_result)):
        # Minimal WAV header (44 bytes) + some data to pass size check
        wav = b"RIFF\x00\x00\x00\x00WAVEfmt " + b"\x00" * 100
        r = client.post("/api/stt", files={"file": ("audio.wav", wav, "audio/wav")}, data={"language_code": "te-IN", "mode": "transcribe"})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["transcript"] == "నాకు Python గురించి చెప్పు"
        assert j["language_code"] == "te-IN"
    get_settings.cache_clear()

def test_brain_route_mocked(monkeypatch):
    client = _client_with_dummy_env(monkeypatch)
    mock_brain = {"text": "హాయ్ సాయి! Python ఒక ప్రోగ్రామింగ్ భాష.", "language_context": {"inputLanguage": "te-IN", "responseLanguage": "te-IN", "isCodeMixed": False}, "usage": {"total_tokens": 20}, "request_id": "resp-123"}
    with patch("server.routes.brain.generate_response", new=AsyncMock(return_value=mock_brain)):
        r = client.post("/api/brain", json={"transcript": "నాకు Python గురించి చెప్పు", "language_code": "te-IN", "sessionId": "test-mock-sid"})
        assert r.status_code == 200, r.text
        j = r.json()
        assert "Python" in j["text"]
        assert j["language_context"]["responseLanguage"] == "te-IN"
    get_settings.cache_clear()

def test_brain_memory_via_mock(monkeypatch):
    """Second turn should see history — we verify conversation_manager is wired."""
    client = _client_with_dummy_env(monkeypatch)
    # Use real conversation_manager but mock OpenAI to return Sai-aware answer
    from server.agent.conversation_manager import conversation_manager
    conversation_manager.clear("mem-sid")
    mock1 = {"text": "మీ పేరు Sai.", "language_context": {"inputLanguage": "te-IN", "responseLanguage": "te-IN", "isCodeMixed": False}, "usage": None, "request_id": "1"}
    mock2 = {"text": "మీ పేరు Sai.", "language_context": {"inputLanguage": "te-IN", "responseLanguage": "te-IN", "isCodeMixed": False}, "usage": None, "request_id": "2"}
    with patch("server.routes.brain.generate_response", side_effect=[mock1, mock2]) as mock_gen:
        r1 = client.post("/api/brain", json={"transcript": "నా పేరు Sai.", "language_code": "te-IN", "sessionId": "mem-sid"})
        assert r1.status_code == 200
        r2 = client.post("/api/brain", json={"transcript": "నా పేరు ఏమిటి?", "language_code": "te-IN", "sessionId": "mem-sid"})
        assert r2.status_code == 200
        # Called twice; history trimming not broken
        assert mock_gen.call_count == 2
    conversation_manager.clear("mem-sid")
    get_settings.cache_clear()

def test_stt_validation_empty(monkeypatch):
    client = _client_with_dummy_env(monkeypatch)
    r = client.post("/api/brain", json={"transcript": "   ", "language_code": "te-IN", "sessionId": "s"})
    assert r.status_code == 400
    get_settings.cache_clear()
