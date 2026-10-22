"""Unit tests for dynamic tier duplication, fault isolation, and Gemini 3.8 Live tier integration."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from server.services.saas.voice_stack_profiles import (
    canonical_voice_tier,
    validate_composed_profile,
    VoiceProfileError,
)
from server.services.saas.voice_stack_defaults import recommended_composed_profile
from server.services.pstn_stack import normalize_pstn_stack_override
from server.services.saas.pstn_saas_stack import saas_stack_override_for_agent
from server.providers.catalog_refresh import apply_live_fx_to_catalog


def test_canonical_voice_tier_allows_custom_and_premium():
    # Base canonical tiers
    assert canonical_voice_tier("low") == "low"
    assert canonical_voice_tier("medium") == "medium"
    assert canonical_voice_tier("premium") == "premium"
    assert canonical_voice_tier("LOW") == "low"
    assert canonical_voice_tier("  Premium  ") == "premium"

    # Custom dynamic tiers
    assert canonical_voice_tier("low_copy_1") == "low_copy_1"
    assert canonical_voice_tier("med_copy_2") == "med_copy_2"
    assert canonical_voice_tier("custom_tier") == "custom_tier"
    assert canonical_voice_tier("tier_123") == "tier_123"

    # Invalid slug characters or lengths
    with pytest.raises(VoiceProfileError):
        canonical_voice_tier("invalid slug with spaces")
    with pytest.raises(VoiceProfileError):
        canonical_voice_tier("tier-with-hyphens!")
    with pytest.raises(VoiceProfileError):
        canonical_voice_tier("a" * 25)  # > 20 characters
    with pytest.raises(VoiceProfileError):
        canonical_voice_tier("")


def test_recommended_composed_profile_premium():
    prof = recommended_composed_profile("premium")
    assert prof["schemaVersion"] == 1
    assert prof["stt"]["provider"] == "gemini"
    assert prof["stt"]["model"] == "gemini-3.8-live-audio"
    assert prof["llm"]["provider"] == "gemini"
    assert prof["llm"]["modelId"] == "gemini-3.8-live"
    assert prof["llm"]["apiMode"] == "websocket"
    assert prof["engines"][0]["models"][0]["model"] == "gemini-3.8-live"
    assert prof["engines"][0]["models"][0]["apiMode"] == "websocket"


def test_validate_composed_profile_custom_tier():
    profile_payload = {
        "schemaVersion": 1,
        "enabled": True,
        "label": "My Custom Low Copy",
        "supportedLanguages": ["te-IN", "en-IN"],
        "stt": {"provider": "sarvam", "model": "saaras:v2"},
        "llm": {"provider": "gemini", "modelId": "gemini-2.0-flash", "apiMode": "chat_completions_v1"},
        "engines": [
            {
                "id": "sarvam",
                "label": "Sarvam Bulbul",
                "models": [
                    {
                        "id": "bulbul:v3",
                        "label": "bulbul:v3",
                        "provider": "sarvam",
                        "model": "bulbul:v3",
                        "apiMode": "websocket",
                        "voices": [
                            {"id": "voice-shubh", "providerVoiceId": "shubh", "label": "Shubh", "languages": ["te-IN", "en-IN"]}
                        ],
                    }
                ],
            }
        ],
        "evidence": {
            "sarvamModelAccess": True,
            "sttVerified": True,
            "ttsCatalogVerified": True,
            "toolsVerified": True,
            "capacityVerified": True,
            "mediaFormatsVerified": True,
            "credentialRefConfigured": True,
        },
    }

    validated = validate_composed_profile(profile_payload, tier="low_copy_1", allow_premium=True)
    assert validated["label"] == "My Custom Low Copy"
    assert validated["engines"][0]["models"][0]["model"] == "bulbul:v3"


def test_pstn_stack_normalization_for_premium_and_composed():
    # Premium tier with realtime pipeline
    premium_raw = {
        "pipeline": "realtime_voice",
        "language": "te-IN",
        "llm": {"provider": "gemini", "model": "gemini-3.8-live"},
        "realtime_voice": {
            "voice": "Puck",
            "turn_detection": "server_vad",
        },
    }
    norm_prem, _ = normalize_pstn_stack_override(premium_raw, language="te-IN", tier="premium")
    assert norm_prem["pipeline"] == "realtime_voice"
    assert norm_prem["llm"]["model"] == "gemini-3.8-live"

    # Composed custom duplicated tier with full stages snapshot
    composed_raw = {
        "pipeline": "composed_voice",
        "voice_flow": "composed_stages",
        "language": "te-IN",
        "_voice_stack_snapshot": {"tier": "low_copy_1"},
        "stt": {"provider": "sarvam", "model": "saaras:v2", "config": {}},
        "llm": {"provider": "gemini", "model": "gemini-2.0-flash", "config": {}},
        "tts": {"provider": "sarvam", "model": "bulbul:v3", "config": {}},
    }
    norm_comp, _ = normalize_pstn_stack_override(composed_raw, language="te-IN", tier="low_copy_1")
    assert norm_comp["pipeline"] == "composed_voice"
    assert norm_comp["stt"]["provider"] == "sarvam"


@pytest.mark.asyncio
async def test_saas_stack_override_for_agent_routing():
    agent = {
        "id": "agent-test-123",
        "default_tier": "premium",
        "voice_settings": {"language": "te-IN"},
    }

    with patch("server.services.saas.pstn_saas_stack.resolve_platform_phone_stack") as mock_stack:
        mock_stack.return_value = {
            "pipeline": "realtime_voice",
            "language": "te-IN",
            "llm": {"provider": "gemini", "model": "gemini-3.8-live"},
            "realtime_voice": {"voice": "Puck"},
        }
        override = await saas_stack_override_for_agent(agent)
        assert override["pipeline"] == "realtime_voice"
        assert override["llm"]["model"] == "gemini-3.8-live"


def test_catalog_refresh_fx_fallback():
    with patch("server.services.usage_pricing.resolve_fx_rate_inr", side_effect=Exception("FX network error")):
        catalog = {"providers": []}
        result = apply_live_fx_to_catalog(catalog)
        assert result.get("fx_rate_inr") == 94.0
