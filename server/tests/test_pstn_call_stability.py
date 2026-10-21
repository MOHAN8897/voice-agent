import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from server.services.pstn_playback import EstimatedPlaybackTracker
from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop


def test_playback_estimate_does_not_accumulate_rounding_over_two_minutes(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("server.services.pstn_playback.time.monotonic", lambda: clock[0])
    tracker = EstimatedPlaybackTracker(post_send_hold_ms=150)
    for _ in range(6000):
        tracker.note_sent_frames(1)
        clock[0] += .011
        tracker.is_active()
        clock[0] += .009
        tracker.queued_ms()
    clock[0] += .2
    assert not tracker.is_active()
    assert tracker.queued_ms() == 0


@pytest.fixture
def voice(monkeypatch):
    loop = PstnRealtimeVoiceLoop(session_id="stability", call_id=None, on_agent_wire=AsyncMock(),
        stack_override={"language": "te-IN", "llm": {"provider": "gemini", "model": "gemini-3.8-live"}})
    loop._adapter = SimpleNamespace(cancel_response=AsyncMock(), clear_output_audio=AsyncMock(), close=AsyncMock())
    loop._live_model = "gemini-3.8-live"
    loop.current_generation_id = "answer-one"
    loop._greeting_protected = lambda: False
    return loop


async def test_local_and_provider_speech_start_only_cancel_generation_once(voice):
    voice._on_barge = AsyncMock()
    await voice._commit_local_barge()
    await voice._commit_local_barge()
    voice._adapter.cancel_response.assert_awaited_once()
    voice._on_barge.assert_awaited_once()
    voice.current_generation_id = "answer-two"
    await voice._commit_local_barge()
    assert voice._adapter.cancel_response.await_count == 2


async def test_carrier_disconnect_closes_live_transcriber_before_session_destroy(voice, monkeypatch):
    stt = SimpleNamespace(close=AsyncMock(), billed_audio_sec=83.5)
    voice._caller_stt = stt
    voice._finalize_live_transcript_usage = AsyncMock()
    monkeypatch.setattr("server.realtime.voice_manager.realtime_voice_manager.destroy", AsyncMock())
    await voice.close()
    stt.close.assert_awaited_once()
    voice._finalize_live_transcript_usage.assert_awaited_once_with(sidecar_sec=83.5)
    assert voice._caller_stt is None
    await voice.close()
    stt.close.assert_awaited_once()


async def test_external_transcript_error_cannot_end_conversation(voice, monkeypatch):
    voice._runtime_end = AsyncMock()
    await voice._on_live_stt_state("failed", "")
    voice._runtime_end.assert_not_awaited()


async def test_completed_call_closes_transcription_task_without_cancelling_it(voice, monkeypatch):
    from server.services.live_caller_transcription import LiveCallerTranscriber
    from server.tests.test_live_caller_transcription import Socket, eventually
    states = []
    stream = LiveCallerTranscriber(model="gpt-4o-mini-transcribe", language="te-IN", input_rate=8000,
        on_final=AsyncMock(), on_state=AsyncMock(side_effect=lambda status, text: states.append(status)))
    socket = Socket("openai")
    monkeypatch.setattr(stream, "_connect", lambda: socket)
    stream.start()
    await eventually(lambda: "streaming" in states)
    voice._caller_stt = stream
    voice._finalize_live_transcript_usage = AsyncMock()
    monkeypatch.setattr("server.realtime.voice_manager.realtime_voice_manager.destroy", AsyncMock())
    for _ in range(10):
        stream.feed_pcm16(b"\x01\x00" * 160)
    await eventually(lambda: socket.audio_bytes > 0)
    await voice.close()
    assert stream._task.done()
    assert states[-1] == "complete"
    assert not stream._failure


async def test_primary_call_keeps_answering_past_two_minutes(voice, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("server.services.pstn_realtime_voice_core.time.monotonic", lambda: clock[0])
    voice._started_at = clock[0]
    voice._intro_noted = True
    voice._runtime_end = AsyncMock()
    for turn in range(20):
        clock[0] += 8
        await voice._handle_event({"type": "user_transcript", "final": True,
            "text": "ఇంకా project వివరాలు చెప్పండి"})
        rid = f"answer-{turn}"
        await voice._handle_event({"type": "response_created", "response_id": rid})
        await voice._handle_event({"type": "assistant_transcript_delta", "response_id": rid,
            "delta": "Project వివరాలు office లో అందుబాటులో ఉన్నాయండి."})
        await voice._handle_event({"type": "audio_delta", "response_id": rid, "pcm": b"\x01\x00" * 960})
        await voice._handle_event({"type": "response_done", "response_id": rid})
        await voice._check_runtime(clock[0])
        assert not voice._pending_end_call
        assert not voice._hangup_started
    assert voice.on_agent_wire.await_count >= 20
    voice._runtime_end.assert_not_awaited()


async def test_gemini_language_tool_asks_for_clarification_without_blaming_caller(voice, monkeypatch):
    from server.call.call_context import clear_all, put
    from server.prompts.agent_voice_rules import UNCLEAR_FALLBACK, pack_get
    voice.call_id = "stability-language"
    voice._adapter.submit_function_output = AsyncMock()
    voice._last_user_final_text = "Aapke paas aur bhi kuch business hai kya?"
    put(SimpleNamespace(call_id=voice.call_id, session_id="s", status="active",
        language_mismatch_handled=False))
    try:
        await voice._handle_language_callback_tool({"call_id": "tool-one", "arguments": {
            "action": "remind", "caller_language": "hi-IN", "communication_blocked": True}})
        result = json.loads(voice._adapter.submit_function_output.call_args.kwargs["output"])
        assert pack_get(UNCLEAR_FALLBACK, "te-IN") in result["instruction"]
        assert "దయచేసి తెలుగులో చెప్పండి" not in result["instruction"]
    finally:
        clear_all()


def test_gemini_instructions_do_not_trust_asr_language_guess():
    from server.realtime.gemini_audio_session import build_gemini_audio_session_instructions
    instructions = build_gemini_audio_session_instructions("Business: property enquiries", language="te-IN")
    assert "ASR text may mistranscribe" in instructions
    assert "ask one neutral clarification" in instructions


@pytest.mark.parametrize("reason,expected", [("client_disconnected", "ws_disconnect"),
    ("provider_stop", "pstn_hangup"), ("media_error", "provider_failure"),
    ("call_hangup_notified", "pstn_hangup")])
async def test_media_disconnect_retains_actual_cause(monkeypatch, reason, expected):
    from server.services.vobiz_pstn_bridge import VobizPstnBridge
    bridge = VobizPstnBridge(Mock(close=AsyncMock()))
    bridge.call_id = "isolated-call"
    bridge._voice = Mock(close=AsyncMock())
    meta = {}
    monkeypatch.setattr("server.call.billing_timing.mark_call_disconnected", Mock())
    monkeypatch.setattr("server.call.call_ledger.call_ledger.read_meta", lambda _: meta)
    monkeypatch.setattr("server.call.call_ledger.call_ledger.write_meta", lambda _, value: meta.update(value))
    end = AsyncMock()
    monkeypatch.setattr("server.call.call_lifecycle_service.call_lifecycle_service.end", end)
    monkeypatch.setattr("server.services.vobiz_pstn_bridge.vobiz_call_registry.upsert", Mock())
    await bridge._cleanup(reason)
    assert meta["media_disconnect"]["reason"] == reason
    end.assert_awaited_once_with(bridge.call_id, reason=expected)
    bridge._voice.close.assert_awaited_once()


async def test_diagnostic_storage_failure_cannot_skip_runtime_disconnect(voice, monkeypatch):
    voice.call_id = "isolated-runtime"
    monkeypatch.setattr("server.call.call_ledger.call_ledger.read_meta", Mock(side_effect=OSError()))
    voice._fast_disconnect_after_farewell = AsyncMock()
    await voice._runtime_end("provider_failure")
    voice._fast_disconnect_after_farewell.assert_awaited_once()


async def test_close_drains_final_turn_before_bridge_can_seal_ledger(voice, monkeypatch):
    async def finish_turn():
        await asyncio.sleep(.01)
        completed.append("last assistant turn")
    completed = []
    voice._run_post_turn(finish_turn())
    monkeypatch.setattr("server.realtime.voice_manager.realtime_voice_manager.destroy", AsyncMock())
    await voice.close()
    assert completed == ["last assistant turn"]
    assert not voice._post_turn_tasks
