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
    assert stack["realtime_voice"]["voice"] == "marin"
