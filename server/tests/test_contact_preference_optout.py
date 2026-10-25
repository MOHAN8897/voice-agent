"""Ending a call and opting out of future contact are separate outcomes."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from server.call.call_context import CallContext, clear_all, put
from server.call.contact_preference import record_contact_preference
from server.providers.base import ResolvedStack, StageSelection
from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

TENANT = "tenant-1"
CALL = "call-cp-1"
CALLER = "+15550100001"


def live_ctx(call_id: str = CALL, *, direction: str = "inbound") -> CallContext:
    ctx = CallContext(
        call_id=call_id,
        tenant_id=TENANT,
        agent_id="agent-1",
        session_id="session-1",
        channel="pstn",
        direction=direction,
        environment="test",
        tier="medium",
        resolved_stack=ResolvedStack(
            combination_id="combo",
            tier="medium",
            mode="backend",
            stt=StageSelection("sarvam", "saaras:v3", {}),
            llm=StageSelection("gemini", "gemini-3.8-flash", {"api_mode": "streaming_rest"}),
            tts=StageSelection("sarvam", "bulbul:v3", {}),
            language="en-IN",
        ),
        compiled_brain_version="v1",
        compiled_brain_text="",
        started_at=datetime.now(timezone.utc),
        storage_path="",
    )
    put(ctx)
    return ctx


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    from server.config.env import get_settings

    monkeypatch.setenv("ENABLE_CALL_ARCHIVE", "false")
    get_settings.cache_clear()
    clear_all()
    yield
    clear_all()
    get_settings.cache_clear()


@pytest.fixture
def dnc(monkeypatch):
    from server.services.saas import dnc_service

    spy = AsyncMock(return_value=True)
    monkeypatch.setattr(dnc_service, "handle_call_opt_out", spy)
    return spy


@pytest.mark.asyncio
async def test_ending_this_call_is_recorded_but_never_enrolls_dnc(dnc):
    ctx = live_ctx()

    await record_contact_preference(CALL, "end_call")

    assert ctx.contact_preference == "end_call"
    dnc.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_opt_out_enrolls_before_the_line_closes(dnc):
    ctx = live_ctx()

    await record_contact_preference(CALL, "do_not_call")

    assert ctx.contact_preference == "do_not_call"
    dnc.assert_awaited_once_with(CALL, disposition="do_not_call")


@pytest.mark.asyncio
async def test_unknown_preference_is_normalized(dnc):
    ctx = live_ctx()

    assert await record_contact_preference(CALL, "maybe later") == "none"
    assert ctx.contact_preference == "none"
    dnc.assert_not_awaited()


@pytest.mark.asyncio
async def test_native_gate_keeps_goodbye_and_opt_out_as_separate_fields(dnc):
    live_ctx()
    loop = PstnRealtimeVoiceLoop(session_id="session-1", call_id=CALL, on_agent_wire=AsyncMock())
    loop._user_partial = "Don't call me again."

    accepted = await loop._gate_end_call_payload(
        {"should_end": True, "reason": "goodbye", "farewell": "Goodbye."}
    )

    assert accepted is not None
    assert accepted["reason"] == "firm_refusal"
    assert accepted["contact_preference"] == "do_not_call"
    dnc.assert_awaited_once_with(CALL, disposition="do_not_call")


@pytest.mark.asyncio
async def test_native_gate_end_call_request_does_not_enroll(dnc):
    ctx = live_ctx()
    loop = PstnRealtimeVoiceLoop(session_id="session-1", call_id=CALL, on_agent_wire=AsyncMock())
    loop._user_partial = "End the call please."

    accepted = await loop._gate_end_call_payload(
        {"should_end": True, "reason": "goodbye", "farewell": "Goodbye."}
    )

    assert accepted is not None
    assert accepted["contact_preference"] == "end_call"
    assert ctx.contact_preference == "end_call"
    dnc.assert_not_awaited()


@pytest.mark.asyncio
async def test_composed_turn_keeps_end_call_out_of_dnc(dnc):
    from server.call.live_turn_orchestrator import live_turn_orchestrator

    ctx = live_ctx()
    chunks = await _composed_turn(
        live_turn_orchestrator,
        transcript="End the call please.",
        end_call={
            "decision": "close",
            "reason": "goodbye",
            "evidence": "End the call please.",
            "remaining_request": "",
            "contact_preference": "end_call",
            "farewell": "Goodbye.",
        },
    )

    done = next(chunk for chunk in chunks if chunk.get("done"))
    assert done["end_call"]["reason"] == "goodbye"
    assert done["end_call"]["contact_preference"] == "end_call"
    assert ctx.contact_preference == "end_call"
    dnc.assert_not_awaited()


@pytest.mark.asyncio
async def test_composed_turn_enrolls_explicit_opt_out(dnc):
    from server.call.live_turn_orchestrator import live_turn_orchestrator

    ctx = live_ctx()
    chunks = await _composed_turn(
        live_turn_orchestrator,
        transcript="Don't call me again.",
        end_call={
            "decision": "close",
            "reason": "goodbye",
            "evidence": "Don't call me again.",
            "remaining_request": "",
            "contact_preference": "do_not_call",
            "farewell": "Goodbye.",
        },
    )

    done = next(chunk for chunk in chunks if chunk.get("done"))
    assert done["end_call"]["reason"] == "firm_refusal"
    assert done["end_call"]["contact_preference"] == "do_not_call"
    assert ctx.contact_preference == "do_not_call"
    dnc.assert_awaited_once_with(CALL, disposition="do_not_call")


async def _composed_turn(orchestrator, *, transcript: str, end_call: dict):
    from unittest.mock import patch

    async def fake_stream(**_kwargs):
        yield {
            "done": True,
            "text": str(end_call.get("farewell") or ""),
            "end_call": end_call,
            "usage": {},
            "finish_reason": "stop",
        }

    async def no_memory(_call_id, **_kwargs):
        return None, None

    with (
        patch.object(orchestrator, "_stream_llm", fake_stream),
        patch.object(orchestrator, "_memory_blocks", no_memory),
    ):
        return [
            chunk
            async for chunk in orchestrator.handle_user_turn_stream(
                transcript=transcript,
                language_code="en-IN",
                session_id="session-1",
                call_id=CALL,
            )
        ]


@pytest.mark.asyncio
async def test_lifecycle_end_reads_the_recorded_preference(monkeypatch):
    ctx = live_ctx()
    ctx.contact_preference = "do_not_call"
    from server.call.call_ledger import call_ledger
    from server.services.saas import dnc_service

    await call_ledger.init(CALL, {"caller_id": CALLER, "direction": "inbound"})
    enroll = AsyncMock(return_value=True)
    monkeypatch.setattr(dnc_service, "auto_enroll_dnc_opt_out", enroll)
    try:
        enrolled = await dnc_service.handle_call_opt_out(CALL)
    finally:
        call_ledger.reset_for_tests()

    assert enrolled is True
    enroll.assert_awaited_once_with(TENANT, CALLER)


@pytest.mark.asyncio
async def test_preference_is_persisted_before_a_meta_file_exists(monkeypatch, tmp_path):
    from server.call.call_ledger import call_ledger
    from server.config.env import get_settings
    from server.services.saas import dnc_service

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    live_ctx()
    monkeypatch.setattr(dnc_service, "handle_call_opt_out", AsyncMock(return_value=True))

    await record_contact_preference(CALL, "do_not_call")

    assert call_ledger.read_meta(CALL)["contact_preference"] == "do_not_call"


@pytest.mark.asyncio
async def test_ledger_copy_enrolls_after_the_live_context_is_gone(monkeypatch, tmp_path):
    from server.call.call_ledger import call_ledger
    from server.call.call_store import call_store
    from server.config.env import get_settings
    from server.services.saas import dnc_service

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    real_opt_out = dnc_service.handle_call_opt_out
    monkeypatch.setattr(dnc_service, "handle_call_opt_out", AsyncMock(return_value=True))
    await call_ledger.init(CALL, {"caller_id": CALLER, "direction": "inbound"})
    live_ctx()
    await record_contact_preference(CALL, "do_not_call")
    clear_all()

    monkeypatch.setattr(dnc_service, "handle_call_opt_out", real_opt_out)
    monkeypatch.setattr(call_store, "get", AsyncMock(return_value={"tenant_id": TENANT}))
    enroll = AsyncMock(return_value=True)
    monkeypatch.setattr(dnc_service, "auto_enroll_dnc_opt_out", enroll)

    assert await dnc_service.handle_call_opt_out(CALL) is True
    enroll.assert_awaited_once_with(TENANT, CALLER)


def test_native_tools_expose_contact_preference():
    from server.realtime.end_call_tool import parse_end_call_tool
    from server.realtime.hangup_tools import REQUEST_END_CALL_TOOL, parse_request_end_call_tool
    from server.realtime.models import END_CALL_TOOL

    for tool in (END_CALL_TOOL, REQUEST_END_CALL_TOOL):
        assert "contact_preference" in tool["parameters"]["properties"]

    parsed = parse_end_call_tool(
        {"should_end": True, "reason": "goodbye", "farewell": "Bye",
         "contact_preference": "do_not_call"}
    )
    assert parsed["contact_preference"] == "do_not_call"

    requested = parse_request_end_call_tool(
        {"reason": "caller_goodbye", "contact_preference": "do_not_call"}
    )
    assert requested["contact_preference"] == "do_not_call"
