from __future__ import annotations

import pytest

from server.services.saas.voice_stack_defaults import COMPOSED_LANGUAGES, recommended_composed_profile
from server.services.saas.voice_stack_profiles import VoiceProfileError, validate_composed_profile


@pytest.mark.parametrize("tier,provider,mode,minimum", [
    ("low", "gemini", "streaming_rest", 30),
    ("medium", "sarvam", "websocket", 37),
])
def test_default_profiles_are_valid_streaming_drafts(tier, provider, mode, minimum):
    profile = recommended_composed_profile(tier)
    validated = validate_composed_profile(profile, tier=tier)
    assert validated["enabled"] is False
    assert not any(validated["evidence"].values())
    assert validated["stt"]["model"] == "saaras:v3-realtime"
    assert validated["llm"]["apiMode"] == "chat_completions_v1"
    model = validated["engines"][0]["models"][0]
    assert model["provider"] == provider
    assert model["apiMode"] == mode
    assert len(model["voices"]) >= minimum
    assert all(set(voice["languages"]) & set(COMPOSED_LANGUAGES) for voice in model["voices"])


def test_recommended_profile_cannot_replace_premium_or_share_mutable_state():
    with pytest.raises(VoiceProfileError, match="read-only"):
        recommended_composed_profile("premium")
    first = recommended_composed_profile("low")
    first["engines"][0]["models"][0]["voices"].clear()
    assert recommended_composed_profile("low")["engines"][0]["models"][0]["voices"]
