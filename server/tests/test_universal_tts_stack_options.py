"""Tests for universal TTS stack selection across Economic and Standard tiers.

Verifies:
1. Admin can configure Gemini, Sarvam, or Cartesia on WebSocket for both 'low' and 'medium' tiers.
2. Chosen stack does NOT fall back to any default when credits/quota fail.
3. Gemini, Sarvam, and Cartesia WebSocket connectors stream properly and report credit exhaustion errors.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.providers.base import TTSConfig
from server.services.gemini_tts_ws import connect_gemini_tts_ws
from server.services.pstn_turn_tts import PstnTurnTtsSession
from server.services.saas.voice_stack_profiles import (
    VoiceProfileError,
    validate_composed_profile,
)


def _composed_profile_with_tts(provider: str, model: str, api_mode: str, voice_id: str = "voice-test"):
    from server.providers.voice_inventory import voices_for_model

    provider_voice = "Zephyr" if provider == "gemini" else (
        ("anushka" if model == "bulbul:v2" else "kavitha_te_conversation" if model == "bulbul:v4-flash" else "shubh")
        if provider == "sarvam" else "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4")
    row = next(row for row in voices_for_model(provider, model) if row["providerVoiceId"] == provider_voice)
    languages = [code for code in ("te-IN", "hi-IN", "en-IN") if code in row["languages"]]
    return {
        "schemaVersion": 1,
        "enabled": False,
        "supportedLanguages": ["te-IN", "hi-IN", "en-IN"],
        "stt": {"provider": "sarvam", "model": "saaras:v2"},
        "llm": {"provider": "gemini", "modelId": "gemini-2.0-flash", "apiMode": "chat_completions_v1"},
        "engines": [
            {
                "id": f"engine-{provider}",
                "label": f"{provider.title()} Engine",
                "models": [
                    {
                        "id": f"model-{model}",
                        "label": model,
                        "provider": provider,
                        "model": model,
                        "apiMode": api_mode,
                        "voices": [
                            {
                                "id": voice_id,
                                "label": "Test Voice",
                                "providerVoiceId": provider_voice,
                                "languages": languages,
                            }
                        ],
                    }
                ],
            }
        ],
        "evidence": {},
    }


@pytest.mark.parametrize("tier", ["low", "medium"])
@pytest.mark.parametrize(
    "provider,model,api_mode",
    [
        ("gemini", "gemini-3.8-flash-tts", "websocket"),
        ("gemini", "gemini-3.8-flash-lite-tts", "websocket"),
        ("sarvam", "bulbul:v3", "websocket"),
        ("sarvam", "bulbul:v2", "websocket"),
        ("sarvam", "bulbul:v4-flash", "websocket"),
        ("cartesia", "sonic-3.5", "websocket"),
        ("cartesia", "sonic-3.5-2026-05-04", "websocket"),
    ],
)
def test_all_tts_providers_supported_on_websocket_in_both_tiers(tier, provider, model, api_mode):
    """Admin can configure Gemini, Sarvam, or Cartesia on WebSocket for both low and medium tiers."""
    profile = _composed_profile_with_tts(provider, model, api_mode)
    validated = validate_composed_profile(profile, tier=tier)
    tts_model = validated["engines"][0]["models"][0]
    assert tts_model["provider"] == provider
    assert tts_model["model"] == model
    assert tts_model["apiMode"] == "websocket"


@pytest.mark.asyncio
async def test_gemini_tts_ws_connector_streams_chunks_and_emits_final(monkeypatch):
    """Test Gemini TTS WebSocket proxy protocol."""
    from server.providers.gemini_tts import GeminiTTSChunk

    async def mock_stream(*args, **kwargs):
        yield GeminiTTSChunk(audio_bytes=b"\x00\x01\x00\x02", sample_rate=24000, usage={"total_tokens": 10})
        yield GeminiTTSChunk(audio_bytes=b"\x00\x03\x00\x04", sample_rate=24000, usage={"total_tokens": 15})

    monkeypatch.setattr(
        "server.providers.gemini_tts.GeminiTTSAdapter.stream_with_metadata",
        mock_stream,
    )
    monkeypatch.setattr("server.services.gemini_tts_ws.dev_secrets_store.effective_secret", lambda *a: "fake-key")

    connector = connect_gemini_tts_ws(model="gemini-3.8-flash-tts")
    async with connector as proxy:
        await proxy.send(json.dumps({"type": "config", "data": {"speaker": "Zephyr", "language_code": "te-IN"}}))
        await proxy.send(json.dumps({"type": "text", "data": {"text": "నమస్కారం"}}))
        await proxy.send(json.dumps({"type": "flush"}))

        received = []
        async for msg in proxy:
            obj = json.loads(msg)
            received.append(obj)
            if obj.get("type") == "end_of_stream":
                break

        assert len(received) == 3
        assert received[0]["type"] == "audio"
        assert received[1]["type"] == "audio"
        assert received[2]["type"] == "end_of_stream"


@pytest.mark.asyncio
async def test_gemini_tts_ws_reports_credits_exhausted_on_429(monkeypatch):
    """When Gemini returns 429 quota exhausted, connector yields credit exhaustion error."""
    async def mock_error_stream(*args, **kwargs):
        raise RuntimeError("429 RESOURCE_EXHAUSTED: Quota exceeded for project")
        yield  # make it a generator

    monkeypatch.setattr(
        "server.providers.gemini_tts.GeminiTTSAdapter.stream_with_metadata",
        mock_error_stream,
    )
    monkeypatch.setattr("server.services.gemini_tts_ws.dev_secrets_store.effective_secret", lambda *a: "fake-key")

    connector = connect_gemini_tts_ws(model="gemini-3.8-flash-tts")
    async with connector as proxy:
        await proxy.send(json.dumps({"type": "text", "data": {"text": "Hello"}}))
        msg = await proxy.__anext__()
        obj = json.loads(msg)
        assert obj["type"] == "error"
        assert obj["code"] == "credits_exhausted"
        assert "exhausted" in obj["message"].lower()


@pytest.mark.asyncio
async def test_no_silent_fallback_when_cartesia_fails(monkeypatch):
    """PSTN session must NOT silently fall back to Sarvam if Cartesia fails/credits out."""
    voice = MagicMock()
    voice.call_id = "test-call-no-fallback"
    voice.tts_session_id = "sess-1"
    voice.sample_rate = 8000
    voice.tts_output_codec = "PCMU"
    voice._resolve_language.return_value = "te-IN"
    voice.current_generation_id = "gen-1"

    session = PstnTurnTtsSession(voice)

    monkeypatch.setattr(
        "server.services.tts_config.merge_pstn_tts_config",
        lambda *a, **kw: {"provider": "cartesia", "model": "sonic-3.5"},
    )

    # Force Cartesia connector to fail with 402 Payment Required / credits over
    fail_cm = MagicMock()
    fail_cm.__aenter__ = AsyncMock(side_effect=RuntimeError("HTTP 402 Payment Required: Cartesia credits exhausted"))
    fail_cm.__aexit__ = AsyncMock(return_value=None)

    monkeypatch.setattr(
        "server.routes.ws._connect_tts_upstream",
        lambda *args, **kwargs: fail_cm,
    )

    with pytest.raises(RuntimeError) as exc_info:
        await session.open()

    assert "credits" in str(exc_info.value).lower()
    # Confirm it did NOT silently set _merged to sarvam
    assert getattr(voice, "_tts_fallback_provider", None) != "sarvam"
    assert getattr(voice, "_tts_credits_exhausted", False) is True
    assert getattr(voice, "_tts_exhausted_provider", None) == "cartesia"
