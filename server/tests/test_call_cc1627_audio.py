"""Regressions from the audio of call CC1627 (Telugu, Gnani Timbre v3.0 over Vobiz).

The caller heard the agent start over them, keep talking ~1.2 s after they cut
in at full volume, amounts read as "85 rupees lakhs", a dotted unit read as
noise, "one minute" before every slow answer, and no listening sounds at all.
"""
from __future__ import annotations

import asyncio
import json
import struct
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from server.call.audio_archive import audio_archive
from server.config.env import get_settings
from server.services import pstn_voice_core as core
from server.services import vobiz_pstn_bridge as bridge_module
from server.services.pstn_backchannel import HOLDING_PHRASES, PstnBackchannelController
from server.services.spoken_numbers import indian_grouping, prepare_spoken_reply


def _gnani(text: str, language: str = "te-IN") -> str:
    return prepare_spoken_reply(text, provider="gnani", model="timbre-v3.0", language=language)


# ------------------------------------------------------------------ what the voice is sent
def test_lakh_and_crore_amounts_become_full_indian_grouped_numbers():
    # Probe: "₹85 Lakhs" was read "85 rupees lakhs"; "₹85,00,000" as "85 lakh rupees".
    said = _gnani("ధర ₹85 Lakhs నుంచి ₹1.10 Crore వరకు ఉంటుంది.")
    assert said == "ధర ₹85,00,000 నుంచి ₹1,10,00,000 వరకు ఉంటుంది."
    assert _gnani("so 50 lakhs budget కి options లేవు.") == "so 50,00,000 budget కి options లేవు."
    assert _gnani("₹1 crore 10 lakh") == "₹1,10,00,000."
    assert _gnani("Rs. 2 lakh 50 thousand") == "₹2,50,000."
    # A fraction of a rupee cannot be grouped: keep the scale word, lower-cased.
    assert _gnani("₹2.123456 Lakh") == "₹2.123456 lakh."
    # Sarvam documents the same grouping; other engines keep what was written.
    assert prepare_spoken_reply("Price ₹85 Lakhs.", provider="sarvam", model="bulbul:v3",
                                language="en-IN") == "Price ₹85,00,000."
    assert "₹85 Lakhs" in prepare_spoken_reply("Price ₹85 Lakhs.", provider="cartesia",
                                                model="sonic-3.5", language="en-IN")


def test_indian_grouping():
    assert [indian_grouping(n) for n in (999, 1000, 150000, 11000000, 1234567890)] == [
        "999", "1,000", "1,50,000", "1,10,00,000", "1,23,45,67,890"]


def test_area_units_are_written_out_for_every_engine():
    # Probe: "1,850 Sq.ft." was unintelligible; "square feet" was read correctly.
    said = _gnani("area 1,450 నుంచి 1,850 Sq.ft. అలాగే Kokapet లో ఉంది.")
    assert said == "area 1,450 నుంచి 1,850 square feet. అలాగే Kokapet లో ఉంది."
    assert _gnani("1200 sft, 200 sq. yds plot") == "1200 square feet, 200 square yards plot."
    for provider, model in (("sarvam", "bulbul:v3"), ("cartesia", "sonic-3.5"), ("gemini", "gemini-3.8-flash-tts")):
        assert "square feet" in prepare_spoken_reply("It is 1,850 sq ft.", provider=provider, model=model, language="en-IN")


def test_gnani_hears_clock_times_with_the_part_of_day_not_am_pm():
    # Probe: "10:30 AM" became "ten hours thirty minutes A M"; "ఉదయం 10:30" read naturally.
    assert _gnani("రేపు 10:30 AM కి call చేస్తాను.") == "రేపు ఉదయం 10:30 కి call చేస్తాను."
    assert _gnani("సాయంత్రం 6 PM కి కలుద్దాం.") == "సాయంత్రం 6 కి కలుద్దాం."
    assert _gnani("रात 9 PM तक.", "hi-IN") == "रात 9 तक."
    assert _gnani("कल 2 PM.", "hi-IN") == "कल दोपहर 2."
    # English calls and other engines are unchanged.
    assert "10:30 AM" in prepare_spoken_reply("Come at 10:30 AM.", provider="sarvam", model="bulbul:v3", language="hi-IN")


def test_holding_line_promises_a_second_not_a_minute():
    assert HOLDING_PHRASES["te-IN"] == "ఒక్క క్షణం."
    for lang, phrase in HOLDING_PHRASES.items():
        assert "నిమిషం" not in phrase and "மிஷம்" not in phrase and "मिनिट" not in phrase, lang


def test_gnani_prompt_no_longer_asks_for_number_words():
    from server.prompts.tts_delivery_rules import tts_delivery_rules

    rules = tts_delivery_rules("gnani", "timbre-v3.0", "te-IN")
    assert "reads digits itself" in rules and "square feet" in rules
    assert "does not read digits" not in rules


# ------------------------------------------------------------------ talking over the caller
@pytest.fixture
def clock(monkeypatch):
    value = [100.0]
    monkeypatch.setattr(core, "time", SimpleNamespace(monotonic=lambda: value[0], perf_counter=time.perf_counter))
    return value


@pytest.fixture
def replying(clock):
    """A reply whose text reached the TTS but which the caller has not heard yet."""
    loop = core.PstnVoiceLoop(session_id="cc1627", call_id=None, on_agent_wire=AsyncMock())
    loop.current_generation_id = "reply-gen"
    loop._set_phase(core.PHASE_SPEAKING)
    loop._tts_active = True
    loop._turn_busy = True
    loop._tts_started_at = 99.8
    loop._last_vad_voice_at = 100.0
    loop._current_turn_transcript = "ఓకే ఆ"
    loop._barge_runtime = {}
    return loop


def test_caller_still_talking_before_the_reply_is_heard_cancels_it(replying, clock):
    # 109.6 s in the call: the caller resumed and the agent started over them.
    assert replying._should_cancel_unheard_reply("నాకు బెస్ట్ బడ్జెట్") is True
    # The ordinary barge gate would still be holding (2 words, echo shield).
    assert replying._should_commit_barge("నాకు బెస్ట్ బడ్జెట్") is False


@pytest.mark.parametrize("text", ["సరే", "ఓకే ఆ", ""])
def test_nods_and_stt_refinements_never_cancel_an_unheard_reply(replying, text):
    assert replying._should_cancel_unheard_reply(text) is False


def test_once_the_caller_can_hear_the_reply_the_barge_rules_apply(replying, clock):
    replying._turn_first_audio_at = 100.0
    clock[0] = 100.2
    replying._last_vad_voice_at = clock[0]
    assert replying._should_cancel_unheard_reply("నాకు బెస్ట్ బడ్జెట్") is True
    clock[0] = 100.5
    replying._last_vad_voice_at = clock[0]
    assert replying._should_cancel_unheard_reply("నాకు బెస్ట్ బడ్జెట్") is False


def test_no_voice_evidence_no_cancel(replying):
    replying._last_vad_voice_at = 0.0
    assert replying._should_cancel_unheard_reply("నాకు బెస్ట్ బడ్జెట్") is False


@pytest.mark.asyncio
async def test_cancelled_unheard_reply_keeps_both_utterances_for_the_relaunch(replying):
    turn = asyncio.create_task(asyncio.sleep(10))
    replying._active_speak_task = turn
    replying.interrupt_tts = AsyncMock()
    await replying._cancel_unheard_reply("నాకు బెస్ట్ బడ్జెట్ 50 లాక్స్")
    await asyncio.sleep(0)
    assert turn.cancelled()
    assert replying._pending_transcript == "ఓకే ఆ నాకు బెస్ట్ బడ్జెట్ 50 లాక్స్"
    assert replying._think_cancel_relaunch == "coalesce"
    replying.interrupt_tts.assert_awaited_once()


# ------------------------------------------------------------------ audio pacing to Vobiz
@pytest.mark.asyncio
async def test_vobiz_audio_is_paced_in_real_time_across_single_frame_sends():
    # Unpaced, 13 s of TTS sat in Vobiz's buffer: a volume duck or a stop took
    # effect only after it played out.
    sent_at: list[float] = []

    async def send_text(_msg: str) -> None:
        sent_at.append(time.monotonic())

    bridge = bridge_module.VobizPstnBridge(MagicMock(send_text=send_text))
    bridge._wire_codec = "linear16"
    bridge._wire_sample_rate = 16000
    frame = struct.pack("<320h", *([1000] * 320))
    start = time.monotonic()
    for _ in range(30):  # 0.6 s of audio, handed over one 20 ms frame at a time
        await bridge._send_agent_wire(frame)
    elapsed = time.monotonic() - start
    assert len(sent_at) == 30
    assert elapsed >= 0.6 - bridge_module.VOBIZ_SEND_LEAD_S - 0.05
    # Never more than the lead ahead of playback.
    for index, at in enumerate(sent_at):
        assert (index * 0.02) - (at - start) <= bridge_module.VOBIZ_SEND_LEAD_S + 0.03


@pytest.mark.asyncio
async def test_realtime_loop_keeps_its_unthrottled_send():
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    assert PstnRealtimeVoiceLoop.paced_carrier_send is False
    bridge = bridge_module.VobizPstnBridge(MagicMock(send_text=AsyncMock()))
    bridge._voice = SimpleNamespace(paced_carrier_send=False, current_generation_id=None)
    bridge._wire_codec = "linear16"
    bridge._wire_sample_rate = 16000
    frame = struct.pack("<320h", *([1000] * 320))
    start = time.monotonic()
    for _ in range(30):
        await bridge._send_agent_wire(frame)
    assert time.monotonic() - start < 0.2


@pytest.mark.asyncio
async def test_clear_audio_restarts_the_pacing_clock():
    bridge = bridge_module.VobizPstnBridge(MagicMock(send_text=AsyncMock()))
    bridge._wire_codec = "linear16"
    bridge._play_clock = time.monotonic() + 5.0
    await bridge._barge_in()
    assert bridge._play_clock == 0.0


# ------------------------------------------------------------------ listening sounds
def _bc_voice(**kw):
    voice = SimpleNamespace(_closed=False, _turn_busy=False, _phase=core.PHASE_LISTENING, _intro_phase=False,
                            _backchannel_playing=True, _cancel_backchannel=MagicMock(), **kw)
    return voice


def test_stt_refinement_does_not_cut_a_playing_listening_sound(monkeypatch):
    voice = _bc_voice()
    controller = PstnBackchannelController(voice)
    monkeypatch.setattr(controller, "_schedule_watch", lambda: None)
    controller._fired_words = 6
    controller.note_partial("నాకు మినిమం బడ్జెట్ వచ్చేసి 50 లాక్స్")  # same six words, refined
    voice._cancel_backchannel.assert_not_called()
    controller.note_partial("నాకు మినిమం బడ్జెట్ వచ్చేసి 50 లాక్స్ అనుకుంటున్నాను")
    voice._cancel_backchannel.assert_called_once()


@pytest.mark.asyncio
async def test_listening_sound_plays_from_memory_or_not_at_all(clock):
    loop = core.PstnVoiceLoop(session_id="bc", call_id=None, on_agent_wire=AsyncMock())
    loop._set_phase(core.PHASE_LISTENING)
    await loop._play_backchannel("సరే.", frames=[b"\x00" * 640, b"\x00" * 640])
    assert loop.on_agent_wire.await_count == 2
    assert loop._backchannel_playing is False and loop.current_generation_id is None


# ------------------------------------------------------------------ the call recording
@pytest.fixture
def archive(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_CALL_ARCHIVE", "true")
    get_settings.cache_clear()
    audio_archive.reset_for_tests()
    yield audio_archive
    audio_archive.reset_for_tests()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_agent_track_keeps_the_call_timeline(archive):
    call_id = "cc1627-timeline"
    archive.init(call_id)
    archive.set_agent_sample_rate(call_id, 16000)
    second = b"\x01\x00" * 16000
    await archive.append_agent_audio(call_id, second)          # opening, 0-1 s
    await archive.append_user_pcm(call_id, second * 3)         # caller audio to 3 s
    await archive.append_agent_audio(call_id, second)          # reply at 3 s, not at 1 s
    await archive.flush(call_id)
    agent = archive.agent_pcm_path(call_id).read_bytes()
    assert len(agent) == len(second) * 4
    assert agent[len(second):len(second) * 3] == bytes(len(second) * 2)
