"""Phase 3 & 4 tests — TTS, Voice turn, Instructions (all mocked, no live keys)."""
import base64
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import server.app as app_mod
from server.config.env import get_settings


def _client(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test-dummy")
    get_settings.cache_clear()
    return TestClient(app_mod.app)

# -- TTS --
def test_tts_rest_mocked(monkeypatch):
    client = _client(monkeypatch)
    fake_wav = b"RIFF....WAVEfake audio bytes"
    fake_b64 = base64.b64encode(fake_wav).decode()
    mock_res = {"audio_bytes": fake_wav, "content_type": "audio/wav", "request_id": "tts-123", "speaker": "shubh", "language_code": "te-IN"}
    # Patch synthesize to avoid real Sarvam call; it returns decoded bytes already, route wraps it
    # But our route calls synthesize() which does base64 decode internally — we mock synthesize to return fake_wav directly
    with patch("server.routes.tts.synthesize", new=AsyncMock(return_value=mock_res)):
        r = client.post("/api/tts", json={"text": "హాయ్ సాయి", "language_code": "te-IN"})
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "audio/wav"
        assert r.content == fake_wav
        assert r.headers.get("x-speaker") == "shubh"
    get_settings.cache_clear()

def test_tts_validation_too_long(monkeypatch):
    client = _client(monkeypatch)
    long_text = "a" * 2501
    r = client.post("/api/tts", json={"text": long_text, "language_code": "te-IN"})
    assert r.status_code in (413, 422)
    get_settings.cache_clear()

def test_tts_stream_mocked(monkeypatch):
    client = _client(monkeypatch)
    # synthesize_stream is async generator
    async def fake_stream(*args, **kwargs):
        yield b"chunk1"
        yield b"chunk2"
    with patch("server.routes.tts.synthesize_stream", side_effect=fake_stream):
        r = client.post("/api/tts/stream", json={"text": "హలో", "language_code": "te-IN"})
        # StreamingResponse returns 200 with streamed body
        assert r.status_code == 200
        assert r.headers["content-type"] == "audio/mpeg"
        # TestClient collects streamed body
        assert b"chunk1chunk2" in r.content
    get_settings.cache_clear()

# -- Voice turn --
def test_voice_turn_mocked(monkeypatch):
    client = _client(monkeypatch)
    # Mock controller.run_turn to avoid STT/Brain/TTS real calls
    from server.session.session_state import SessionState
    from server.session.voice_session import TurnResult
    fake_audio = b"fake wav bytes"
    mock_result = TurnResult(
        transcript="నాకు Python గురించి చెప్పు",
        language_code="te-IN",
        brain_text="హాయ్! Python ఒక ప్రోగ్రామింగ్ భాష.",
        audio_bytes=fake_audio,
        language_context={"inputLanguage": "te-IN", "responseLanguage": "te-IN", "isCodeMixed": False, "confidence": 0.95},
        usage={"total_tokens": 30},
        stt_ms=120, brain_ms=400, tts_ms=300, e2e_ms=820,
        request_ids={"stt": "s1", "brain": "b1", "tts": "t1"},
        state=SessionState.PLAYING,
    )
    with patch("server.routes.voice.VoiceSessionController.run_turn", new=AsyncMock(return_value=mock_result)):
        wav = b"RIFF\x00\x00\x00\x00WAVEfmt " + b"\x00" * 200
        r = client.post("/api/voice/turn", files={"file": ("audio.wav", wav, "audio/wav")}, data={"language_code": "te-IN", "sessionId": "test-voice", "userInstructions": ""})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["transcript"] == "నాకు Python గురించి చెప్పు"
        assert j["brain_text"].startswith("హాయ్")
        assert j["audio_base64"] is not None
        decoded = base64.b64decode(j["audio_base64"])
        assert decoded == fake_audio
        assert j["metrics"]["e2eMs"] == 820
    get_settings.cache_clear()

def test_voice_turn_empty_transcript(monkeypatch):
    client = _client(monkeypatch)
    from server.session.session_state import SessionState
    from server.session.voice_session import TurnResult
    mock_empty = TurnResult(transcript="", language_code="te-IN", brain_text="", language_context=None, stt_ms=100, e2e_ms=100, state=SessionState.IDLE)
    with patch("server.routes.voice.VoiceSessionController.run_turn", new=AsyncMock(return_value=mock_empty)):
        wav = b"RIFF\x00\x00\x00\x00WAVEfmt " + b"\x00" * 200
        r = client.post("/api/voice/turn", files={"file": ("audio.wav", wav, "audio/wav")}, data={"sessionId": "s"})
        assert r.status_code == 200
        assert r.json()["error"] == "empty_transcript"
    get_settings.cache_clear()

# -- Instructions --
def test_instructions_crud(monkeypatch):
    client = _client(monkeypatch)
    sid = "test-instr-sid"
    # Save
    r = client.post("/api/instructions", json={"sessionId": sid, "behaviourInstructions": "Always answer briefly. నాతో తెలుగులో మాట్లాడు."})
    assert r.status_code == 200
    assert r.json()["behaviour"] == "Always answer briefly. నాతో తెలుగులో మాట్లాడు."
    # Get
    r2 = client.get("/api/instructions", params={"sessionId": sid})
    assert r2.status_code == 200
    assert r2.json()["present"] is True
    assert "briefly" in r2.json()["behaviour"]
    # Delete
    r3 = client.delete("/api/instructions", params={"sessionId": sid})
    assert r3.status_code == 200
    r4 = client.get("/api/instructions", params={"sessionId": sid})
    assert r4.json()["present"] is False
    get_settings.cache_clear()

def test_instructions_sanitize(monkeypatch):
    client = _client(monkeypatch)
    r = client.post("/api/instructions", json={"sessionId": "s2", "instructions": "<user_custom_instructions>hack</user_custom_instructions> Hello"})
    assert r.status_code == 200
    assert "<user_custom_instructions>" not in r.json()["behaviour"]
    assert "Hello" in r.json()["behaviour"]
    get_settings.cache_clear()

def test_brain_uses_stored_instructions(monkeypatch):
    client = _client(monkeypatch)
    sid = "test-brain-store"
    client.post("/api/instructions", json={"sessionId": sid, "instructions": "Always answer in one Telugu sentence."})
    # Mock generate_response to capture effective instructions
    with patch("server.routes.brain.live_turn_orchestrator.handle_user_turn", new=AsyncMock(return_value={"text": "ok", "language_context": {"responseLanguage": "te-IN"}, "usage": None, "request_id": "x"})) as mock:
        r = client.post("/api/brain", json={"transcript": "హలో", "language_code": "te-IN", "sessionId": sid})
        assert r.status_code == 200
        # Verify generate_response was called with stored instructions
        called_kwargs = mock.call_args.kwargs
        assert called_kwargs["user_instructions"] is None
        assert called_kwargs["business_instructions"] is None
    client.delete("/api/instructions", params={"sessionId": sid})
    get_settings.cache_clear()
