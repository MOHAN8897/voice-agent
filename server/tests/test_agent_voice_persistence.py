"""A saved voice choice must round-trip: PATCH, read back, reload, language switch.

The console reported voices "not persisting" while every PATCH answered 200.
These pin the server half of that contract: what a revision-checked save
stores is what the agent read returns, a later save builds on the returned
revision, and a script/language save (no voice fields) never resets the voice.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from server.brain.agent_service import AgentService
from server.db.models.entities import Agent
from server.services.saas import voice_stack_profiles


class _Result:
    def __init__(self, row):
        self.row = row

    def scalar_one_or_none(self):
        return self.row


class _Session:
    def __init__(self, row):
        self.row = row
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, _statement):
        return _Result(self.row)

    async def commit(self):
        self.commits += 1

    async def refresh(self, _row):
        return None


def _agent() -> Agent:
    return Agent(
        agent_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        name="Persistence test",
        status="active",
        active_compiled_brain_version=None,
        default_tier="medium",
        languages=["te-IN"],
        memory_schema="compact_v1",
        environment="development",
        voice_settings={
            "stackSelectionVersion": 1, "profileRevision": 44, "engineId": "eng_a",
            "modelId": "mod_a", "voiceId": "voc_first", "_voice_revision": 7,
        },
        recording_disclosure_enabled=False,
        recording_disclosure_text=None,
    )


def _pick(voice_id: str, *, profile_revision: int = 44) -> dict:
    return {
        "stackSelectionVersion": 1, "profileRevision": profile_revision,
        "engineId": "eng_a", "modelId": "mod_a", "voiceId": voice_id,
    }


@pytest.fixture
def stored(monkeypatch):
    row = _agent()
    session = _Session(row)
    monkeypatch.setattr("server.brain.agent_service.get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(voice_stack_profiles, "validate_agent_voice_selection_async", AsyncMock())
    monkeypatch.setattr(voice_stack_profiles, "validate_agent_language_for_tier", AsyncMock())
    return row, session


@pytest.mark.asyncio
async def test_saved_voice_is_what_the_agent_read_returns(stored):
    row, _session = stored
    saved = await AgentService().patch_agent(
        str(row.agent_id), {"default_tier": "medium", "voice_settings": _pick("voc_fifth")},
        tenant_id=str(row.tenant_id), expected_voice_revision=7,
    )
    # The PATCH answer and a fresh read (reload) agree on the choice.
    reread = AgentService._row_to_dict(row)
    for view in (saved, reread):
        assert view["voice_settings"]["voiceId"] == "voc_fifth"
        assert view["voiceRevision"] == 8
        assert "_voice_revision" not in view["voice_settings"]


@pytest.mark.asyncio
async def test_back_to_back_picks_each_persist_with_the_returned_revision(stored):
    row, session = stored
    service = AgentService()
    first = await service.patch_agent(
        str(row.agent_id), {"default_tier": "medium", "voice_settings": _pick("voc_second")},
        tenant_id=str(row.tenant_id), expected_voice_revision=7,
    )
    second = await service.patch_agent(
        str(row.agent_id), {"default_tier": "medium", "voice_settings": _pick("voc_third")},
        tenant_id=str(row.tenant_id), expected_voice_revision=first["voiceRevision"],
    )
    assert second["voice_settings"]["voiceId"] == "voc_third"
    assert row.voice_settings["voiceId"] == "voc_third"
    assert row.voice_settings["_voice_revision"] == 9
    assert session.commits == 2


@pytest.mark.asyncio
async def test_language_switch_keeps_the_saved_voice(stored):
    row, _session = stored
    await AgentService().patch_agent(
        str(row.agent_id), {"default_tier": "medium", "voice_settings": _pick("voc_fifth")},
        tenant_id=str(row.tenant_id), expected_voice_revision=7,
    )
    # The script Save sends only languages (no voice fields, no revision).
    after = await AgentService().patch_agent(
        str(row.agent_id), {"languages": ["hi-IN"]}, tenant_id=str(row.tenant_id),
    )
    assert after["languages"] == ["hi-IN"]
    assert after["voice_settings"]["voiceId"] == "voc_fifth"
    assert after["voiceRevision"] == 8


@pytest.mark.asyncio
async def test_voice_and_language_saved_together_both_persist(stored):
    row, _session = stored
    saved = await AgentService().patch_agent(
        str(row.agent_id),
        {"default_tier": "medium", "languages": ["hi-IN"], "voice_settings": _pick("voc_fifth")},
        tenant_id=str(row.tenant_id), expected_voice_revision=7,
    )
    reread = AgentService._row_to_dict(row)
    assert saved["languages"] == reread["languages"] == ["hi-IN"]
    assert reread["voice_settings"]["voiceId"] == "voc_fifth"


@pytest.mark.asyncio
async def test_saved_voice_survives_an_admin_profile_revision_bump(monkeypatch):
    """An admin label/price edit bumps the profile revision; the saved alias still resolves."""
    record = {
        "revision": 45,
        "profile": {
            "supportedLanguages": ["te-IN"],
            "stt": {"provider": "sarvam", "model": "saarika"},
            "llm": {"provider": "openai", "modelId": "gpt-4o-mini", "apiMode": "rest"},
            "engines": [{"id": "gnani", "models": [{
                "id": "timbre", "provider": "gnani", "model": "timbre", "apiMode": "rest",
                "voices": [{"id": "v1", "providerVoiceId": "spk", "languages": ["te-IN"]}],
            }]}],
        },
        "publicAliases": {
            "engines": {"gnani": "eng_a"},
            "models": {"gnani::timbre": "mod_a"},
            "voices": {"gnani::timbre::v1": "voc_first"},
        },
    }
    monkeypatch.setattr(voice_stack_profiles, "load_profile_records", AsyncMock(return_value={"medium": record}))
    monkeypatch.setattr(voice_stack_profiles, "_load_rates_without_fallback", AsyncMock(return_value={}))
    monkeypatch.setattr(voice_stack_profiles, "readiness_for_profile",
                        lambda *_a, **_k: {"ready": True, "enabled": True, "blockers": []})
    monkeypatch.setattr(voice_stack_profiles, "_native_tier_retail_rate", lambda *_a, **_k: None)
    monkeypatch.setattr(voice_stack_profiles, "_web_tier_retail_rate", lambda *_a, **_k: None)
    try:
        _stack, snapshot = await voice_stack_profiles.resolve_agent_selection(
            environment="development", tier="medium",
            voice_settings=_pick("voc_first", profile_revision=44), language="te-IN",
        )
    except voice_stack_profiles.VoiceProfileError as exc:  # pragma: no cover - the failure we guard
        pytest.fail(f"saved voice rejected after an admin edit: {exc.code}")
    assert snapshot["voiceId"] == "voc_first"
    assert snapshot["profileRevision"] == 45
