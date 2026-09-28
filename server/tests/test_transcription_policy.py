from server.services.transcription_policy import (
    attach_normalized_stack_override,
    normalize_transcription_block,
    transcription_policy_from_stack,
    _exclusive_live_post,
)


def test_policy_defaults_post_call_from_env(monkeypatch):
    monkeypatch.setenv("POST_CALL_TRANSCRIPT_ENABLED", "true")
    from server.config.env import get_settings

    get_settings.cache_clear()
    policy = transcription_policy_from_stack({"pipeline": "realtime_voice"})
    assert policy.post_call_enabled is True
    assert policy.live_enabled is False


def test_stack_overrides_opt_out_post_call():
    policy = transcription_policy_from_stack(
        {
            "transcription": {
                "live_enabled": True,
                "post_call_enabled": False,
            }
        }
    )
    assert policy.live_enabled is True
    assert policy.post_call_enabled is False


def test_exclusive_live_wins_over_post_call():
    live, post = _exclusive_live_post(True, True)
    assert live is True
    assert post is False
    policy = transcription_policy_from_stack(
        {"transcription": {"live_enabled": True, "post_call_enabled": True}}
    )
    assert policy.live_enabled is True
    assert policy.post_call_enabled is False


def test_normalize_transcription_block_exclusive():
    adj: list[str] = []
    block = normalize_transcription_block({"live_enabled": True, "post_call_enabled": True}, adjustments=adj)
    assert block["live_enabled"] is True
    assert block["post_call_enabled"] is False
    assert any("only one mode" in a for a in adj)


def test_attach_stack_override_to_meta():
    meta = {"resolved_stack": {"llm": {"provider": "openai", "model": "gpt-realtime-2.1-mini"}}}
    attach_normalized_stack_override(
        meta,
        {
            "pipeline": "realtime_voice",
            "llm": {"provider": "gemini", "model": "gemini-3.8-live"},
            "transcription": {"live_enabled": True, "post_call_enabled": False},
            "realtime_voice": {"voice": "marin"},
        },
        language="te-IN",
        tier="medium",
    )
    assert meta["stack_override"]["transcription"]["live_enabled"] is True
    assert meta["resolved_stack"]["transcription"]["live_enabled"] is True
    assert meta["resolved_stack"]["llm"]["model"] == "gemini-3.8-live"
