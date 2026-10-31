import json
from unittest.mock import AsyncMock

import pytest

from server.realtime.providers.gemini_voice import _gemini_tools
from server.realtime.testing import FakeRealtimeVoiceAdapter
from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop


def test_gemini_call_control_tool_does_not_promise_unimplemented_playback():
    tools = _gemini_tools()
    action = next(decl for tool in tools for decl in tool.function_declarations if decl.name == "call_action")
    assert "NOT played" in action.description
    assert "Answer ordinary questions directly" in action.description
    assert "before speaking a final response" not in action.description


@pytest.mark.asyncio
@pytest.mark.parametrize("already_spoke", [False, True])
async def test_continue_tool_recovers_silence_without_duplicating_an_audible_answer(already_spoke):
    adapter = FakeRealtimeVoiceAdapter()
    adapter.connected = True
    adapter.instructions = "LONG_SYSTEM_BRAIN_SENTINEL"
    wire = AsyncMock()
    core = PstnRealtimeVoiceLoop(session_id="test", call_id=None, on_agent_wire=wire, adapter=adapter, sample_rate=16000, stack_override={"language":"te-IN"})
    core._adapter = adapter
    core._live_model = "gemini-3.8-live"
    core._intro_noted = True
    await core._handle_event({"type":"response_created", "response_id":"answer"})
    if already_spoke:
        await core._handle_event({"type":"audio_delta", "response_id":"answer", "pcm":b"\x01\x00"*960})
    await core._handle_event({"type":"function_call", "name":"call_action", "call_id":"tool", "response_id":"answer", "arguments":json.dumps({"call_action":"CONTINUE", "response":"We repair phones.", "reason":"continue", "confidence":.99})})
    await core._handle_event({"type":"response_done", "response_id":"answer", "status":"completed"})
    # The fake records tool acknowledgements alongside spoken-response requests.
    spoken_tasks = [task for task in adapter.started_responses if not task.startswith("fn:")]
    if already_spoke:
        assert not spoken_tasks
    else:
        assert len(spoken_tasks) == 1
        task = spoken_tasks[0]
        assert "LONG_SYSTEM_BRAIN_SENTINEL" not in task
        assert "We repair phones" in task and "spoken audio" in task
        assert "English" in task
    await core.close()


@pytest.mark.asyncio
async def test_browser_greeting_waits_for_the_whole_playback_queue(monkeypatch):
    core = PstnRealtimeVoiceLoop(session_id="test", call_id=None, on_agent_wire=AsyncMock(), playback=type("Playback", (), {"queued_ms":lambda self:4200})(), channel="browser")
    sleep = AsyncMock()
    monkeypatch.setattr("server.services.pstn_realtime_voice_core.asyncio.sleep", sleep)
    await core._wait_greeting_tail()
    assert sleep.await_args.args[0] == pytest.approx(4.24)
    await core.close()
