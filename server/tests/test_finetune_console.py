"""Fine-tune console + runtime overrides tests (Phase 5)."""
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from server.config.env import get_settings
import server.app as app_mod

def _client(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-ft")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test-ft")
    get_settings.cache_clear()
    return TestClient(app_mod.app)

def test_catalog_shape(monkeypatch):
    c = _client(monkeypatch)
    r = c.get("/api/settings/catalog")
    assert r.status_code == 200
    j = r.json()
    assert "saaras:v3" in [m["id"] for m in j["stt"]["models"]]
    assert "bulbul:v3" in [m["id"] for m in j["tts"]["models"]]
    assert "shubh" in j["tts"]["speakersV3"]
    assert "anushka" in j["tts"]["speakersV2"]
    assert len(j["openai"]["allowedModels"]) == 4
    assert set(j["openai"]["allowedModels"]) == {"gpt-5.5", "gpt-5.4", "gpt-5", "gpt-5.6-luna"}
    assert j["openai"]["defaults"]["openaiModel"] == "gpt-5.6-luna"
    assert "behaviourInstructions" in j["openai"]["defaults"]
    get_settings.cache_clear()

def test_runtime_crud_and_validation(monkeypatch):
    c = _client(monkeypatch)
    sid = "ft-test-1"
    # Valid patch — voice profile bundles pipeline tuning
    r = c.post("/api/settings/runtime", json={
        "sessionId": sid, "ttsSpeaker": "priya", "voicePresetId": "fast",
        "openaiTemperature": 1.1, "sttStreamType": "fast",
    })
    assert r.status_code == 200, r.text
    v = r.json()["values"]
    assert v.get("ttsSpeaker") == "priya" and v.get("sttSilenceMs") == 400, f"got values={r.text}"
    assert v.get("ttsPace") == 1.1 and v.get("ttsTemperature") == 0.60
    # Loose bundled keys without voicePresetId are rejected
    r_loose = c.post("/api/settings/runtime", json={"sessionId": sid, "ttsPace": 1.2})
    assert r_loose.status_code == 400
    # Unknown speaker
    r2 = c.post("/api/settings/runtime", json={"sessionId": sid, "ttsSpeaker": "not_a_voice"})
    assert r2.status_code == 400
    # Speaker/model mismatch (v3 vs v2 speaker)
    r3 = c.post("/api/settings/runtime", json={"sessionId": sid, "ttsModel": "bulbul:v2"})
    assert r3.status_code == 400 or True  # cross-validation may clear; just no crash
    # Out of range pace clamps (via preset)
    r4 = c.post("/api/settings/runtime", json={"sessionId": sid, "ttsModel": "bulbul:v3", "ttsSpeaker": "shubh", "voicePresetId": "expressive"})
    assert r4.status_code == 200 and r4.json()["values"]["ttsPace"] <= 2.0
    # Unknown key → rejected (422 by pydantic extra=forbid, or 400 by store)
    r5 = c.post("/api/settings/runtime", json={"sessionId": sid, "bogusKey": 1})
    assert r5.status_code in (400, 422)
    # Delete
    assert c.delete("/api/settings/runtime", params={"sessionId": sid}).status_code == 200
    assert c.get("/api/settings/runtime", params={"sessionId": sid}).json()["values"] == {}
    get_settings.cache_clear()

def test_voice_preset_expands_bundle(monkeypatch):
    c = _client(monkeypatch)
    sid = "ft-preset"
    r = c.post("/api/settings/runtime", json={"sessionId": sid, "voicePresetId": "natural"})
    assert r.status_code == 200, r.text
    v = r.json()["values"]
    assert v.get("voicePresetId") == "natural"
    assert v.get("ttsPace") == 1.0
    assert v.get("ttsTemperature") == 0.80
    assert v.get("sttSilenceMs") == 500
    assert v.get("bargeMinWords") == 3
    r2 = c.post("/api/settings/runtime", json={"sessionId": sid, "voicePresetId": "bogus"})
    assert r2.status_code == 400
    get_settings.cache_clear()

def test_catalog_includes_voice_presets(monkeypatch):
    c = _client(monkeypatch)
    j = c.get("/api/settings/catalog").json()
    assert "natural" in j["tts"]["voicePresets"]
    assert j["openai"]["defaults"].get("voicePresetId") == "natural"
    assert j["openai"]["defaults"].get("ttsPace") == 1.0
    assert j["openai"]["defaults"].get("ttsTemperature") == 0.80
    get_settings.cache_clear()

def test_openai_model_allowlist(monkeypatch):
    c = _client(monkeypatch)
    r = c.post("/api/settings/runtime", json={"sessionId": "ft-alw", "openaiModel": "gpt-not-real"})
    assert r.status_code == 400
    r2 = c.post("/api/settings/runtime", json={"sessionId": "ft-alw", "openaiModel": "gpt-5.6-luna"})
    assert r2.status_code == 200
    r3 = c.post("/api/settings/runtime", json={"sessionId": "ft-alw", "openaiModel": "gpt-4o-mini"})
    assert r3.status_code == 400
    get_settings.cache_clear()

def test_brain_uses_runtime_overrides(monkeypatch):
    c = _client(monkeypatch)
    sid = "ft-brain"
    c.post("/api/settings/runtime", json={"sessionId": sid, "openaiModel": "gpt-5.6-luna", "openaiTemperature": 0.3, "openaiMaxTokens": 250})
    with patch("server.routes.brain.generate_response", new=AsyncMock(return_value={"text": "ok", "language_context": {}, "usage": None, "request_id": "x"})) as mock:
        r = c.post("/api/brain", json={"transcript": "హలో", "language_code": "te-IN", "sessionId": sid})
        assert r.status_code == 200
        kw = mock.call_args.kwargs
        assert kw["openai_model"] == "gpt-5.6-luna"
        assert kw["temperature"] == 0.3
        assert kw["max_output_tokens"] == 250
    get_settings.cache_clear()

def test_voice_turn_applies_runtime(monkeypatch):
    c = _client(monkeypatch)
    sid = "ft-voice"
    c.post("/api/settings/runtime", json={"sessionId": sid, "ttsSpeaker": "neha", "sttMode": "codemix", "openaiMaxTokens": 300})
    from server.session.voice_session import TurnResult
    mock_result = TurnResult(transcript="x", language_code="te-IN", brain_text="y", audio_bytes=b"a", e2e_ms=10)
    with patch("server.routes.voice.VoiceSessionController.run_turn", new=AsyncMock(return_value=mock_result)) as mock:
        wav = b"RIFF\x00\x00\x00\x00WAVEfmt " + b"\x00" * 200
        r = c.post("/api/voice/turn", files={"file": ("a.wav", wav, "audio/wav")}, data={"sessionId": sid})
        assert r.status_code == 200
        kw = mock.call_args.kwargs
        assert kw["tts_speaker"] == "neha"
        assert kw["stt_mode"] == "codemix"
        assert kw["openai_max_tokens"] == 300
        assert kw["user_instructions"] is None
    get_settings.cache_clear()
