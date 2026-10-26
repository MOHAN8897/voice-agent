"""Executable regressions for the PSTN VAD/barge-in v2.2 audit."""
from __future__ import annotations

import base64
import json
import struct
import time
from itertools import pairwise
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from server.services import pstn_voice_core as core


@pytest.fixture
def clock(monkeypatch):
    value = [100.0]
    monkeypatch.setattr(core, "time", SimpleNamespace(
        monotonic=lambda: value[0], perf_counter=time.perf_counter,
    ))
    return value


@pytest.fixture
def voice(clock):
    loop = core.PstnVoiceLoop(session_id="audit", call_id=None, on_agent_wire=AsyncMock())
    loop.current_generation_id = "audit-generation"
    loop._set_phase(core.PHASE_SPEAKING)
    loop._tts_active = True
    loop._tts_started_at = 99.0
    loop._last_vad_voice_at = 100.0
    loop._barge_runtime = {}
    return loop


NODS = [
    "yes", "Yeah yeah", "ok ok sure", "no problem", "Actually that's fine",
    "అవునండి", "సరే", "avunu", "हाँ जी", "ठीक है", "theek na", "hai na",
    "ஆம்", "ಹೌದು", "അതെ", "हो", "হ্যাঁ", "હા", "ਹਾਂ",
]
HALTS = ["Stop!", "Wait", "ఆగండి", "रुको", "நில்லுங்கள்", "ನಿಲ್ಲಿಸಿ", "നിൽക്കൂ",
         "थांबा", "থামুন", "ઊભા રહો", "ਰੁਕੋ", "stop చెప్పండి"]
NEGATIONS = ["No", "కాదు", "नहीं", "இல்லை", "ಬೇಡ", "വേണ്ട", "नको", "না", "નથી", "ਨਹੀਂ"]
QUESTIONS = ["ఎంత?", "ఎందుకు?", "ఎప్పుడు?", "कितना?", "कब?", "அப்படியா", "ಹೌದಾ"]


@pytest.mark.parametrize("text", NODS)
def test_nods_never_barge_or_cancel_thinking(voice, clock, text):
    assert voice._should_commit_barge(text) is False
    clock[0] += 0.4
    voice._last_vad_voice_at = clock[0]
    assert voice._should_commit_barge(text) is False
    voice._tts_active = False
    voice._set_phase(core.PHASE_THINKING)
    voice._turn_busy = True
    assert voice._should_think_cancel(text) is False
    assert voice._should_think_continue_final(text) is False


@pytest.mark.parametrize("text", HALTS)
def test_strong_halts_bypass_onset_energy_and_hold(voice, text):
    voice._tts_started_at = 99.99
    voice._last_vad_voice_at = 0.0
    assert voice._should_commit_barge(text) is True
    voice._tts_active = False
    voice._set_phase(core.PHASE_THINKING)
    assert voice._should_think_cancel(text) is True


@pytest.mark.parametrize("text", NEGATIONS)
def test_negations_require_recent_voice_and_150ms_hold(voice, clock, text):
    voice._last_vad_voice_at = 0.0
    assert voice._should_commit_barge(text) is False
    voice._last_vad_voice_at = clock[0]
    assert voice._should_commit_barge(text) is False
    clock[0] += 0.149
    assert voice._should_commit_barge(text) is False
    clock[0] += 0.002
    assert voice._should_commit_barge(text) is True


@pytest.mark.parametrize("text", QUESTIONS)
def test_short_indic_questions_use_300ms_hold(voice, clock, text):
    assert voice._should_commit_barge(text) is False
    clock[0] += 0.299
    assert voice._should_commit_barge(text) is False
    clock[0] += 0.002
    assert voice._should_commit_barge(text) is True


def test_general_barge_requires_voice_and_350ms_playout_grace(voice, clock):
    voice._tts_started_at = 99.9
    voice._last_vad_voice_at = 0.0
    assert voice._should_commit_barge("I need more information") is False
    voice._last_vad_voice_at = clock[0]
    assert voice._should_commit_barge("I need more information") is False
    clock[0] += 0.301
    assert voice._should_commit_barge("I need more information") is True


def test_thinking_final_cannot_bypass_voice_and_negation_hold(voice, clock):
    voice._tts_active = False
    voice._turn_busy = True
    voice._set_phase(core.PHASE_THINKING)
    voice._last_vad_voice_at = 0.0
    assert voice._should_think_continue_final("No") is False
    assert voice._should_think_continue_final("background conversation continues") is False
    voice._last_vad_voice_at = clock[0]
    assert voice._should_think_continue_final("No") is False
    clock[0] += 0.151
    assert voice._should_think_continue_final("No") is True


@pytest.mark.asyncio
async def test_pcm_continuity_and_voice_latch_survive_quiet_frames(voice, clock):
    voice._stt = SimpleNamespace(send=AsyncMock())
    loud = struct.pack("<160h", *([1600] * 160))
    quiet = b"\0\0" * 160
    frames = [loud, loud] + [quiet] * 26
    for frame in frames:
        await voice.feed_user_pcm16(frame)
        clock[0] += 0.02
    assert not voice._aec_barge_open
    forwarded = [base64.b64decode(json.loads(call.args[0])["audio"])
                 for call in voice._stt.send.await_args_list]
    assert forwarded == frames
    assert voice._should_commit_barge("I need more information") is False
    clock[0] += 0.301
    assert voice._should_commit_barge("I need more information") is True


@pytest.mark.asyncio
async def test_thinking_collects_energy_without_ducking_on_raw_rms(voice, clock):
    voice._stt = SimpleNamespace(send=AsyncMock())
    voice._tts_active = False
    voice._set_phase(core.PHASE_THINKING)
    voice._last_vad_voice_at = 0.0
    for _ in range(2):
        await voice.feed_user_pcm16(struct.pack("<160h", *([1600] * 160)))
    assert voice._last_vad_voice_at == clock[0]
    assert not voice._tts_ducked


class SttEvents:
    def __init__(self, events):
        self.events = events

    async def __aiter__(self):
        for event in self.events:
            yield json.dumps(event)


@pytest.mark.asyncio
@pytest.mark.parametrize("text,partial_kept", [
    ("your booking is confirmed", False), ("your booking is confirmed at 10 AM", False),
    ("10 AM", True), ("4 3 2 1", True),
    ("one two three four", True), ("Stop please", True), ("No", True),
])
async def test_guarded_partial_echo_never_skips_final(voice, monkeypatch, text, partial_kept):
    voice._tts_heard_text = "Your booking is confirmed at 10 AM with code 4 3 2 1 one two three four"
    voice._turn_busy = True
    voice._stt = SttEvents([{"event": "transcript.partial", "text": text},
                           {"event": "transcript.final", "text": text}])
    schedule = Mock()
    queue = Mock()
    monkeypatch.setattr(voice, "_schedule_interrupt_confirmation", schedule)
    monkeypatch.setattr(voice, "_should_commit_barge", lambda _: False)
    monkeypatch.setattr(voice, "_queue_user_transcript", queue)
    await voice._stt_reader()
    assert schedule.call_count == 1 + int(partial_kept)
    queue.assert_called_once_with(text)


@pytest.mark.asyncio
@pytest.mark.parametrize("assistant,answer,kept", [
    ("I'll confirm your booking details.", "Avunu", False),
    ("That is correct.", "हाँ", False),
    ("Would you like a visit? Your booking is confirmed.", "yes", False),
    ("Shall I proceed?", "yes", True), ("సరేనా", "అవును", True),
    ("बताइए", "हाँ", True), ("தொடரலாமா", "ஆம்", True),
    ("ಮುಂದುವರಿಯಲೇ", "ಹೌದು", True), ("തുടരണമോ", "അതെ", True),
    ("पुढे जाऊ का", "हो", True), ("বলুন", "হ্যাঁ", True),
    ("આગળ વધું", "હા", True), ("ਅੱਗੇ ਵਧਾਂ", "ਹਾਂ", True),
])
async def test_turn_completion_keeps_answers_and_purges_statement_nods(
    monkeypatch, assistant, answer, kept,
):
    loop = core.PstnVoiceLoop(session_id="audit-turn", call_id="audit-turn", on_agent_wire=AsyncMock())
    tts = SimpleNamespace(prepare_for_turn=AsyncMock(), finish=AsyncMock(), has_sent_text=True)

    async def stream(**_kwargs):
        yield {"done": True, "text": assistant}

    async def send(_session, text):
        loop._last_tts_text = text
        loop._pending_transcript = answer
        return _session

    monkeypatch.setattr("server.call.live_turn_orchestrator.live_turn_orchestrator.handle_user_turn_stream", stream)
    monkeypatch.setattr(loop, "_get_call_tts_session", lambda: tts)
    monkeypatch.setattr(loop, "_send_tts_text", send)
    monkeypatch.setattr(loop, "_release_tts_turn", AsyncMock())
    launch = Mock()
    monkeypatch.setattr(loop, "_launch_turn", launch)
    await loop._run_turn("Tell me the details")
    assert launch.call_args_list == ([((answer,), {})] if kept else [])
    assert not loop._tts_ducked
    assert loop._tts_current_factor == loop._tts_target_factor == 1.0


@pytest.mark.parametrize("language", ["en-IN", "en-US", "te-IN", "hi-IN", "ta-IN",
                                     "kn-IN", "ml-IN", "mr-IN", "bn-IN", "gu-IN", "pa-IN"])
def test_backchannel_pools_are_native(language):
    from server.services.pstn_backchannel import BACKCHANNEL_PHRASES, pick_backchannel_phrase

    assert language in BACKCHANNEL_PHRASES
    phrase = pick_backchannel_phrase(language)
    assert phrase in BACKCHANNEL_PHRASES[language]
    if not language.startswith("en"):
        assert any(ord(char) > 127 for char in phrase)


@pytest.mark.parametrize("text", ["na", "ना", "no problem", "actually that's fine"])
def test_weak_negations_have_no_arbitrary_tail(text):
    from server.services.pstn_lexicon import _WEAK_NEGATION_RE

    assert _WEAK_NEGATION_RE.fullmatch(text) is None


@pytest.mark.parametrize("text", ["చెప్పండి", "சொல்லுங்க", "ಹೇಳಿ", "പറയൂ", "सांगा", "বলুন", "કહો", "ਦੱਸੋ", "बोलिए"])
def test_turn_claims_are_not_nods_and_can_interrupt(voice, clock, text):
    from server.services.pstn_lexicon import _BACKCHANNEL_NODS_RE

    assert _BACKCHANNEL_NODS_RE.fullmatch(text) is None
    assert voice._should_commit_barge(text) is False
    clock[0] += 0.301
    assert voice._should_commit_barge(text) is True


@pytest.mark.parametrize("explicit", [True, False])
def test_explicit_answer_state_wins_over_question_heuristic(voice, explicit):
    voice._last_tts_text = "This is a statement." if explicit else "Shall I proceed?"
    voice._expects_answer = explicit
    assert voice._filter_pending_backchannel("yes") == ("yes" if explicit else None)


@pytest.mark.parametrize("assistant,kept", [("The booking is confirmed.", False), ("సరేనా", True)])
def test_playback_drain_filters_nods_too(voice, monkeypatch, assistant, kept):
    voice._tts_active = False
    voice._set_phase(core.PHASE_LISTENING)
    voice._last_tts_text = assistant
    voice._pending_transcript = "అవును"
    arm = Mock()
    monkeypatch.setattr(voice, "_arm_listen_coalesce", arm)
    voice.on_playback_drained()
    assert arm.call_args_list == ([(('అవును',), {})] if kept else [])
    assert voice._pending_transcript is None


@pytest.mark.asyncio
@pytest.mark.parametrize("codec,sample_rate", [("mulaw", 8000), ("linear16", 16000)])
async def test_ducking_ramps_and_restores_without_leaking(voice, clock, codec, sample_rate):
    from server.services.audio_transcode import audioop, pcm16_rms

    voice.tts_output_codec = codec
    voice.sample_rate = sample_rate
    pcm = struct.pack("<h", 10000) * (sample_rate // 50)
    wire = audioop.lin2ulaw(pcm, 2) if codec == "mulaw" else pcm
    voice._on_vad_speech_onset()
    factors = [1.0]
    for _ in range(4):
        await voice._emit_agent_wire(wire)
        factors.append(voice._tts_current_factor)
        clock[0] += 0.02
    assert factors == pytest.approx([1.0, 0.8, 0.6, 0.4, 0.2])
    outputs = [call.args[0] for call in voice.on_agent_wire.await_args_list]
    decoded = [audioop.ulaw2lin(frame, 2) if codec == "mulaw" else frame for frame in outputs]
    assert all(len(frame) == len(wire) for frame in outputs)
    assert all(pcm16_rms(a) > pcm16_rms(b) for a, b in pairwise(decoded))
    if codec == "linear16":
        samples = struct.unpack("<" + "h" * (len(pcm) // 2), decoded[0])
        assert max(abs(a - b) for a, b in pairwise(samples)) <= 8
    # A later partial extends the timeout past the original onset.
    clock[0] += 0.7
    voice._stt = SttEvents([{"event": "transcript.partial", "text": "my appointment time"}])
    voice._schedule_interrupt_confirmation = Mock()
    await voice._stt_reader()
    assert voice._tts_duck_at == clock[0]
    clock[0] += 0.2
    await voice._emit_agent_wire(wire)
    assert voice._tts_ducked
    clock[0] += 0.66
    for _ in range(4):
        await voice._emit_agent_wire(wire)
    assert not voice._tts_ducked
    assert voice._tts_current_factor == pytest.approx(1.0)
    voice._tts_ducked = True
    voice._tts_current_factor = 0.2
    voice._set_tts_active(False)
    voice._set_tts_active(True)
    assert not voice._tts_ducked
    assert voice._tts_current_factor == 1.0


@pytest.mark.asyncio
async def test_vad_onset_ducks_and_nod_partial_releases_smoothly(voice, clock):
    voice._stt = SttEvents([{"event": "vad.speech_start"}])
    await voice._stt_reader()
    assert voice._tts_ducked
    assert voice._last_vad_voice_at == clock[0]
    voice._tts_current_factor = 0.4
    voice._stt = SttEvents([{"event": "transcript.partial", "text": "हाँ जी"}])
    voice._schedule_interrupt_confirmation = Mock()
    await voice._stt_reader()
    assert not voice._tts_ducked
    assert voice._tts_target_factor == 1.0
    assert voice._tts_current_factor == 0.4


@pytest.mark.asyncio
async def test_impulsive_pcm_is_forwarded_without_voice_or_duck(voice):
    voice._last_vad_voice_at = 0.0
    voice._stt = SimpleNamespace(send=AsyncMock())
    click = struct.pack("<160h", *([30000] + [0] * 159))
    for _ in range(2):
        await voice.feed_user_pcm16(click)
    assert voice._stt.send.await_count == 2
    assert voice._last_vad_voice_at == 0.0
    assert not voice._tts_ducked


@pytest.mark.asyncio
async def test_mp3_payload_is_unchanged(voice):
    voice.tts_output_codec = "mp3"
    voice._on_vad_speech_onset()
    assert not voice._tts_ducked
    payload = b"ID3\x00encoded-mp3"
    await voice._emit_agent_wire(payload)
    voice.on_agent_wire.assert_awaited_once_with(payload)


@pytest.mark.asyncio
async def test_barge_commit_resets_ducking(voice):
    voice._on_vad_speech_onset()
    voice._tts_current_factor = 0.2
    voice.interrupt_tts = AsyncMock()
    await voice._commit_barge("Stop")
    assert not voice._tts_ducked
    assert voice._tts_current_factor == voice._tts_target_factor == 1.0
    await voice.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("text,hold", [("Stop", 0.0), ("No", 0.15), ("I need more details", 0.3)])
async def test_lone_stt_result_confirms_at_the_right_hold(text, hold):
    import asyncio

    loop = core.PstnVoiceLoop(session_id="lone", call_id=None, on_agent_wire=AsyncMock())
    loop._set_phase(core.PHASE_SPEAKING)
    loop._tts_active = True
    loop._tts_started_at = time.monotonic() - 1.0
    loop._last_vad_voice_at = time.monotonic()
    loop._barge_runtime = {}
    loop._commit_barge = AsyncMock()
    started = time.monotonic()
    loop._schedule_interrupt_confirmation(text)
    await asyncio.wait_for(loop._barge_confirm_task, timeout=0.6)
    elapsed = time.monotonic() - started
    loop._commit_barge.assert_awaited_once_with(text)
    assert elapsed >= hold
    assert elapsed < hold + 0.15


@pytest.mark.asyncio
async def test_thinking_lone_final_obeys_voice_latch_and_hold():
    import asyncio

    loop = core.PstnVoiceLoop(session_id="final", call_id=None, on_agent_wire=AsyncMock())
    loop._set_phase(core.PHASE_THINKING)
    loop._turn_busy = True
    loop._think_cancel = AsyncMock()
    loop._stt = SttEvents([{"event": "transcript.final", "text": "No"}])
    await loop._stt_reader()
    await loop._barge_confirm_task
    loop._think_cancel.assert_not_awaited()
    assert loop._pending_transcript is None
    loop._last_vad_voice_at = time.monotonic()
    loop._stt = SttEvents([{"event": "transcript.final", "text": "No"}])
    await loop._stt_reader()
    loop._think_cancel.assert_not_awaited()
    await asyncio.wait_for(loop._barge_confirm_task, timeout=0.4)
    loop._think_cancel.assert_awaited_once_with("No", immediate=True)


@pytest.mark.parametrize("overrides", [{}, {"threshold": None, "silence_duration_ms": None}])
def test_adapter_sends_calibrated_defaults(monkeypatch, overrides):
    from server.providers import sarvam_stt
    from server.providers.base import STTConfig

    connect = Mock()
    monkeypatch.setattr(sarvam_stt, "connect_stt_realtime", connect)
    sarvam_stt.SarvamSTTAdapter().connect_realtime(STTConfig(
        provider="sarvam", model="saaras:v3-realtime", language="te-IN", vad_config=overrides,
    ))
    kwargs = connect.call_args.kwargs
    assert {key: kwargs[key] for key in ("threshold", "min_speech_duration_ms", "silence_duration_ms", "prefix_padding_ms")} == {
        "threshold": 0.55, "min_speech_duration_ms": 200, "silence_duration_ms": 300, "prefix_padding_ms": 300,
    }
    assert kwargs["high_vad_sensitivity"] is False


@pytest.mark.parametrize("overrides,expected", [({}, {"threshold": ["0.55"], "silence_duration_ms": ["300"]}),
    ({"threshold": 0.0, "silence_duration_ms": 0}, {"threshold": ["0.0"], "silence_duration_ms": ["0"]})])
def test_direct_ws_defaults_and_zero_overrides(monkeypatch, overrides, expected):
    from urllib.parse import parse_qs, urlsplit

    from server.services import sarvam_ws

    connect = Mock()
    monkeypatch.setattr(sarvam_ws, "_connect", connect)
    sarvam_ws.connect_stt_realtime(**overrides)
    params = parse_qs(urlsplit(connect.call_args.args[0]).query)
    assert all(params[key] == value for key, value in expected.items())
    assert params["min_speech_duration_ms"] == ["200"]
    assert params["prefix_padding_ms"] == ["300"]
    assert "high_vad_sensitivity" not in params


def test_repeated_multilingual_nods_are_classified_without_backtracking():
    from server.services.pstn_lexicon import is_backchannel

    assert is_backchannel("हाँ जी " * 1000)
    assert is_backchannel("yes, అవును, ஆம் " * 500)
    assert not is_backchannel("हाँ जी " * 1000 + "more details")
    assert not is_backchannel("yesplease")


@pytest.mark.parametrize("phase", [core.PHASE_CLOSING, core.PHASE_ENDED])
def test_strong_halt_does_not_reopen_terminal_phases(voice, phase):
    voice._set_phase(phase)
    assert voice._should_commit_barge("Stop") is False


@pytest.mark.asyncio
async def test_background_final_does_not_become_deferred_turn(voice):
    voice._last_vad_voice_at = 0.0
    voice._turn_busy = True
    voice._stt = SttEvents([{"event": "transcript.final", "text": "background conversation continues"}])
    await voice._stt_reader()
    await voice._barge_confirm_task
    assert voice._pending_transcript is None


@pytest.mark.asyncio
async def test_accepted_thinking_final_survives_fast_generation_completion(voice):
    voice._tts_active = False
    voice._set_phase(core.PHASE_THINKING)
    voice._turn_busy = True
    voice._stt = SttEvents([{"event": "transcript.final", "text": "No"}])
    await voice._stt_reader()
    assert voice._pending_transcript == "No"
    # Finishing this generation must invalidate its delayed cancellation.
    voice.current_generation_id = "next-generation"
    await voice._barge_confirm_task


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["না", "ના", "ਨਾ", "बस", "ऐक"])
async def test_short_native_barge_final_is_not_lost(voice, text):
    voice._tts_active = False
    voice._awaiting_barge_final = True
    voice._barge_epoch = 99.9
    voice._set_phase(core.PHASE_INTERRUPTING)
    voice._stt = SttEvents([{"event": "transcript.final", "text": text}])
    launch = Mock()
    voice._launch_turn = launch
    await voice._stt_reader()
    launch.assert_called_once_with(text)
    assert not voice._awaiting_barge_final


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime,silence,threshold", [({}, 300, None),
    ({"sttSilenceMs": 250, "sttThreshold": 0.0}, 250, 0.0)])
async def test_initial_and_reconnect_keep_the_same_stt_tuning(monkeypatch, runtime, silence, threshold):
    loop = core.PstnVoiceLoop(session_id="reconnect", call_id=None, on_agent_wire=AsyncMock())
    stt = SimpleNamespace(close=AsyncMock())
    cm = SimpleNamespace(__aenter__=AsyncMock(return_value=stt), __aexit__=AsyncMock())
    connect = Mock(return_value=cm)
    monkeypatch.setattr("server.routes.ws._connect_stt_upstream", connect)
    monkeypatch.setattr("server.services.runtime_settings.runtime_settings.get", lambda _sid: runtime)
    loop._stt_supervisor = AsyncMock()
    loop._stt_ping = AsyncMock()
    await loop.open_stt()
    assert await loop._reopen_stt_socket()
    assert connect.call_count == 2
    for call in connect.call_args_list:
        assert call.kwargs["silence_duration_ms"] == silence
        assert call.kwargs["threshold"] == threshold
    await loop.close()


@pytest.mark.asyncio
async def test_echo_refinement_cancels_an_earlier_short_partial_candidate():
    import asyncio

    loop = core.PstnVoiceLoop(session_id="echo-refine", call_id=None, on_agent_wire=AsyncMock())
    loop._tts_active = True
    loop._set_phase(core.PHASE_SPEAKING)
    loop._tts_started_at = time.monotonic() - 1.0
    loop._last_vad_voice_at = time.monotonic()
    loop._tts_heard_text = "Please confirm your booking"
    loop._stt = SttEvents([{"event": "transcript.partial", "text": "please confirm"},
                           {"event": "transcript.partial", "text": "please confirm your booking"}])
    loop._commit_barge = AsyncMock()
    await loop._stt_reader()
    await asyncio.gather(loop._barge_confirm_task, return_exceptions=True)
    loop._commit_barge.assert_not_awaited()
    assert not loop._tts_ducked


@pytest.mark.asyncio
async def test_strong_final_preempts_a_pending_general_confirmation():
    import asyncio

    loop = core.PstnVoiceLoop(session_id="urgent-final", call_id=None, on_agent_wire=AsyncMock())
    loop._tts_active = True
    loop._set_phase(core.PHASE_SPEAKING)
    loop._tts_started_at = time.monotonic() - 1.0
    loop._last_vad_voice_at = time.monotonic()
    loop._schedule_interrupt_confirmation("I need more details")
    await asyncio.sleep(0.01)
    loop._stt = SttEvents([{"event": "transcript.final", "text": "Stop"}])
    loop._commit_barge = AsyncMock()
    started = time.monotonic()
    await loop._stt_reader()
    await asyncio.wait_for(loop._barge_confirm_task, timeout=0.1)
    loop._commit_barge.assert_awaited_once_with("Stop")
    assert time.monotonic() - started < 0.15


@pytest.mark.asyncio
async def test_onset_grace_starts_when_carrier_reports_first_heard_frame(voice, clock):
    voice.playback = SimpleNamespace(defer_heard_until_sent=True)
    voice._tts_queued_text = "Here are the booking details."
    await voice._emit_agent_wire(b"\xff" * 160)
    assert voice._tts_started_at == 99.0
    clock[0] = 100.5
    voice._promote_queued_tts_to_heard()
    assert voice._tts_started_at == 100.5
    voice._last_vad_voice_at = clock[0]
    assert voice._should_commit_barge("I need more details") is False
    clock[0] += 0.301
    assert voice._should_commit_barge("I need more details") is False
    clock[0] += 0.05
    assert voice._should_commit_barge("I need more details") is True
    voice._tts_queued_text = "The next sentence."
    voice._promote_queued_tts_to_heard()
    assert voice._tts_started_at == 100.5


@pytest.mark.asyncio
@pytest.mark.parametrize("assistant,kept", [("Shall I proceed?", True), ("The booking is confirmed.", False)])
async def test_final_nod_after_carrier_drain_does_not_get_stuck_in_echo_tail(assistant, kept):
    import asyncio

    loop = core.PstnVoiceLoop(session_id="tail-answer", call_id=None, on_agent_wire=AsyncMock())
    loop._last_tts_text = assistant
    loop._tts_tail_until = time.monotonic() + core.PSTN_ECHO_TAIL_S
    loop._stt = SttEvents([{"event": "transcript.final", "text": "yes"}])
    loop._launch_turn = Mock()
    await loop._stt_reader()
    assert loop._pending_transcript is None
    if kept:
        assert loop._coalesce_task is not None
        await asyncio.wait_for(loop._coalesce_task, timeout=0.4)
        loop._launch_turn.assert_called_once_with("yes")
    else:
        assert loop._coalesce_task is None
        loop._launch_turn.assert_not_called()
