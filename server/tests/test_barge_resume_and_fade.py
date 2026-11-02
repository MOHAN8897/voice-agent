"""Industry-standard interruption: resume a false interruption, fade out at the cut."""
import asyncio
import base64
import json
import struct
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from server.agent import conversation_manager as cm_module
from server.agent.conversation_manager import ConversationManager
from server.prompts.tts_delivery_rules import tts_delivery_rules
from server.services import pstn_voice_core as core
from server.services import vobiz_pstn_bridge as bridge_module
from server.services.pstn_voice_core import PHASE_LISTENING, PstnVoiceLoop


@pytest.fixture
def loop(monkeypatch):
    monkeypatch.setattr(core, "PSTN_FALSE_INTERRUPTION_TIMEOUT_S", 0.05)
    voice = PstnVoiceLoop(session_id="s", call_id=None, on_agent_wire=lambda _: None)
    voice.speak = AsyncMock()
    voice._set_phase(PHASE_LISTENING)
    history = ConversationManager()
    monkeypatch.setattr(cm_module, "conversation_manager", history)
    return voice, history


@pytest.mark.asyncio
async def test_false_interruption_resumes_from_the_cut_sentence(loop):
    voice, history = loop
    history.add_turn("s", "what is the fee", "Hello. Our fee is five hundred rupees a month.")
    history.note_barge("s", "Hello. Our fee is")
    epoch = time.monotonic()
    voice._barge_epoch = epoch
    await voice._resume_after_false_interruption(epoch, "Hello.", "Our fee is five hundred rupees a month.")
    voice.speak.assert_awaited_once_with("Our fee is five hundred rupees a month.")
    # The model's memory matches what the caller heard in the end.
    assert history.get_history("s")[-1]["content"] == "Hello. Our fee is five hundred rupees a month."


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["caller_turn", "new_barge", "pending", "busy", "closed"])
async def test_a_real_caller_turn_or_a_newer_barge_is_never_talked_over(loop, change):
    voice, _ = loop
    epoch = time.monotonic()
    voice._barge_epoch = epoch
    if change == "caller_turn":
        voice._last_caller_turn_at = epoch + 0.01
    elif change == "new_barge":
        voice._barge_epoch = epoch + 1
    elif change == "pending":
        voice._pending_transcript = "actually I wanted to ask"
    elif change == "busy":
        voice._turn_busy = True
    else:
        voice._closed = True
    await voice._resume_after_false_interruption(epoch, "", "Our fee is five hundred rupees.")
    voice.speak.assert_not_awaited()


@pytest.mark.asyncio
async def test_commit_keeps_the_cut_sentence_and_what_was_queued(loop, monkeypatch):
    voice, _ = loop
    armed = []

    async def capture(epoch, before_cut, remainder):
        armed.append((before_cut, remainder))

    monkeypatch.setattr(voice, "_resume_after_false_interruption", capture)
    voice.interrupt_tts = AsyncMock()
    voice._heard_sentences = ["Hi there.", "Our fee is five hundred"]
    voice._tts_queued_text = "rupees a month."
    await voice._commit_barge("wait what")
    await asyncio.sleep(0)
    assert armed == [("Hi there.", "Our fee is five hundred rupees a month.")]


def _frame(amplitude: int, samples: int = 320) -> bytes:
    return struct.pack(f"<{samples}h", *([amplitude] * samples))


def _peak(payload: str) -> int:
    pcm = base64.b64decode(payload)
    return max(abs(value) for (value,) in struct.iter_unpack("<h", pcm))


@pytest.mark.asyncio
async def test_barge_fades_the_next_frames_to_silence_after_clearing():
    ws = MagicMock(send_text=AsyncMock())
    bridge = bridge_module.VobizPstnBridge(ws)
    bridge._wire_codec = "linear16"
    bridge._upcoming_wire = ([_frame(10000)] * bridge_module.VOBIZ_BARGE_FADE_FRAMES, "audio/x-l16", 16000)
    await bridge._barge_in()
    sent = [json.loads(call.args[0]) for call in ws.send_text.await_args_list]
    assert sent[0]["event"] == "clearAudio"
    fade = [msg for msg in sent[1:] if msg["event"] == "playAudio"]
    peaks = [_peak(msg["media"]["payload"]) for msg in fade]
    assert len(fade) == bridge_module.VOBIZ_BARGE_FADE_FRAMES
    assert peaks == sorted(peaks, reverse=True) and peaks[-1] < 2600
    # Nothing is left to fade a second time.
    assert bridge._upcoming_wire[0] == []


@pytest.mark.asyncio
async def test_alaw_calls_keep_the_plain_clear():
    ws = MagicMock(send_text=AsyncMock())
    bridge = bridge_module.VobizPstnBridge(ws)
    bridge._wire_codec = "alaw"
    bridge._upcoming_wire = ([b"\x55" * 160] * 4, "audio/x-alaw;rate=8000", 8000)
    await bridge._barge_in()
    assert [json.loads(call.args[0])["event"] for call in ws.send_text.await_args_list] == ["clearAudio"]


def test_gnani_v3_guidance_lets_the_agent_laugh_at_a_joke_and_others_stay_plain():
    gnani = tts_delivery_rules("gnani", "timbre-v3.0", "te-IN")
    assert "jokes" in gnani and "<laugh>" in gnani and "at most one cue" in gnani
    assert "no-forced-laughter note does not forbid it" in gnani
    for provider, model in (("sarvam", "bulbul:v3"), ("gnani", "timbre-v2.5"), ("gemini", "gemini-3.8-flash-tts")):
        assert "No inline audio tags" in tts_delivery_rules(provider, model, "te-IN")
