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


@pytest.fixture
def failing_cartesia(monkeypatch):
    """Reproduce the production handshake failure while exercising real TTS framing."""
    import base64
    from unittest.mock import Mock
    from server.services import tts_config, sarvam_ws
    from server.services.dev_fallback_store import dev_fallback_store
    from server.services.dev_secrets_store import dev_secrets_store

    monkeypatch.setattr(dev_fallback_store, "get_chains", lambda: {"tts": ["sarvam", "cartesia"]})
    monkeypatch.setattr(dev_secrets_store, "effective", lambda name, default=None: True)
    monkeypatch.setattr(dev_secrets_store, "effective_secret", lambda name: "test-key")
    monkeypatch.setattr(tts_config, "merge_pstn_tts_config", lambda *a, **k: {
        "provider": "cartesia", "model": "sonic-3.5", "speaker": "cartesia-voice",
        "output_audio_codec": "linear16", "speech_sample_rate": "16000",
    })

    class AudioSocket:
        def __init__(self):
            self.messages = asyncio.Queue()
            self.sent = []
            self.closed = False

        async def send(self, raw):
            obj = json.loads(raw)
            self.sent.append(obj)
            if obj["type"] == "flush":
                await self.messages.put(json.dumps({"type": "audio", "data": {
                    "audio": base64.b64encode(b"\x10\x00" * 640).decode(),
                }}))
                await self.messages.put(json.dumps({"type": "done"}))

        def __aiter__(self):
            return self

        async def __anext__(self):
            return await self.messages.get()

        async def close(self):
            self.closed = True

    failed = SimpleNamespace(
        __aenter__=AsyncMock(side_effect=RuntimeError("server rejected WebSocket connection: HTTP 402")),
        __aexit__=AsyncMock(),
    )
    primary = Mock(return_value=failed)
    sockets = []
    def connect(**kwargs):
        assert kwargs["model"].startswith("bulbul:")
        sock = AudioSocket()
        sockets.append(sock)
        return SimpleNamespace(__aenter__=AsyncMock(return_value=sock), __aexit__=AsyncMock())

    monkeypatch.setattr("server.routes.ws._connect_tts_upstream", primary)
    monkeypatch.setattr(sarvam_ws, "connect_tts_ws", connect)
    return primary, failed, sockets


@pytest.mark.asyncio
@pytest.mark.parametrize("rate,codec,frame_size", [(16000, "linear16", 640), (8000, "mulaw", 160)])
async def test_cartesia_402_greeting_recovers_and_next_turn_uses_fallback(failing_cartesia, monkeypatch, rate, codec, frame_size):
    from server.services.telnyx_pstn_bridge import TelnyxPstnBridge

    primary, failed, sockets = failing_cartesia
    output = AsyncMock()
    voice = PstnVoiceLoop(session_id="fallback", call_id="fallback", on_agent_wire=output,
                          sample_rate=rate, tts_output_codec=codec)
    monkeypatch.setattr(voice, "open_stt", AsyncMock())
    monkeypatch.setattr(voice, "_note_opening_spoken", AsyncMock())
    bridge = TelnyxPstnBridge(SimpleNamespace(close=AsyncMock()))
    bridge.call_id = "fallback"
    bridge._voice = voice
    bridge._prewarm_bundle = SimpleNamespace(
        greeting_wire_frames=[], greeting_text="Hello, how can I help?", greeting_usage=None,
    )
    bridge._provider_hangup = AsyncMock()
    bridge._cleanup = AsyncMock()

    await bridge._start_voice_loop()
    assert output.await_count > 0
    assert all(len(call.args[0]) == frame_size for call in output.await_args_list)
    bridge._provider_hangup.assert_not_awaited()
    bridge._cleanup.assert_not_awaited()
    assert voice._tts_fallback_provider == "sarvam"
    await voice.speak("How may I help you today?")
    await voice.close()
    primary.assert_called_once()
    failed.__aexit__.assert_awaited_once()
    # Greeting + follow-up speak reuse one warm Sarvam socket per call.
    assert len(sockets) == 1
    for sock in sockets:
        config = sock.sent[0]["data"]
        assert config["output_audio_codec"] == "linear16"
        assert config["speech_sample_rate"] == str(rate)
        assert config["speaker"] != "cartesia-voice"
        assert sock.closed


@pytest.mark.asyncio
async def test_pstn_does_not_use_unconfigured_fallback(failing_cartesia, monkeypatch):
    from server.services.dev_fallback_store import dev_fallback_store
    from server.services.pstn_prewarm import _synthesize_greeting_frames

    monkeypatch.setattr(dev_fallback_store, "get_chains", lambda: {"tts": []})
    with pytest.raises(RuntimeError, match="HTTP 402"):
        await _synthesize_greeting_frames(greeting="Hello", session_id="fallback", pseudo_call_id="prewarm",
                                          sample_rate=16000, tts_output_codec="linear16", language="te-IN")
    assert not failing_cartesia[2]


@pytest.mark.asyncio
async def test_prewarm_greeting_recovers_from_cartesia_402(failing_cartesia):
    from server.services.pstn_prewarm import _synthesize_greeting_frames

    frames = await _synthesize_greeting_frames(greeting="Hello", session_id="fallback", pseudo_call_id="prewarm",
                                               sample_rate=16000, tts_output_codec="linear16", language="te-IN")
    assert frames and all(len(frame) == 640 for frame in frames)


def test_fallback_config_ignores_locked_cartesia_stack(monkeypatch):
    from server.services import tts_config
    from unittest.mock import Mock

    stack = Mock(side_effect=AssertionError("must not resolve the failed locked stack"))
    monkeypatch.setattr(tts_config, "_stack_for_session", stack)
    monkeypatch.setattr(tts_config.runtime_settings, "get", lambda sid: {"ttsModel": "sonic-3.5", "ttsSpeaker": "cartesia-voice"})
    cfg = tts_config.resolve_tts_config("locked", provider_override="sarvam", language_code="te-IN")
    assert cfg["provider"] == "sarvam"
    assert cfg["model"].startswith("bulbul:")
    assert cfg["speaker"] != "cartesia-voice"


@pytest.mark.parametrize("enabled,key", [(False, "test-key"), (True, "")])
def test_fallback_requires_enabled_provider_and_credentials(monkeypatch, enabled, key):
    from server.config.env import get_settings
    from server.services.dev_fallback_store import dev_fallback_store
    from server.services.dev_secrets_store import dev_secrets_store
    from server.services.pstn_turn_tts import _sarvam_fallback_config

    monkeypatch.setattr(dev_fallback_store, "get_chains", lambda: {"tts": ["sarvam"]})
    monkeypatch.setattr(dev_secrets_store, "effective", lambda *a: enabled)
    monkeypatch.setattr(dev_secrets_store, "effective_secret", lambda *a: key)
    monkeypatch.setattr(get_settings(), "sarvam_api_key", "")
    assert _sarvam_fallback_config("te-IN", "rtp_l16") is None


@pytest.mark.asyncio
async def test_disabled_greeting_does_not_play_prewarm_audio(monkeypatch):
    voice = PstnVoiceLoop(session_id="skip", call_id="skip", on_agent_wire=AsyncMock())
    monkeypatch.setattr(voice, "open_stt", AsyncMock())
    monkeypatch.setattr(voice, "_play_buffered_greeting", AsyncMock())
    await voice.start_call(play_greeting=False, greeting_text="Hello", greeting_wire_frames=[b"\x00" * 640])
    voice._play_buffered_greeting.assert_not_awaited()
    assert voice._wire_frames_out == 0


@pytest.mark.asyncio
async def test_prewarm_rejects_empty_audio(monkeypatch):
    from server.services.pstn_prewarm import _synthesize_greeting_frames

    fake = SimpleNamespace(open=AsyncMock(), send_text=AsyncMock(), finish=AsyncMock(),
                           close=AsyncMock(), had_error=False)
    monkeypatch.setattr("server.services.pstn_turn_tts.PstnTurnTtsSession", lambda voice: fake)
    with pytest.raises(RuntimeError, match="no usable audio"):
        await _synthesize_greeting_frames(greeting="Hello", session_id="silent", pseudo_call_id="prewarm",
                                          sample_rate=16000, tts_output_codec="linear16", language="te-IN")
    fake.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_prewarm_greeting_uses_the_same_locked_stack_as_call_turns(monkeypatch):
    from server.services.pstn_prewarm import _synthesize_greeting_frames

    locked_stack = SimpleNamespace(tts=SimpleNamespace(provider="sarvam", model="bulbul:v3"))
    fake = SimpleNamespace(
        open=AsyncMock(),
        send_text=AsyncMock(),
        finish=AsyncMock(),
        close=AsyncMock(),
        had_error=False,
    )

    def factory(voice):
        voice.frames.append(b"\x00" * 640)
        return fake

    monkeypatch.setattr("server.services.pstn_turn_tts.PstnTurnTtsSession", factory)
    frames = await _synthesize_greeting_frames(
        greeting="Hello",
        session_id="locked-greeting",
        pseudo_call_id="prewarm",
        sample_rate=16000,
        tts_output_codec="linear16",
        language="en-IN",
        resolved_stack=locked_stack,
    )

    assert frames
    fake.open.assert_awaited_once_with(language_code="en-IN", resolved_stack=locked_stack)


@pytest.mark.asyncio
@pytest.mark.parametrize("buffered", [False, True])
async def test_intro_waits_for_last_rtp_send_before_releasing_caller(monkeypatch, buffered):
    from server.services.pstn_playback import TelnyxQueuePlayback
    from server.services.telnyx_pstn_bridge import TelnyxPstnBridge

    last_frame_in_flight = asyncio.Event()
    release_last_frame = asyncio.Event()
    sent = []

    async def send(raw):
        if len(sent) == 1:
            last_frame_in_flight.set()
            await release_last_frame.wait()
        sent.append(json.loads(raw))

    bridge = TelnyxPstnBridge(SimpleNamespace(send_text=send, close=AsyncMock()))
    playback = TelnyxQueuePlayback(queue_size=bridge._out_queue.qsize, drain=lambda: 0,
                                   sending=lambda: bridge._out_sending)
    voice = PstnVoiceLoop(session_id="intro-drain", call_id=None,
                          on_agent_wire=bridge._send_agent_wire, sample_rate=16000,
                          tts_output_codec="linear16", playback=playback)
    bridge._voice = voice
    bridge._playback = playback
    frames = [b"\x10\x00" * 320, b"\x20\x00" * 320]

    async def cold_greeting(text):
        voice.current_generation_id = "cold-greeting"
        playback.set_current_generation(voice.current_generation_id)
        for frame in frames:
            await voice._emit_agent_wire(frame)

    monkeypatch.setattr(voice, "speak", cold_greeting)
    monkeypatch.setattr(voice, "open_stt", AsyncMock())
    note = AsyncMock()
    monkeypatch.setattr(voice, "_note_opening_spoken", note)
    from unittest.mock import Mock
    launch = Mock()
    monkeypatch.setattr(voice, "_launch_turn", launch)
    worker = asyncio.create_task(bridge._out_worker())
    startup = asyncio.create_task(voice.start_call(greeting_text="Hello, how may I help?",
                                                   greeting_wire_frames=frames if buffered else None))
    try:
        await asyncio.wait_for(last_frame_in_flight.wait(), timeout=1)
        assert bridge._out_queue.empty()  # Empty queue is not proof of completed playback.
        voice._queue_user_transcript("I would like the price details", intro=True)
        await asyncio.sleep(0.05)
        assert voice._intro_phase
        assert not startup.done()
        launch.assert_not_called()
        note.assert_not_awaited()
        release_last_frame.set()
        await asyncio.wait_for(startup, timeout=1)
        assert len(sent) == 2
        assert bridge._media_frames_out == 2
        assert not voice._intro_phase
        launch.assert_called_once_with("I would like the price details")
        note.assert_awaited_once()
    finally:
        startup.cancel()
        worker.cancel()
        await asyncio.gather(startup, worker, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("finish", ["hangup", "barge"])
async def test_intro_playback_wait_does_not_reopen_ended_or_interrupted_call(monkeypatch, finish):
    from server.services.pstn_voice_core import PHASE_ENDED, PHASE_INTERRUPTING
    from unittest.mock import Mock

    voice = PstnVoiceLoop(session_id="intro-stop", call_id=None, on_agent_wire=AsyncMock(),
                          is_agent_audio_active=lambda: True)
    monkeypatch.setattr(voice, "open_stt", AsyncMock())
    monkeypatch.setattr(voice, "_warm_tts_connection", AsyncMock())
    monkeypatch.setattr(voice, "speak", AsyncMock())
    launch = Mock()
    monkeypatch.setattr(voice, "_launch_turn", launch)
    startup = asyncio.create_task(voice.start_call(greeting_text="Hello"))
    try:
        await asyncio.sleep(0.03)
        assert voice._intro_phase
        voice._intro_queue.append("caller speech")
        phase = PHASE_ENDED if finish == "hangup" else PHASE_INTERRUPTING
        if finish == "hangup":
            voice._closed = True
        voice._set_phase(phase)
        await asyncio.wait_for(startup, timeout=0.5)
        assert voice._phase == phase
        launch.assert_not_called()
    finally:
        startup.cancel()
        await asyncio.gather(startup, return_exceptions=True)


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
        assert start.call_args.kwargs["config_session_id"] == "test-studio:default-agent"
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

        async def synthesize_to_frames(self, text: str) -> list[bytes]:
            await self.send_text(text)
            await self.finish()
            return []
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
