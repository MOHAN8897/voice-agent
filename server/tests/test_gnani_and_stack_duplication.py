"""Tests for Gnani TTS, Cartesia, Sarvam Bulbul v4 Flash, voice anonymization, and stack duplication."""
from __future__ import annotations

import asyncio
import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from server.config.constants import constants
from server.providers.base import StageSelection, TTSConfig
from server.services import composed_voice_session
from server.services.saas import composed_costing, voice_catalog, voice_preview, voice_stack_profiles


def test_constants_and_models_configured():
    # Verify bulbul:v4-flash is in constants
    assert "bulbul:v4-flash" in constants.TTS_MODELS
    # Verify Gnani models
    assert "timbre-v3.0" in constants.GNANI_TTS_MODELS
    assert "timbre-v2.5" in constants.GNANI_TTS_MODELS
    assert constants.GNANI_DEFAULT_MODEL == "timbre-v3.0"
    assert constants.GNANI_TTS_WS == "wss://api.vachana.ai/api/v1/tts"


def test_voice_catalog_uses_documented_model_specific_gnani_voices():
    rows = [row for row in voice_catalog.phone_voice_catalog() if row.get("provider") == "gnani"]
    assert len(rows) == 55
    assert any(row["providerVoiceId"] == "Nalini" and row["model"] == "timbre-v2.5" for row in rows)
    assert any(row["providerVoiceId"] == "Shivani" and row["model"] == "timbre-v3.0" for row in rows)


def test_voice_stack_profile_labels_anonymized():
    # Gnani
    assert voice_stack_profiles._clean_catalog_voice_label("Nalini (Female)", "voice-gnani-1", "low") == "Voice 1"
    assert voice_stack_profiles._clean_catalog_voice_label("Pranav (Male)", "voice-gnani-2", "medium") == "Voice 2"

    # Cartesia
    assert voice_stack_profiles._clean_catalog_voice_label("Sonic Natural", "voice-cartesia-1", "low") == "Voice 1"
    assert voice_stack_profiles._clean_catalog_voice_label("Sonic Confident", "voice-cartesia-2", "medium") == "Voice 2"

    # Metadata belongs to the exact supplier ID; numbered labels carry none.
    gnani_meta = voice_stack_profiles._resolve_catalog_voice_metadata("Shivani", "low")
    assert gnani_meta["gender"] == "female"
    assert voice_stack_profiles._resolve_catalog_voice_metadata("voice-cartesia-2", "medium")["gender"] == ""


def test_voice_preview_requires_exact_model_voice_and_rejects_numbered_aliases():
    assert voice_preview.resolve_preview_voice("Shivani", provider="gnani", model="timbre-v3.0", language="te-IN")[0] == "Shivani"
    for speaker in ("Nalini", "voice-gnani-1", "voice-gnani-4"):
        with pytest.raises(ValueError):
            voice_preview.resolve_preview_voice(speaker, provider="gnani", model="timbre-v3.0", language="te-IN")
    with pytest.raises(ValueError):
        voice_preview.resolve_preview_voice("voice-cartesia-1", provider="cartesia", model="sonic-3.5")


def test_gnani_audio_tags_injected_in_composed_prompt():
    ctx_gnani = SimpleNamespace(
        compiled_brain_text="Only speak Telugu. Keep business hours 9am to 6pm.",
        compiled_brain_version="v2",
        resolved_stack=SimpleNamespace(
            language="te-IN",
            llm=StageSelection("gemini", "gemini-2.0-flash", {"api_mode": "chat_completions_v1"}),
            tts=StageSelection("gnani", "timbre-v3.0", {"api_mode": "websocket"}),
        ),
    )
    prompt_gnani = composed_voice_session.composed_system_prompt(ctx_gnani)
    assert "[Gnani Audio Tags Expressive Guidelines]" in prompt_gnani
    assert "<laugh>" not in prompt_gnani  # no forced laughter on ordinary business calls
    assert "<pauses>" in prompt_gnani
    assert "<excited>" in prompt_gnani

    # Compare with non-gnani prompt
    ctx_gemini = SimpleNamespace(
        compiled_brain_text="Only speak Telugu. Keep business hours 9am to 6pm.",
        compiled_brain_version="v2",
        resolved_stack=SimpleNamespace(
            language="te-IN",
            llm=StageSelection("gemini", "gemini-2.0-flash", {"api_mode": "chat_completions_v1"}),
            tts=StageSelection("gemini", "gemini-3.8-flash-tts", {"api_mode": "websocket"}),
        ),
    )
    prompt_gemini = composed_voice_session.composed_system_prompt(ctx_gemini)
    assert "[Gnani Audio Tags Expressive Guidelines]" not in prompt_gemini


def test_composed_costing_tariffs_for_gnani_and_bulbul_v4():
    rates = composed_costing.default_provider_rates()
    # Check bulbul:v4-flash rate
    v4_tariff = next((r for r in rates if r["provider"] == "sarvam" and r["model"] == "bulbul:v4-flash"), None)
    assert v4_tariff is not None
    assert v4_tariff["price"] == "2"
    assert v4_tariff["currency"] == "INR"

    # Check Gnani timbre-v3.0 rate
    gnani_v3_tariff = next((r for r in rates if r["provider"] == "gnani" and r["model"] == "timbre-v3.0"), None)
    assert gnani_v3_tariff is not None
    assert gnani_v3_tariff["price"] == "3.5"
    assert gnani_v3_tariff["currency"] == "INR"

    # Check Gnani timbre-v2.5 rate
    gnani_v25_tariff = next((r for r in rates if r["provider"] == "gnani" and r["model"] == "timbre-v2.5"), None)
    assert gnani_v25_tariff is not None
    assert gnani_v25_tariff["price"] == "2.5"
    assert gnani_v25_tariff["currency"] == "INR"

    # Calculate pricing with snapshot
    snapshot_v4 = composed_costing.build_cost_snapshot(
        {"version": 1, "configured": True, "rates": rates},
        {"tier": "medium", "stt": {"provider": "sarvam", "model": "saaras:v3-realtime"}, "llm": {"provider": "sarvam", "model": "sarvam-105b-conversations"}, "tts": {"provider": "sarvam", "model": "bulbul:v4-flash"}},
        fx_rate_inr=85.0,
    )
    usage_v4 = {
        "stt": {"audio_seconds": 60},
        "llm": {"input_tokens": 1000, "output_tokens": 500},
        "tts": {"input_characters": 1000},
    }
    price_v4 = composed_costing.price_composed_usage(snapshot_v4, usage_v4)
    assert price_v4["status"] == "ready"
    assert price_v4["stages"]["tts"]["costInr"] == "2"

    snapshot_gnani = composed_costing.build_cost_snapshot(
        {"version": 1, "configured": True, "rates": rates},
        {"tier": "low", "stt": {"provider": "sarvam", "model": "saaras:v3-realtime"}, "llm": {"provider": "sarvam", "model": "sarvam-105b-conversations"}, "tts": {"provider": "gnani", "model": "timbre-v3.0"}},
        fx_rate_inr=85.0,
    )
    usage_gnani = {
        "stt": {"audio_seconds": 60},
        "llm": {"input_tokens": 1000, "output_tokens": 500},
        "tts": {"input_characters": 2000},
    }
    price_gnani = composed_costing.price_composed_usage(snapshot_gnani, usage_gnani)
    assert price_gnani["status"] == "ready"
    assert price_gnani["stages"]["tts"]["costInr"] == "7.0"  # 2 * 3.5 INR


def test_validate_composed_profile_with_gnani_and_cartesia(monkeypatch):
    from server.providers import voice_inventory
    original = voice_inventory.voices_for_model
    monkeypatch.setattr(voice_inventory, "_voice_indexes", {})
    monkeypatch.setattr(voice_inventory, "voices_for_model", lambda provider, model: [
        {"id": "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4", "providerVoiceId": "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4", "languages": ["te-IN", "en-IN"]}
    ] if provider == "cartesia" else original(provider, model))
    # Valid low-tier profile with Gnani
    gnani_profile = {
        "schemaVersion": 1,
        "enabled": True,
        "label": "Low Latency Gnani Stack",
        "supportedLanguages": ["te-IN", "hi-IN", "en-IN"],
        "stt": {"provider": "sarvam", "model": "saaras:v2"},
        "llm": {"provider": "gemini", "modelId": "gemini-2.0-flash", "apiMode": "chat_completions_v1"},
        "engines": [
            {
                "id": "gnani",
                "label": "Gnani Timbre",
                "models": [
                    {
                        "id": "timbre-v3.0",
                        "label": "timbre-v3.0",
                        "provider": "gnani",
                        "model": "timbre-v3.0",
                        "apiMode": "websocket",
                        "voices": [
                            {"id": "voice-gnani-1", "providerVoiceId": "Shivani", "label": "Voice 1", "languages": ["te-IN", "hi-IN"]},
                            {"id": "voice-gnani-2", "providerVoiceId": "Prakash", "label": "Voice 2", "languages": ["te-IN", "en-IN"]},
                        ],
                    }
                ],
            }
        ],
        "evidence": {k: True for k in voice_stack_profiles._EVIDENCE_KEYS},
    }

    validated = voice_stack_profiles.validate_composed_profile(gnani_profile, tier="low")
    assert validated["schemaVersion"] == 1
    assert validated["label"] == "Low Latency Gnani Stack"
    assert validated["engines"][0]["models"][0]["provider"] == "gnani"
    assert validated["engines"][0]["models"][0]["model"] == "timbre-v3.0"

    # Duplicating stack with Cartesia for medium tier
    cartesia_profile = {
        "schemaVersion": 1,
        "enabled": False,
        "label": "Duplicated Cartesia Stack",
        "supportedLanguages": ["te-IN", "en-IN"],
        "stt": {"provider": "cartesia", "model": "ink-whisper"},
        "llm": {"provider": "sarvam", "modelId": "sarvam-105b-conversations", "apiMode": "chat_completions_v1"},
        "engines": [
            {
                "id": "cartesia",
                "label": "Cartesia Sonic",
                "models": [
                    {
                        "id": "sonic-3.5",
                        "label": "sonic-3.5",
                        "provider": "cartesia",
                        "model": "sonic-3.5",
                        "apiMode": "websocket",
                        "voices": [
                            {"id": "voice-cartesia-1", "providerVoiceId": "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4", "label": "Voice 1", "languages": ["te-IN", "en-IN"]},
                        ],
                    }
                ],
            }
        ],
        "evidence": {k: True for k in voice_stack_profiles._EVIDENCE_KEYS},
    }

    validated_cartesia = voice_stack_profiles.validate_composed_profile(cartesia_profile, tier="medium")
    assert validated_cartesia["label"] == "Duplicated Cartesia Stack"
    assert validated_cartesia["engines"][0]["models"][0]["provider"] == "cartesia"


@pytest.mark.asyncio
async def test_gnani_ws_wav_header_stripping_and_events():
    from server.services.gnani_tts_ws import connect_gnani_tts_ws

    # Create dummy WAV with 44-byte header + 100 bytes PCM audio
    wav_header = b"RIFF" + b"\x00" * 4 + b"WAVE" + b"fmt " + b"\x00" * 20 + b"data" + b"\x00" * 4
    assert len(wav_header) == 44
    pcm_audio = b"\x01\x02" * 50
    full_wav = wav_header + pcm_audio

    # Mock websocket connection
    mock_ws = AsyncMock()
    mock_ws.recv.side_effect = [
        full_wav,
    ]
    mock_connect = AsyncMock(return_value=mock_ws)

    with patch("server.services.gnani_tts_ws.websockets.connect", mock_connect):
        with patch("server.services.gnani_tts_ws._gnani_api_key", return_value="vach_test_key_123"):
            async with connect_gnani_tts_ws(
                model="timbre-v3.0",
            ) as proxy:
                await proxy.send(json.dumps({"type": "config", "data": {"speaker": "Shivani", "language_code": "te-IN"}}))
                await proxy.send(json.dumps({"type": "text", "data": {"text": "నమస్కారం"}}))

                # Check outgoing request
                sent_req = json.loads(mock_ws.send.call_args[0][0])
                assert sent_req["text"] == "నమస్కారం"
                assert sent_req["voice"] == "Shivani"
                assert sent_req["model"] == "timbre-v3.0"

                # Check received audio chunk
                chunk_str = await proxy.__anext__()
                chunk = json.loads(chunk_str)
                assert chunk["type"] == "audio"
                decoded = base64.b64decode(chunk["data"]["audio"])
                assert decoded == pcm_audio
                assert not decoded.startswith(b"RIFF")


@pytest.mark.asyncio
async def test_gnani_ws_credit_exhaustion_detection():
    from server.services.gnani_tts_ws import connect_gnani_tts_ws

    mock_ws = AsyncMock()
    # Mock credit exhaustion message
    mock_ws.recv.side_effect = [
        json.dumps({"type": "error", "status": 402, "message": "Insufficient credits or quota exhausted"}),
    ]
    mock_connect = AsyncMock(return_value=mock_ws)

    with patch("server.services.gnani_tts_ws.websockets.connect", mock_connect):
        with patch("server.services.gnani_tts_ws._gnani_api_key", return_value="vach_test_key_123"):
            async with connect_gnani_tts_ws(
                model="timbre-v3.0",
            ) as proxy:
                chunk_str = await proxy.__anext__()
                chunk = json.loads(chunk_str)
                assert chunk["type"] == "error"
                assert chunk["code"] == "credits_exhausted"


def test_static_sample_never_substitutes_another_speaker():
    assert voice_preview.find_static_sample("skylar-does-not-exist", "te-IN") is None
    assert voice_preview.find_static_sample("../voice-cartesia-1", "te-IN") is None


@pytest.mark.asyncio
async def test_resolve_agent_selection_accepts_custom_tier():
    from server.services.saas.voice_stack_profiles import resolve_agent_selection, VoiceProfileError

    # Custom slug should not raise invalid_composed_tier
    # If the record is not in DB, it raises profile_unavailable rather than invalid_composed_tier
    with pytest.raises(VoiceProfileError) as exc_info:
        await resolve_agent_selection(
            environment="development",
            tier="low_copy_1",
            voice_settings={"profileRevision": 1},
            language="te-IN",
        )
    assert exc_info.value.code != "invalid_composed_tier"
