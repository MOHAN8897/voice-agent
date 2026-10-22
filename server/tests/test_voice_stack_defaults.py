from __future__ import annotations

import pytest

from server.services.saas.voice_stack_defaults import recommended_composed_profile
from server.services.saas.voice_stack_profiles import VoiceProfileError, validate_composed_profile


@pytest.mark.parametrize("tier,provider,mode,count", [
    ("low", "gemini", "streaming_rest", 9),
    ("medium", "sarvam", "websocket", 6),
])
def test_default_profiles_are_valid_streaming_drafts(tier, provider, mode, count):
    profile = recommended_composed_profile(tier)
    validated = validate_composed_profile(profile, tier=tier)
    assert validated["enabled"] is False
    assert not any(validated["evidence"].values())
    assert validated["stt"]["model"] == "saaras:v3-realtime"
    assert validated["llm"]["apiMode"] == "chat_completions_v1"
    model = validated["engines"][0]["models"][0]
    assert model["provider"] == provider
    assert model["apiMode"] == mode
    assert len(model["voices"]) == count
    assert all("te-IN" in voice["languages"] for voice in model["voices"])


def test_recommended_profile_cannot_replace_premium_or_share_mutable_state():
    with pytest.raises(VoiceProfileError, match="read-only"):
        recommended_composed_profile("premium")
    first = recommended_composed_profile("low")
    first["engines"][0]["models"][0]["voices"].clear()
    assert recommended_composed_profile("low")["engines"][0]["models"][0]["voices"]
