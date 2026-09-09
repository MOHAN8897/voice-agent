"""PSTN acceptance regressions. No carrier calls or provider credentials required."""
from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.requests import Request

from server.services.pstn_voice_core import PstnVoiceLoop, PHASE_SPEAKING, PHASE_INTRO
from server.services.telnyx_client import TelnyxClient, TelnyxCallRegistry


@pytest.mark.asyncio
async def test_answer_contract_and_stable_command_id():
    client = TelnyxClient(cfg={"api_key": "test"})
    client._request = AsyncMock(return_value={"data": {"result": "ok"}})
    assert await client.answer("control") == {"result": "ok"}
    await client.answer("control")
    first, second = client._request.call_args_list
    assert first == second
    assert first.args == ("POST", "/calls/control/actions/answer")
    assert set(first.kwargs["json"]) == {"command_id"}


@pytest.mark.asyncio
@pytest.mark.parametrize("direction,expected", [("incoming", 1), ("outgoing", 0)])
async def test_initiated_answers_inbound_once_without_waiting(monkeypatch, direction, expected):
    from server.routes import telnyx
    registry = TelnyxCallRegistry()
    monkeypatch.setattr(registry, "_redis", lambda: None)
    monkeypatch.setattr(telnyx, "telnyx_call_registry", registry)
    monkeypatch.setattr(telnyx, "parse_verified_webhook_json", lambda **kw: json.loads(kw["payload"]))
    answer = AsyncMock()
    monkeypatch.setattr(telnyx, "_answer_inbound", answer)
    payload = {"data": {"event_type": "call.initiated", "payload": {"call_control_id": "cid", "direction": direction}}}
    async def receive():
        return {"type": "http.request", "body": json.dumps(payload).encode()}
    for _ in range(2):
        assert await telnyx.telnyx_webhook(Request({"type": "http", "method": "POST", "headers": []}, receive)) == {"ok": True}
    await asyncio.sleep(0)
    assert answer.await_count == expected


@pytest.mark.asyncio
async def test_inbound_bridge_resolves_agent_and_creates_call(monkeypatch):
    from server.services import telnyx_pstn_bridge as mod
    from server.brain.agent_service import agent_service
    from server.call.call_lifecycle_service import call_lifecycle_service
    from server.services.pstn_prewarm import take_prewarm_for_answer
    monkeypatch.setattr(agent_service, "resolve_default_agent_id", AsyncMock(return_value="default-agent"))
    start = AsyncMock(return_value={"call_id": "internal", "session_id": "isolated"})
    monkeypatch.setattr(call_lifecycle_service, "start", start)
    monkeypatch.setattr("server.services.pstn_prewarm.take_prewarm_for_answer", AsyncMock(return_value=None))
    monkeypatch.setattr("server.services.telnyx_client.telnyx_call_registry.get", lambda _: None)
    monkeypatch.setattr("server.services.telnyx_client.telnyx_call_registry.upsert", lambda *a: None)
    monkeypatch.setattr(mod.TelnyxPstnBridge, "_out_worker", AsyncMock())
    monkeypatch.setattr(mod.TelnyxPstnBridge, "_start_voice_loop", AsyncMock())
    bridge = mod.TelnyxPstnBridge(SimpleNamespace())
    try:
        await bridge._on_start({"start": {"call_control_id": "inbound-test", "media_format": {"encoding": "L16", "sample_rate": 16000}}})
        assert bridge.agent_id == "default-agent"
        assert bridge._voice.call_id == "internal"
        assert start.call_args.kwargs["direction"] == "inbound"
        assert start.call_args.kwargs["channel"] == "pstn"
    finally:
        mod.active_telnyx_bridges.pop("inbound-test", None)
        for task in (bridge._out_task, bridge._voice_loop_task):
            if task:
                await task


@pytest.mark.asyncio
async def test_remote_clear_failure_still_cancels_tts_and_llm(monkeypatch):
    from server.realtime.manager import realtime_text_manager
    cancel = AsyncMock()
    monkeypatch.setattr(realtime_text_manager, "cancel", cancel)
    voice = PstnVoiceLoop(session_id="clear-test", call_id="clear-test", on_agent_wire=AsyncMock())
    voice.current_generation_id = "g"
    session = SimpleNamespace(interrupt=AsyncMock())
    voice._active_tts_session = session
    voice.set_barge_handler(AsyncMock(side_effect=ConnectionError("carrier unavailable")))
    await voice._commit_barge("Wait")
    await asyncio.sleep(0)
    session.interrupt.assert_awaited_once()
    cancel.assert_awaited_once_with("clear-test")
    assert voice.emission_blocked()


@pytest.mark.parametrize("text", ["Wait", "No", "కాదు", "లేదు"])
@pytest.mark.parametrize("phase", [PHASE_SPEAKING, PHASE_INTRO])
def test_early_short_barge(text, phase):
    from server.services.transcript_gate import is_substantive_transcript
    voice = PstnVoiceLoop(session_id="early", call_id=None, on_agent_wire=AsyncMock())
    voice._set_phase(phase)
    voice._tts_active = True
    voice._tts_started_at = time.monotonic() - 0.20
    voice._partial_started_at = time.monotonic() - 0.13
    assert voice._should_commit_barge(text)
    assert is_substantive_transcript(text, after_barge=True)


def test_question_repetition_is_not_echo():
    from server.services.echo_guard import is_barge_echo, is_final_echo
    assert not is_barge_echo("Shamshabad?", "We have plots in Shamshabad.")
    assert not is_final_echo("Shamshabad?", "We have plots in Shamshabad.", in_echo_tail=True)
    assert is_barge_echo("We have plots in Shamshabad.", "We have plots in Shamshabad.")


@pytest.mark.asyncio
async def test_wire_rechecks_generation_after_send_lock():
    from server.services.telnyx_pstn_bridge import TelnyxPstnBridge, OutboundFrame
    ws = SimpleNamespace(send_text=AsyncMock())
    bridge = TelnyxPstnBridge(ws)
    await bridge._ws_send_lock.acquire()
    bridge._out_queue.put_nowait(OutboundFrame(payload=b"\0" * 640, codec="L16", turn_id="t", generation_id="g"))
    worker = asyncio.create_task(bridge._out_worker())
    await asyncio.sleep(0.02)
    bridge._invalid_generations.add("g")
    bridge._ws_send_lock.release()
    await asyncio.sleep(0.02)
    worker.cancel()
    await worker
    ws.send_text.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("event", [
    {"type": "session.created"},
    {"type": "error", "error": {"message": "invalid session field"}},
])
async def test_realtime_never_ready_on_creation_or_error(event):
    from server.realtime.providers.openai import OpenAIRealtimeTextAdapter
    adapter = OpenAIRealtimeTextAdapter(api_key="test")
    async def events():
        yield event
    adapter._conn = events()
    adapter._pump_task = asyncio.create_task(adapter._pump())
    with pytest.raises((ConnectionError, RuntimeError)):
        await adapter.wait_ready(timeout=0.2)
    await adapter._pump_task


@pytest.mark.asyncio
async def test_reconnect_restores_opening_and_conversation():
    from server.realtime.testing import FakeRealtimeAdapter
    from server.realtime.text_session import RealtimeTextSession
    adapter = FakeRealtimeAdapter()
    session = RealtimeTextSession("reconnect", adapter=adapter, model="test", instructions="brain")
    await session.note_spoken("Hello. [Opening already spoken aloud]")
    result = [part async for part in session.run_turn("I want a plot")]
    expected = list(session._history)
    await adapter.close()
    adapter.send_user_text = AsyncMock()
    adapter.send_assistant_text = AsyncMock()
    await session.start()
    assert result[-1]["done"]
    assert adapter.send_user_text.call_args.args[0] == "I want a plot"
    assert [c.args[0] for c in adapter.send_assistant_text.call_args_list] == [text for role, text in expected if role == "assistant"]
    await session.close()


def test_downsample_rejects_alias_and_preserves_packet_continuity():
    import audioop
    from server.tests.test_pstn_tts_resample import _tone
    from server.services.audio_transcode import StreamingPcmResampler
    low = StreamingPcmResampler(24000, 8000).feed(_tone(24000, ms=300, freq=1000))
    high = StreamingPcmResampler(24000, 8000).feed(_tone(24000, ms=300, freq=6000))
    assert audioop.rms(high[800:], 2) < audioop.rms(low[800:], 2) * 0.03
    pcm = _tone(24000, ms=300, freq=1000)
    stream = StreamingPcmResampler(24000, 8000)
    actual = b"".join(stream.feed(pcm[i:i+641]) for i in range(0, len(pcm), 641)) + stream.flush()
    assert actual == low


@pytest.mark.asyncio
@pytest.mark.parametrize("tts_age", [0.0, 0.1])
async def test_single_partial_confirms_without_second_stt_packet(tts_age):
    voice = PstnVoiceLoop(session_id="single", call_id=None, on_agent_wire=AsyncMock())
    voice._set_phase(PHASE_SPEAKING)
    voice._tts_active = True
    voice.current_generation_id = "g"
    voice._tts_started_at = time.monotonic() - tts_age
    commit = AsyncMock()
    voice._commit_barge = commit
    voice._schedule_interrupt_confirmation("Wait")
    await asyncio.wait_for(voice._barge_confirm_task, timeout=0.3)
    commit.assert_awaited_once_with("Wait")


@pytest.mark.asyncio
async def test_silent_greeting_is_not_recorded_as_spoken(monkeypatch):
    voice = PstnVoiceLoop(session_id="silent", call_id="silent", on_agent_wire=AsyncMock())
    monkeypatch.setattr(voice, "open_stt", AsyncMock())
    monkeypatch.setattr(voice, "speak", AsyncMock())
    note = AsyncMock()
    monkeypatch.setattr(voice, "_note_opening_spoken", note)
    await voice.start_call(greeting_text="Hello there.")
    note.assert_not_awaited()
    await voice.start_call(greeting_text="Hello there.")
    voice.speak.assert_awaited_once()


@pytest.mark.asyncio
async def test_tts_failure_retry_does_not_reenter_speak_lock(monkeypatch):
    from server.call.live_turn_orchestrator import live_turn_orchestrator
    from server.tests.test_pstn_critical_loop import FakeTtsSession
    class BrokenTts(FakeTtsSession):
        had_error = True
        audio_emitted = False
    async def reply(**kwargs):
        yield {"done": True, "text": "I can help you find a plot."}
    monkeypatch.setattr(live_turn_orchestrator, "handle_user_turn_stream", reply)
    monkeypatch.setattr("server.services.pstn_turn_tts.PstnTurnTtsSession", BrokenTts)
    voice = PstnVoiceLoop(session_id="tts-retry", call_id="tts-retry", on_agent_wire=AsyncMock())
    attempts = []
    async def retry(*args, **kwargs):
        assert not voice._speak_lock.locked()
        attempts.append(1)
    monkeypatch.setattr(voice, "speak", retry)
    await asyncio.wait_for(voice._run_turn("I need a plot"), timeout=0.5)
    assert attempts == [1]


@pytest.mark.asyncio
async def test_startup_failure_hangs_up_and_cleans_up():
    from server.services.telnyx_pstn_bridge import TelnyxPstnBridge
    ws = SimpleNamespace(close=AsyncMock())
    bridge = TelnyxPstnBridge(ws)
    bridge._voice = SimpleNamespace(start_call=AsyncMock(side_effect=RuntimeError("STT unavailable")))
    bridge._provider_hangup = AsyncMock(side_effect=RuntimeError("carrier unavailable"))
    bridge._cleanup = AsyncMock()
    await bridge._start_voice_loop()
    bridge._provider_hangup.assert_awaited_once()
    bridge._cleanup.assert_awaited_once_with("voice_start_failed")
    ws.close.assert_awaited_once_with(code=1011)


def test_latency_excludes_greeting_and_previous_turn():
    from server.services.pstn_media_flow import PstnMediaFlowStore
    events = [
        {"stage": stage, "timestamp": timestamp}
        for stage, timestamp in [
            ("tts_audio", 1.0), ("outbound_sent", 1.1),
            ("llm_started", 2.0), ("llm_first_token", 2.1),
            ("tts_audio", 2.2), ("outbound_sent", 2.3),
            ("llm_started", 4.0), ("llm_first_token", 4.3),
            ("tts_audio", 4.5), ("outbound_sent", 4.55),
        ]
    ]
    metrics = PstnMediaFlowStore._latencies(events)
    assert metrics["llm_first_token_ms"] == 300
    assert metrics["tts_first_audio_ms"] == 200
    assert metrics["telnyx_first_outbound_ms"] == 50
    assert PstnMediaFlowStore._latencies(events[:-2])["tts_first_audio_ms"] is None


@pytest.mark.asyncio
async def test_realtime_cancel_does_not_compete_with_active_event_reader():
    from server.realtime.text_session import RealtimeTextSession
    queue = asyncio.Queue()
    entered = asyncio.Event()
    async def events():
        entered.set()
        yield await queue.get()
    async def cancel():
        await queue.put({"type": "cancelled"})
    adapter = SimpleNamespace(events=events, cancel_response=cancel, discard_queued=lambda: None)
    session = RealtimeTextSession("cancel-reader", adapter=adapter, model="test", instructions="brain")
    session._state = "streaming"
    session._drain_until_idle = AsyncMock()
    async def collect():
        return [event async for event in session._collect_until_done()]
    task = asyncio.create_task(collect())
    await entered.wait()
    await session.cancel_response()
    assert await task == [{"type": "cancelled"}]
    session._drain_until_idle.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_from_startup_task_does_not_cancel_itself():
    from server.services.telnyx_pstn_bridge import TelnyxPstnBridge
    bridge = TelnyxPstnBridge(SimpleNamespace())
    bridge._voice_loop_task = asyncio.current_task()
    await bridge._cleanup("voice_start_failed")
    assert bridge._cleanup_done
