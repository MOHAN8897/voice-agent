"""Selected composed stacks use the same admitted stages on browser and PSTN."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from server.call import call_context
from server.call.call_ledger import call_ledger
from server.call.call_lifecycle_service import CallLifecycleService
from server.config.env import get_settings


@pytest.fixture
def composed_lifecycle(monkeypatch, tmp_path):
    from server.call.call_store import call_store
    from server.realtime.manager import realtime_text_manager
    from server.realtime.voice_manager import realtime_voice_manager
    from server.services import test_studio_config
    from server.services.saas import billing_wallet_service, campaign_script

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    call_ledger.reset_for_tests()
    call_context.clear_all()
    service = CallLifecycleService()
    agent = {"agent_id": "selected-agent", "tenant_id": "00000000-0000-4000-8000-000000000001", "languages": ["te-IN"]}
    monkeypatch.setattr(service, "_resolve_agent", AsyncMock(return_value=agent))
    monkeypatch.setattr(service, "_lock_compiled_brain", AsyncMock(return_value=("v1", "", "published")))
    monkeypatch.setattr(service, "_schedule_max_duration_watchdog", Mock())
    monkeypatch.setattr(test_studio_config, "saved_call_config", lambda _: {})
    monkeypatch.setattr(call_store, "insert", AsyncMock())
    monkeypatch.setattr(billing_wallet_service, "max_allowed_call_duration_sec", AsyncMock(return_value=900))
    monkeypatch.setattr(campaign_script, "campaign_call_script", AsyncMock(return_value=None))
    text_create = AsyncMock()
    voice_create = AsyncMock()
    monkeypatch.setattr(realtime_text_manager, "create", text_create)
    monkeypatch.setattr(realtime_voice_manager, "create", voice_create)
    yield service, text_create, voice_create
    call_context.clear_all()
    call_ledger.reset_for_tests()
    get_settings.cache_clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("tier", ["low", "medium"])
@pytest.mark.parametrize("channel", ["browser", "pstn"])
async def test_composed_lifecycle_preserves_selected_stages_on_each_channel(composed_lifecycle, monkeypatch, tier, channel):
    from server.providers.base import ResolvedStack, StageSelection

    service, text_create, voice_create = composed_lifecycle
    stack = ResolvedStack(
        combination_id="pinned-profile", tier=tier, mode="env", language="te-IN",
        stt=StageSelection("sarvam", "saaras:v3-realtime", {"mode": "realtime"}),
        llm=StageSelection("sarvam", "sarvam-30b", {"api_mode": "chat_completions_v2"}),
        tts=StageSelection("sarvam", "bulbul:v3", {"api_mode": "websocket", "speaker": "shubh"}),
    )
    snapshot = {"tier": tier, "profileRevision": 3, "voiceId": "public-voice-1", "retailRate": {
        "complete": True, "usdMicrosPerMin": 10000, "inrPaisePerMin": 95,
        "fxRateInr": 95.5, "version": 1,
    }}
    override = {**stack.to_safe_dict(), "pipeline": "composed_voice", "voice_flow": "composed_stages", "_voice_stack_snapshot": snapshot}
    monkeypatch.setattr(service, "_resolve_locked_stack", Mock(return_value=stack))

    started = await service.start(agent_id="selected-agent", tenant_id="00000000-0000-4000-8000-000000000001",
                                  session_id=f"selected-{tier}-{channel}", channel=channel, tier=tier,
                                  stack_override=override)

    ctx = call_context.get(started["call_id"])
    assert ctx.pipeline == "composed_voice"
    assert ctx.resolved_stack is stack
    assert ctx.channel == channel
    assert ctx.tier == tier
    assert call_ledger.read_meta(started["call_id"])["voice_stack_snapshot"] == snapshot
    text_create.assert_not_awaited()
    voice_create.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["snapshot", "approved_rate"])
async def test_browser_composed_lifecycle_fails_closed_without_admission_snapshot(composed_lifecycle, monkeypatch, missing):
    from server.utils.errors import AppError

    service, text_create, voice_create = composed_lifecycle
    stack = SimpleNamespace(tier="low", llm=SimpleNamespace(provider="sarvam", model="sarvam-30b", config={}))
    monkeypatch.setattr(service, "_resolve_locked_stack", Mock(return_value=stack))
    override = {"pipeline": "composed_voice", "voice_flow": "composed_stages"}
    if missing == "approved_rate":
        override["_voice_stack_snapshot"] = {"tier": "low", "retailRate": {"complete": False}}

    with pytest.raises(AppError):
        await service.start(agent_id="selected-agent", session_id=f"invalid-{missing}", channel="browser",
                            tier="low", stack_override=override)

    assert call_context.get_active_for_session(f"invalid-{missing}") is None
    text_create.assert_not_awaited()
    voice_create.assert_not_awaited()
