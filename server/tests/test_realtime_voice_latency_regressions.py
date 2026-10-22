"""Realtime latency regressions using delayed server events, without API calls."""
import asyncio
import base64
from unittest.mock import AsyncMock

import pytest

from server.realtime.providers.openai_voice import (
    OpenAIRealtimeVoiceAdapter,
    build_realtime_voice_session,
)
from server.realtime.testing import FakeRealtimeVoiceAdapter
from server.services.pstn_playback import TelnyxQueuePlayback
from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop


class Connection:
    def __init__(self):
        self.sent = []

    async def send(self, event):
        self.sent.append(event)


def adapter_with_connection():
    adapter = OpenAIRealtimeVoiceAdapter()
    adapter._conn = Connection()
    adapter.last_session = build_realtime_voice_session(model="gpt-realtime-2.1-mini", instructions="test")
    return adapter


def created(rid, metadata=None):
    return {"type": "response.created", "response": {"id": rid, "metadata": metadata or {}}}


def audio(rid):
    return {"type": "response.output_audio.delta", "response_id": rid,
            "delta": base64.b64encode(b"\0\0" * 960).decode()}


def done(rid):
    return {"type": "response.done", "response": {"id": rid, "status": "cancelled"}}


def test_low_latency_defaults_preserve_supported_format_and_overrides():
    session = build_realtime_voice_session(model="gpt-realtime-2.1-mini", instructions="test")
    assert session["audio"]["input"]["turn_detection"]["eagerness"] == "high"
    assert session["audio"]["input"]["turn_detection"]["interrupt_response"] is False
    assert session["audio"]["input"]["format"]["rate"] == 24000
    assert session["audio"]["output"]["format"]["rate"] == 24000
    server = build_realtime_voice_session(model="gpt-realtime-2.1-mini", instructions="test", turn_detection="server_vad", noise_reduction="off")
    assert server["audio"]["input"]["turn_detection"]["silence_duration_ms"] == 250
    assert server["audio"]["input"]["turn_detection"]["prefix_padding_ms"] == 300
    assert server["audio"]["input"]["noise_reduction"] is None
    explicit = build_realtime_voice_session(model="gpt-realtime-2.1-mini", instructions="test", vad_eagerness="medium")
    assert explicit["audio"]["input"]["turn_detection"]["eagerness"] == "medium"


@pytest.mark.asyncio
async def test_cancel_returns_without_ack_and_targets_only_requested_response():
    adapter = adapter_with_connection()
    adapter._normalize(created("new"))
    await asyncio.wait_for(adapter.cancel_response(response_id="old"), 0.1)
    assert adapter._conn.sent == [{"type": "response.cancel", "response_id": "old"}]
    assert adapter._normalize(audio("new")) is not None
    assert adapter._normalize(done("old")) is None
    assert not adapter._response_idle.is_set()
    await adapter.cancel_response(response_id="old")
    assert len(adapter._conn.sent) == 1


@pytest.mark.asyncio
async def test_injected_answer_survives_late_cancel_ack_before_response_created():
    adapter = adapter_with_connection()
    adapter._normalize(created("old"))
    await asyncio.wait_for(adapter.start_response(instructions="Answer now."), 0.1)
    assert [e["type"] for e in adapter._conn.sent] == [
        "session.update", "response.cancel", "response.create", "session.update",
    ]
    assert adapter._normalize(done("old")) is None
    assert not adapter._response_idle.is_set()
    metadata = adapter._conn.sent[2]["response"]["metadata"]
    assert adapter._normalize(created("answer", metadata))["response_id"] == "answer"
    assert adapter._normalize(audio("old")) is None
    assert adapter._normalize(audio("answer"))["type"] == "audio_delta"


@pytest.mark.asyncio
async def test_unobserved_vad_response_cannot_replace_injected_answer():
    adapter = adapter_with_connection()
    await asyncio.wait_for(adapter.start_response(instructions="Goodbye."), 0.1)
    assert adapter._conn.sent[1] == {"type": "response.cancel"}
    assert adapter._normalize(created("late-vad")) is None
    assert adapter._normalize(audio("late-vad")) is None
    assert adapter._normalize(done("late-vad")) is None
    metadata = adapter._conn.sent[2]["response"]["metadata"]
    assert adapter._normalize(created("farewell", metadata)) is not None
    assert adapter._normalize(audio("farewell")) is not None


@pytest.mark.asyncio
async def test_barge_before_created_rejects_pending_injected_response():
    adapter = adapter_with_connection()
    await adapter.start_response(instructions="Goodbye.")
    metadata = adapter._conn.sent[2]["response"]["metadata"]
    await adapter.cancel_response()
    assert adapter._normalize(created("cancelled-farewell", metadata)) is None
    assert adapter._normalize(audio("cancelled-farewell")) is None
    assert adapter._normalize(created("real-answer")) is not None
    assert adapter._normalize(done("cancelled-farewell")) is None
    assert adapter._normalize(audio("real-answer")) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("consumer", ["poll", "stream"])
async def test_cancel_discards_already_queued_audio_and_terminal_events(consumer):
    adapter = adapter_with_connection()
    for event in (created("old"), audio("old"), done("old")):
        adapter._events.put_nowait(adapter._normalize(event))
    await adapter.cancel_response(response_id="old")
    adapter._events.put_nowait({"type": "speech_started"})
    if consumer == "poll":
        received = await adapter.poll_event(timeout=0.1)
    else:
        stream = adapter.events()
        received = await asyncio.wait_for(anext(stream), 0.1)
        await stream.aclose()
    assert received == {"type": "speech_started"}


@pytest.mark.asyncio
async def test_idle_transport_unmutes_before_response_done_and_keeps_echo_gate():
    transport = {"queued": 1, "sending": False}
    playback = TelnyxQueuePlayback(queue_size=lambda: transport["queued"], drain=lambda: 0,
                                   sending=lambda: transport["sending"])
    adapter = FakeRealtimeVoiceAdapter()
    loop = PstnRealtimeVoiceLoop(session_id="latency", call_id=None, on_agent_wire=AsyncMock(),
                                 sample_rate=16000, playback=playback, adapter=adapter)
    loop._adapter = adapter
    loop._hold_inbound = False
    loop._tts_active = True
    quiet = b"\0\0" * 320
    await loop.feed_user_pcm16(quiet)
    assert not adapter.appended
    transport.update(queued=0, sending=True)
    await loop.feed_user_pcm16(quiet)
    assert not adapter.appended
    transport["sending"] = False
    await loop.feed_user_pcm16(quiet)
    assert adapter.appended
    await loop._handle_event({"type": "speech_started"})
    assert loop._caller_speaking
    assert not loop._should_drop_user_final("John")
    assert adapter.cancelled == 0


@pytest.mark.asyncio
async def test_first_audio_preserves_caller_buffer_and_duplicate_created_is_idempotent():
    adapter = FakeRealtimeVoiceAdapter()
    wire = AsyncMock()
    loop = PstnRealtimeVoiceLoop(session_id="latency", call_id=None, on_agent_wire=wire,
                                 sample_rate=16000, adapter=adapter)
    loop._adapter = adapter
    await loop._handle_event({"type": "response_created", "response_id": "answer"})
    await loop._handle_event({"type": "audio_delta", "response_id": "answer", "pcm": b"\0\0" * 960})
    generation = loop.current_generation_id
    await loop._handle_event({"type": "response_created", "response_id": "answer"})
    assert loop.current_generation_id == generation
    assert loop._response_had_audio
    assert adapter.cleared_input == 0
    assert adapter.cancelled == 0
    assert wire.await_count > 0


@pytest.mark.asyncio
async def test_rejected_greeting_late_events_do_not_leak_into_real_answer():
    adapter = FakeRealtimeVoiceAdapter()
    loop = PstnRealtimeVoiceLoop(session_id="latency", call_id=None, on_agent_wire=AsyncMock(), adapter=adapter)
    loop._adapter = adapter
    loop._deferred_greeting_armed = True
    await loop._handle_event({"type": "response_created", "response_id": "greeting"})
    assert adapter.cancelled == 1
    loop._deferred_greeting_armed = False
    await loop._handle_event({"type": "response_created", "response_id": "answer"})
    await loop._handle_event({"type": "assistant_transcript", "response_id": "answer", "text": "The price is ten."})
    await loop._handle_event({"type": "assistant_transcript", "response_id": "greeting", "text": "Hello again."})
    await loop._handle_event({"type": "cancelled", "response_id": "greeting"})
    assert loop._assistant_text == "The price is ten."
    assert loop._response_open


def test_final_assistant_transcript_uses_realtime_event():
    adapter = adapter_with_connection()
    adapter._normalize(created("answer"))
    result = adapter._normalize({"type": "response.output_audio_transcript.done", "response_id": "answer", "transcript": "The price is ten."})
    assert result == {"type": "assistant_transcript", "response_id": "answer", "text": "The price is ten."}
    assert adapter._conn.sent == []


def test_vad_latency_uses_latest_turn_and_actual_transport_send():
    from server.services.pstn_media_flow import PstnMediaFlowStore

    events = [{"stage": stage, "timestamp": timestamp} for stage, timestamp in [
        ("vad_speech_stopped", 1.0), ("llm_started", 1.1), ("outbound_sent", 1.3),
        ("vad_speech_stopped", 3.0), ("llm_started", 3.1),
        ("tts_audio", 3.2), ("outbound_sent", 3.4),
    ]]
    assert PstnMediaFlowStore._latencies(events)["vad_stop_to_first_audio_ms"] == 400
    assert PstnMediaFlowStore._latencies(events[:-1])["vad_stop_to_first_audio_ms"] is None
    events.append({"stage": "llm_started", "timestamp": 5.0})
    events.append({"stage": "outbound_sent", "timestamp": 5.1})
    assert PstnMediaFlowStore._latencies(events)["vad_stop_to_first_audio_ms"] is None


def test_voice_tool_description_prefers_speech_without_changing_text_tool():
    from server.call.call_controller import CALL_ACTION_TOOL

    session = build_realtime_voice_session(model="gpt-realtime-2.1-mini", instructions="test")
    voice_tool = next(t for t in session["tools"] if t["name"] == "call_action")
    assert "speak a short farewell, then report END_CALL" in voice_tool["description"]
    assert "before speaking" in CALL_ACTION_TOOL["description"]
    assert voice_tool["parameters"] == CALL_ACTION_TOOL["parameters"]
