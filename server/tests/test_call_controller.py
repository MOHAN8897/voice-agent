"""Regression coverage for pickup latency, consent, lifecycle and ambiguous dials."""
import asyncio
import json
import struct
from unittest.mock import AsyncMock

import httpx
import pytest

from server.call.call_controller import AgentAction, CallAction, CallLifecycleController, CallState
from server.call.end_call_validate import caller_requested_hangup
from server.realtime.testing import FakeRealtimeVoiceAdapter
from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop


def action(kind="END_CALL", reason="firm_refusal", confidence=0.98):
    return {"call_action": kind, "reason": reason, "confidence": confidence,
            "response": "Understood. Thank you for your time. Goodbye."}


@pytest.mark.parametrize("confidence", [float("nan"), float("inf"), -1, 1.1, "no"])
def test_action_rejects_invalid_confidence(confidence):
    assert AgentAction.parse(action(confidence=confidence)) is None


def test_controller_handles_semantic_actions_without_keyword_matching():
    controller = CallLifecycleController()
    continuing = AgentAction(CallAction.CONTINUE, "What else would you like to know?", "continue", 0.99)
    assert controller.request(continuing) is None
    assert controller.state == CallState.ACTIVE
    ending = AgentAction.parse(action())
    assert controller.request(ending) is None
    assert controller.state == CallState.ENDING
    assert controller.request(ending) == "call_not_active"
    controller.resume()
    assert controller.state == CallState.ACTIVE
    controller.end()
    controller.resume()
    assert controller.state == CallState.ENDED


def test_uncertain_and_inflight_speech_do_not_end():
    controller = CallLifecycleController()
    assert controller.request(AgentAction.parse(action(confidence=0.6))) == "uncertain_intent"
    assert controller.request(AgentAction.parse(action()), caller_speaking=True) == "caller_still_talking"
    assert controller.state == CallState.ACTIVE


@pytest.mark.parametrize("kind,reason", [("TRANSFER", "transfer_requested"), ("VOICEMAIL", "voicemail")])
def test_unconfigured_actions_never_disconnect(kind, reason):
    controller = CallLifecycleController()
    assert controller.request(AgentAction.parse(action(kind, reason))) == "action_unavailable"
    assert controller.state == CallState.ACTIVE


def make_loop():
    adapter = FakeRealtimeVoiceAdapter()
    adapter.connected = True
    loop = PstnRealtimeVoiceLoop(session_id="test", call_id=None, on_agent_wire=AsyncMock(),
                                 adapter=adapter, sample_rate=16000,
                                 stack_override={"pipeline": "realtime_voice", "language": "en-IN",
                                                 "direction": "outbound"})
    loop._adapter = adapter
    loop._on_remote_hangup = AsyncMock()
    return loop, adapter


@pytest.mark.asyncio
async def test_cached_greeting_uses_local_endpoint_without_waiting_for_remote_vad():
    loop, adapter = make_loop()
    frames = [b"\x01" * 640]
    await loop.start_call(greeting_wire_frames=frames, greeting_text="Hi, do you have a moment?")
    loud = struct.pack("<320h", *([1200] * 320))
    for _ in range(15):
        await loop.feed_user_pcm16(loud)
    loop.on_agent_wire.assert_not_awaited()
    assert adapter.appended == []
    await loop._handle_event({"type": "speech_stopped"})
    await asyncio.sleep(0.35)
    if loop._deferred_greeting_task:
        await asyncio.wait_for(loop._deferred_greeting_task, 0.5)
    loop.on_agent_wire.assert_awaited_once_with(frames[0])
    # Leftover VAD is cancelled after the cached greeting, not used to start it.
    assert adapter.cancelled >= 1
    assert adapter.auto_response_states == [False, True]
    # A delayed provider speech_stopped must not play the greeting twice.
    await loop._handle_event({"type": "speech_stopped"})
    assert loop.on_agent_wire.await_count == 1
    await loop.close()


@pytest.mark.asyncio
async def test_background_noise_does_not_start_greeting():
    loop, _ = make_loop()
    await loop.start_call(greeting_wire_frames=[bytes(640)], greeting_text="Hello.")
    for _ in range(20):
        await loop.feed_user_pcm16(struct.pack("<320h", *([20] * 320)))
    assert loop._deferred_greeting_task is None
    loop.on_agent_wire.assert_not_awaited()
    await loop.close()


@pytest.mark.asyncio
async def test_latest_record_callback_withdrawal_is_latched_across_later_noise():
    loop, _ = make_loop()
    loop._callback_request_text = "Please can you call me again?"
    assert caller_requested_hangup("No, you don't have to call me.")
    await loop._handle_event({"type": "user_transcript", "final": True,
                              "text": "No, you don't have to call me."})
    await loop._handle_event({"type": "user_transcript", "final": True,
                              "text": "Modern the same God."})
    assert loop._callback_request_text == ""
    assert loop.controller.callback_cancelled
    assert loop._sync_callback_close_state().phase == "idle"
    await loop._maybe_resume_callback_close()
    assert loop._pending_followup_instruction is None
    await loop.close()


@pytest.mark.asyncio
async def test_structured_refusal_overrides_callback_and_waits_for_goodbye(monkeypatch):
    monkeypatch.setattr("server.call.natural_hangup.HANGUP_TRAIL_SILENCE_SEC", 0)
    loop, adapter = make_loop()
    loop._callback_request_text = "Call me tomorrow"
    loop._user_partial = "This service isn't something I want to pursue."
    await loop._handle_event({"type": "response_created", "response_id": "close"})
    await loop._handle_event({"type": "function_call", "name": "call_action", "call_id": "fn",
                              "response_id": "close", "arguments": json.dumps(action())})
    await loop._handle_event({"type": "response_done", "response_id": "close"})
    loop._on_remote_hangup.assert_not_awaited()
    assert loop.controller.state == CallState.ENDING
    assert loop._callback_request_text == ""
    assert "call you" not in adapter.started_responses[-1]
    await loop._handle_event({"type": "response_created", "response_id": "goodbye"})
    await loop._handle_event({"type": "audio_delta", "response_id": "goodbye", "pcm": bytes(1920)})
    await loop._handle_event({"type": "response_done", "response_id": "goodbye"})
    loop._on_remote_hangup.assert_awaited_once()
    assert loop.controller.state == CallState.ENDED
    await loop.close()


@pytest.mark.asyncio
async def test_stale_tool_cannot_end_new_turn():
    loop, _ = make_loop()
    loop._openai_response_id = "new"
    await loop._handle_event({"type": "function_call", "response_id": "old", "name": "call_action",
                              "arguments": json.dumps(action())})
    assert loop._pending_end_call is None
    assert loop.controller.state == CallState.ACTIVE
    await loop.close()


@pytest.mark.asyncio
async def test_runtime_max_duration_is_independent_of_model():
    loop, _ = make_loop()
    loop._started_at = 1
    await loop._check_runtime(901)
    await loop._check_runtime(902)
    loop._on_remote_hangup.assert_awaited_once()
    assert loop.controller.state == CallState.ENDED
    await loop.close()


@pytest.mark.asyncio
async def test_silence_prompts_once_then_soft_ends():
    loop, adapter = make_loop()
    loop._last_activity_at = 0
    await loop._check_runtime(5)
    assert "still there" in adapter.started_responses[-1]
    loop._followup_inflight = False
    loop._response_open = False
    await loop._check_runtime(15)
    assert loop._pending_end_call["reason"] == "silence_timeout"
    loop._on_remote_hangup.assert_not_awaited()
    await loop.close()


@pytest.mark.asyncio
async def test_ambiguous_dial_timeout_does_not_place_second_call(monkeypatch):
    from server.services.telnyx_client import TelnyxApiError, TelnyxClient
    request = AsyncMock(side_effect=httpx.ReadTimeout("response lost after dial accepted"))
    monkeypatch.setattr(httpx.AsyncClient, "request", request)
    client = TelnyxClient(cfg={"api_key": "test", "connection_id": "test", "phone_number": "+15551234567"})
    with pytest.raises(TelnyxApiError):
        await client.create_outbound_call(to_e164="+15557654321")
    assert request.await_count == 1


@pytest.mark.asyncio
async def test_goodbye_flushes_tail_before_waiting_for_playback(monkeypatch):
    monkeypatch.setattr("server.call.natural_hangup.HANGUP_TRAIL_SILENCE_SEC", 0)
    loop, _ = make_loop()
    events = []
    playing = False

    async def drain():
        nonlocal playing
        await asyncio.sleep(0.03)
        playing = False
        events.append("played")

    async def flush():
        nonlocal playing
        playing = True
        events.append("flushed")
        asyncio.create_task(drain())

    async def hangup():
        events.append("hangup")

    loop._flush_agent_pcm_to_wire = flush
    loop.is_agent_audio_active = lambda: playing
    loop._on_remote_hangup = hangup
    loop._pending_end_call = {"reason": "goodbye"}
    loop._response_had_audio = True
    await loop._finish_hangup()
    assert events == ["flushed", "played", "hangup"]
    await loop.close()


@pytest.mark.asyncio
async def test_user_resumes_before_disconnect():
    loop, _ = make_loop()
    loop.controller.state = CallState.ENDING
    loop._pending_end_call = {"reason": "goal_complete"}
    await loop._handle_event({"type": "speech_started"})
    assert loop.controller.state == CallState.ACTIVE
    assert loop._pending_end_call is None
    loop._on_remote_hangup.assert_not_awaited()
    await loop.close()


@pytest.mark.asyncio
async def test_provider_eof_hangs_up_once():
    loop, adapter = make_loop()

    async def eof():
        for event in []:
            yield event

    adapter.events = eof
    await loop._event_pump()
    await loop._runtime_end("provider_failure")
    loop._on_remote_hangup.assert_awaited_once()
    await loop.close()


@pytest.mark.asyncio
async def test_injected_response_waits_for_vad_disable_and_cancellation_ack():
    from server.realtime.providers.openai_voice import OpenAIRealtimeVoiceAdapter, build_realtime_voice_session

    queue = asyncio.Queue()
    sent = []
    adapter = OpenAIRealtimeVoiceAdapter()
    adapter.last_session = build_realtime_voice_session(model="gpt-realtime-2.1-mini", instructions="test")

    class Conn:
        def __aiter__(self):
            return self

        async def __anext__(self):
            return await queue.get()

        async def send(self, event):
            sent.append(event["type"])
            if event["type"] == "session.update":
                if not event["session"]["audio"]["input"]["turn_detection"]["create_response"]:
                    # A VAD response starts just before the disable is applied.
                    await queue.put({"type": "response.created", "response": {"id": "vad"}})
                await queue.put({"type": "session.updated", "session": event["session"]})
            elif event["type"] == "response.cancel":
                await queue.put({"type": "response.done", "response": {"id": "vad", "status": "cancelled"}})

        async def close(self):
            pass

    adapter._conn = Conn()
    adapter._pump_task = asyncio.create_task(adapter._pump())
    await asyncio.wait_for(adapter.start_response(instructions="Goodbye."), 1)
    assert sent == ["session.update", "response.cancel", "response.create", "session.update"]
    await adapter.close()


def test_old_response_done_does_not_mark_new_response_idle():
    from server.realtime.providers.openai_voice import OpenAIRealtimeVoiceAdapter
    adapter = OpenAIRealtimeVoiceAdapter()
    adapter._normalize({"type": "response.created", "response": {"id": "new"}})
    assert adapter._normalize({"type": "response.done", "response": {"id": "old"}}) is None
    assert not adapter._response_idle.is_set()
    assert adapter._active_response_id == "new"


@pytest.mark.parametrize("text", ["Okay.", "Thanks.", "Okay, one more thing about the price?"])
@pytest.mark.asyncio
async def test_acknowledgement_or_followup_does_not_end(text):
    loop, _ = make_loop()
    await loop._handle_event({"type": "user_transcript", "final": True, "text": text})
    await loop._handle_event({"type": "response_created"})
    await loop._handle_event({"type": "assistant_transcript", "text": "How can I help?"})
    await loop._handle_event({"type": "response_done"})
    assert loop._pending_end_call is None
    loop._on_remote_hangup.assert_not_awaited()
    await loop.close()
