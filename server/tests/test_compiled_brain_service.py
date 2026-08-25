"""Compiled brain service tests — Phase 2."""
import pytest

from server.brain.compiled_brain_service import compiled_brain_service
from server.brain.agent_service import agent_service


@pytest.fixture
def brain_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    from server.config.env import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_compile_produces_version_and_checksum(brain_env):
    agent = await agent_service.ensure_default_agent()
    snap = await compiled_brain_service.compile_for_agent(agent["agent_id"])
    assert snap["compiled_version"].startswith("cb_v")
    assert snap["checksum"]
    assert snap["token_estimate"] > 0
    assert "STATIC OUTPUT RULES" in snap["compiled_text"] or "static" in snap["compiled_text"].lower()


@pytest.mark.asyncio
async def test_publish_pipeline(brain_env):
    agent = await agent_service.ensure_default_agent()
    snap = await compiled_brain_service.publish_agent_brain(agent["agent_id"])
    assert snap["compiled_version"]
    active = await compiled_brain_service.get_active_for_agent(agent["agent_id"])
    assert active["compiled_version"] == snap["compiled_version"]
