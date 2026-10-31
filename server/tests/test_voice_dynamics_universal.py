"""Tests for universal voice dynamics settings on composed tier profiles."""
from __future__ import annotations

import copy
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from server.services.saas import voice_stack_profiles, pstn_saas_stack


def _sample_profile(provider="sarvam", model="bulbul:v3"):
    return {
        "schemaVersion": 1,
        "enabled": True,
        "label": "Test Standard Tier",
        "retailRateInr": 5.0,
        "supplierCostInr": 2.0,
        "supportedLanguages": ["te-IN", "hi-IN", "en-IN"],
        "stt": {"provider": "sarvam", "model": "saaras:v2"},
        "llm": {"provider": "gemini", "modelId": "gemini-2.0-flash", "apiMode": "chat_completions_v1"},
        "engines": [
            {
                "id": provider,
                "label": f"{provider} Speech",
                "models": [
                    {
                        "id": model,
                        "label": model,
                        "provider": provider,
                        "model": model,
                        "apiMode": "websocket",
                        "voices": [
                            {"id": "voice-1", "label": "Shubh", "providerVoiceId": "shubh", "languages": ["te-IN", "hi-IN", "en-IN"]},
                        ],
                    }
                ],
            }
        ],
        "evidence": {key: True for key in voice_stack_profiles._EVIDENCE_KEYS},
        "voiceDynamics": {
            "speed": 1.25,
            "pitch": 0.05,
            "temperature": 0.85,
            "emotion": "confident",
            "volume": 1.1,
        },
    }


def test_validate_composed_profile_accepts_voice_dynamics():
    raw = _sample_profile()
    validated = voice_stack_profiles.validate_composed_profile(raw, tier="medium")
    assert "voiceDynamics" in validated
    dyn = validated["voiceDynamics"]
    assert dyn["speed"] == 1.25
    assert dyn["pace"] == 1.25
    assert dyn["pitch"] == 0.05
    assert dyn["temperature"] == 0.85
    assert dyn["emotion"] == "confident"
    assert dyn["volume"] == 1.1


@pytest.mark.asyncio
async def test_resolve_agent_selection_injects_tier_dynamics(monkeypatch):
    profile = _sample_profile(provider="cartesia", model="sonic-3.5")
    profile["voiceDynamics"] = {
        "speed": 1.2,
        "emotion": "happy",
        "volume": 1.05,
    }
    record = {
        "revision": 3,
        "profile": profile,
        "publicAliases": {
            "engines": {"cartesia": "eng_c1"},
            "models": {"cartesia::sonic-3.5": "mod_c1"},
            "voices": {"cartesia::sonic-3.5::voice-1": "voc_c1"},
        },
    }
    monkeypatch.setattr(voice_stack_profiles, "load_profile_records", AsyncMock(return_value={"medium": record}))
    monkeypatch.setattr(voice_stack_profiles, "_load_rates_without_fallback", AsyncMock(return_value={}))
    monkeypatch.setattr(voice_stack_profiles, "readiness_for_profile", lambda *_: {"ready": True, "enabled": True, "blockers": []})

    stack, snapshot = await voice_stack_profiles.resolve_agent_selection(
        environment="development",
        tier="medium",
        voice_settings={"profileRevision": 3, "engineId": "eng_c1", "modelId": "mod_c1", "voiceId": "voc_c1"},
        language="te-IN",
        allow_fallback=True,
    )
    assert stack["tts"]["config"]["speed"] == 1.2
    assert stack["tts"]["config"]["pace"] == 1.2
    assert stack["tts"]["config"]["emotion"] == "happy"
    assert stack["tts"]["config"]["volume"] == 1.05


@pytest.mark.asyncio
async def test_saas_stack_override_applies_universal_tier_dynamics(monkeypatch):
    profile = _sample_profile(provider="gnani", model="timbre-v3.0")
    profile["voiceDynamics"] = {
        "speed": 1.15,
        "pitch": 0.04,
        "volume": 1.0,
    }
    original_stack = {
        "pipeline": "composed_voice",
        "voice_flow": "composed_stages",
        "language": "te-IN",
        "stt": {"provider": "sarvam", "model": "saaras:v2", "config": {}},
        "llm": {"provider": "gemini", "model": "gemini-2.0-flash", "config": {}},
        "tts": {
            "provider": "gnani",
            "model": "timbre-v3.0",
            "config": {"speaker": "Shivani", "speed": 1.15, "pace": 1.15, "pitch": 0.04},
        },
        "_voice_stack_snapshot": {"tier": "medium"},
    }
    monkeypatch.setattr(pstn_saas_stack, "load_agent_voice_config", AsyncMock(return_value={}))
    monkeypatch.setattr(
        voice_stack_profiles, "resolve_agent_selection",
        AsyncMock(return_value=(copy.deepcopy(original_stack), {})),
    )
    # Agent does not specify speed_val; universal tier dynamics must be preserved
    stack = await pstn_saas_stack.saas_stack_override_for_agent({
        "agent_id": "real-estate-mohan",
        "default_tier": "medium",
        "environment": "development",
        "languages": ["te-IN"],
    })
    assert stack["tts"]["config"]["pace"] == 1.15
    assert stack["tts"]["config"]["pitch"] == 0.04


@pytest.mark.asyncio
@pytest.mark.parametrize("emotion", ["sarcastic", "excited", "determined", "neutral"])
async def test_documented_cartesia_emotion_survives_profile_validation_and_runtime_mapping(monkeypatch, emotion):
    from server.providers import voice_inventory
    from server.services.tts_voice_direction import cartesia_generation_config, provider_tts_payload

    # Model/voice routing has independent coverage; this regression follows the
    # persisted profile's delivery choice through the actual call resolver.
    monkeypatch.setattr(voice_inventory, "validate_voice", lambda *args: {"providerVoiceId": "voice-test"})
    raw = _sample_profile(provider="cartesia", model="sonic-3.5")
    raw["voiceDynamics"] = {"speed": 1.1, "emotion": emotion, "volume": 1.2}
    profile = voice_stack_profiles.validate_composed_profile(raw, tier="medium")
    assert profile["voiceDynamics"]["emotion"] == emotion
    record = {
        "revision": 3,
        "profile": profile,
        "publicAliases": {
            "engines": {"cartesia": "eng_c1"},
            "models": {"cartesia::sonic-3.5": "mod_c1"},
            "voices": {"cartesia::sonic-3.5::voice-1": "voc_c1"},
        },
    }
    monkeypatch.setattr(voice_stack_profiles, "load_profile_records", AsyncMock(return_value={"medium": record}))
    monkeypatch.setattr(voice_stack_profiles, "_load_rates_without_fallback", AsyncMock(return_value={}))
    monkeypatch.setattr(voice_stack_profiles, "readiness_for_profile", lambda *_: {"ready": True, "enabled": True, "blockers": []})
    stack, _ = await voice_stack_profiles.resolve_agent_selection(
        environment="development", tier="medium", language="en-IN",
        voice_settings={"profileRevision": 3, "engineId": "eng_c1", "modelId": "mod_c1", "voiceId": "voc_c1"},
    )
    values = provider_tts_payload("cartesia", "sonic-3.5", stack["tts"]["config"])
    assert cartesia_generation_config(
        emotion=values["emotion"], speed=values["speed"], volume=values["volume"],
    ) == {"emotion": emotion, "speed": 1.1, "volume": 1.2}


def test_cartesia_admin_emotion_catalog_is_complete_and_default_matches_runtime(monkeypatch):
    from server.services.tts_voice_direction import cartesia_generation_config, tts_knob_specs
    from server.config import env

    monkeypatch.setattr(env, "get_settings", lambda: SimpleNamespace())
    emotion = next(spec for spec in tts_knob_specs("cartesia", "sonic-3.5") if spec["key"] == "emotion")
    values = {option["value"] for option in emotion["options"]}
    assert len(values) == 58
    assert {"sarcastic", "excited", "determined", "neutral"} <= values
    assert "English-only" in emotion["description"]
    assert emotion["default"] == cartesia_generation_config()["emotion"] == "calm"
