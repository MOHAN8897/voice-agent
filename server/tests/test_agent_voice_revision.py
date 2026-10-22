from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from server.brain.agent_service import AgentService, AgentVoiceRevisionConflict
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
        self.statement = None
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, statement):
        self.statement = statement
        return _Result(self.row)

    async def commit(self):
        self.commits += 1

    async def refresh(self, _row):
        return None


def _agent(*, revision: int = 2, tier: str = "medium") -> Agent:
    return Agent(
        agent_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        name="Voice revision test",
        status="active",
        active_compiled_brain_version=None,
        default_tier=tier,
        languages=["te-IN"],
        memory_schema="compact_v1",
        environment="development",
        voice_settings={"stackSelectionVersion": 1, "_voice_revision": revision},
        recording_disclosure_enabled=False,
        recording_disclosure_text=None,
    )


def _selection() -> dict:
    return {
        "stackSelectionVersion": 1,
        "profileRevision": 5,
        "engineId": "engine-a",
        "modelId": "model-a",
        "voiceId": "voice-a",
    }


@pytest.mark.asyncio
async def test_voice_patch_uses_row_lock_and_increments_server_owned_revision(monkeypatch):
    row = _agent()
    session = _Session(row)
    monkeypatch.setattr("server.brain.agent_service.get_session_factory", lambda: lambda: session)

    async def validate(*_args, **_kwargs):
        return None

    monkeypatch.setattr(voice_stack_profiles, "validate_agent_voice_selection_async", validate)
    result = await AgentService().patch_agent(
        str(row.agent_id),
        {"default_tier": "medium", "voice_settings": _selection()},
        tenant_id=str(row.tenant_id),
        expected_voice_revision=2,
    )

    assert session.statement._for_update_arg is not None
    assert session.commits == 1
    assert row.voice_settings["_voice_revision"] == 3
    assert result["voice_revision"] == 3
    assert "_voice_revision" not in result["voice_settings"]


@pytest.mark.asyncio
async def test_versioned_voice_patch_requires_matching_revision(monkeypatch):
    row = _agent(revision=2)
    session = _Session(row)
    monkeypatch.setattr("server.brain.agent_service.get_session_factory", lambda: lambda: session)

    with pytest.raises(AgentVoiceRevisionConflict) as missing:
        await AgentService().patch_agent(
            str(row.agent_id),
            {"voice_settings": _selection()},
            tenant_id=str(row.tenant_id),
        )
    assert missing.value.status_code == 428
    assert session.commits == 0

    with pytest.raises(AgentVoiceRevisionConflict) as stale:
        await AgentService().patch_agent(
            str(row.agent_id),
            {"voice_settings": _selection()},
            tenant_id=str(row.tenant_id),
            expected_voice_revision=1,
        )
    assert stale.value.details == {"currentRevision": 2}
    assert session.commits == 0


@pytest.mark.asyncio
async def test_versioned_voice_patch_refuses_premium_and_requires_durable_store(monkeypatch):
    row = _agent(revision=2)
    session = _Session(row)
    monkeypatch.setattr("server.brain.agent_service.get_session_factory", lambda: lambda: session)
    with pytest.raises(AgentVoiceRevisionConflict) as premium:
        await AgentService().patch_agent(
            str(row.agent_id),
            {"default_tier": "premium", "voice_settings": _selection()},
            tenant_id=str(row.tenant_id),
            expected_voice_revision=2,
        )
    assert premium.value.code == "premium_composed_settings_forbidden"
    assert session.commits == 0

    monkeypatch.setattr("server.brain.agent_service.get_session_factory", lambda: None)
    with pytest.raises(AgentVoiceRevisionConflict) as unavailable:
        await AgentService().patch_agent(
            str(row.agent_id),
            {"voice_settings": _selection()},
            tenant_id=str(row.tenant_id),
            expected_voice_revision=2,
        )
    assert unavailable.value.status_code == 503
    assert unavailable.value.code == "durable_store_unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("voice_patch", [{"stackSelectionVersion": 1, "realtimeVoice": "puck"}, None])
async def test_switch_to_premium_persists_validated_voice_without_old_composed_aliases(monkeypatch, voice_patch):
    row = _agent()
    row.voice_settings.update(_selection())
    session = _Session(row)
    monkeypatch.setattr("server.brain.agent_service.get_session_factory", lambda: lambda: session)
    # Keep the actual validator: mocking it hid Premium being rejected by
    # the composed-only resolver with invalid_composed_tier on every save.
    patch = {"default_tier": "premium"}
    if voice_patch is not None:
        patch["voice_settings"] = voice_patch
    await AgentService().patch_agent(str(row.agent_id), patch, tenant_id=str(row.tenant_id), expected_voice_revision=2)
    assert row.default_tier == "premium"
    assert row.voice_settings["_voice_revision"] == 3
    assert not {"voiceId", "engineId", "modelId", "profileRevision"} & row.voice_settings.keys()
    if voice_patch:
        assert row.voice_settings["realtimeVoice"] == "puck"


@pytest.mark.asyncio
@pytest.mark.parametrize("voice_id,language,error_code", [
    ("shubh", "te-IN", "voice_selection_invalid"),
    ("unlisted-voice", "te-IN", "voice_selection_invalid"),
])
async def test_premium_rejects_wrong_live_voice_without_misclassifying_revision(monkeypatch, voice_id, language, error_code):
    row = _agent()
    session = _Session(row)
    monkeypatch.setattr("server.brain.agent_service.get_session_factory", lambda: lambda: session)
    with pytest.raises(AgentVoiceRevisionConflict) as invalid:
        await AgentService().patch_agent(
            str(row.agent_id), {"default_tier": "premium", "languages": [language],
                                "voice_settings": {"stackSelectionVersion": 1, "realtimeVoice": voice_id}},
            tenant_id=str(row.tenant_id), expected_voice_revision=2,
        )
    assert invalid.value.code == error_code
    assert session.commits == 0


@pytest.mark.asyncio
async def test_premium_rejects_unsupported_language_live_voice(monkeypatch):
    row = _agent()
    session = _Session(row)
    monkeypatch.setattr("server.brain.agent_service.get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(
        "server.services.saas.voice_catalog.phone_voice_catalog",
        lambda: [{"id": "live-en", "provider": "gemini", "languageCode": "en-US"}],
    )
    with pytest.raises(AgentVoiceRevisionConflict) as invalid:
        await AgentService().patch_agent(
            str(row.agent_id),
            {"default_tier": "premium", "languages": ["hi-IN"],
             "voice_settings": {"stackSelectionVersion": 1, "realtimeVoice": "live-en"}},
            tenant_id=str(row.tenant_id), expected_voice_revision=2,
        )
    assert invalid.value.code == "unsupported_language"
    assert session.commits == 0
