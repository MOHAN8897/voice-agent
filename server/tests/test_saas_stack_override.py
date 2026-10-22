"""Platform phone stack applied per agent (voice overlay + normalization)."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_saas_stack_override_uses_gemini_from_platform(monkeypatch):
    from server.services.saas import pstn_saas_stack as mod

    async def fake_resolve(_lang: str):
        return {
            "pipeline": "realtime_voice",
            "language": "te-IN",
            "llm": {"provider": "gemini", "model": "gemini-3.8-live"},
            "realtime_voice": {"voice": "marin"},
        }

    async def fake_voice_cfg(_agent_id: str):
        return {}

    monkeypatch.setattr(mod, "resolve_platform_phone_stack", fake_resolve)
    monkeypatch.setattr(mod, "load_agent_voice_config", fake_voice_cfg)

    stack = await mod.saas_stack_override_for_agent({"agent_id": "a1", "languages": ["te-IN"]})
    assert stack["llm"]["provider"] == "gemini"
    assert stack["llm"]["model"] == "gemini-3.8-live"
    assert stack["realtime_voice"]["voice"] == "te-in-csagent-5"


def test_no_admin_saved_stack_defaults_to_gemini_live_telugu(monkeypatch):
    from server.services.saas import platform_phone_stack

    monkeypatch.setattr(platform_phone_stack, "load_universal_phone_stack_raw", lambda: None)
    stack = platform_phone_stack.resolve_platform_phone_stack_sync("te-IN")

    assert stack["llm"] == {"provider": "gemini", "model": "gemini-3.8-live"}
    assert stack["realtime_voice"]["voice"] == "te-in-csagent-5"


def test_explicit_admin_openai_stack_is_preserved(monkeypatch):
    from server.services.saas import platform_phone_stack

    monkeypatch.setattr(
        platform_phone_stack,
        "load_universal_phone_stack_raw",
        lambda: {
            "stack_override": {
                "pipeline": "realtime_voice",
                "language": "te-IN",
                "llm": {"provider": "openai", "model": "gpt-realtime-2.1-mini"},
                "realtime_voice": {"voice": "marin"},
            }
        },
    )
    stack = platform_phone_stack.resolve_platform_phone_stack_sync("te-IN")

    assert stack["llm"] == {"provider": "openai", "model": "gpt-realtime-2.1-mini"}
    assert stack["realtime_voice"]["voice"] == "marin"
