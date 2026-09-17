"""Realtime audio PSTN path — factory, stack, session payload, costing (no live WS)."""
from __future__ import annotations

import asyncio
import struct
from unittest.mock import AsyncMock

import pytest

from server.realtime.models import (
    pipeline_mode,
    resolve_realtime_voice_model,
    uses_realtime_text,
    uses_realtime_voice,
)
from server.realtime.providers.openai_voice import build_realtime_voice_session
from server.realtime.text_session import build_audio_session_instructions, build_session_instructions
from server.realtime.testing import FakeRealtimeVoiceAdapter
from server.services.pstn_stack import normalize_pstn_stack_override
from server.services.pstn_voice_core import PstnVoiceLoop
from server.services.pstn_voice_flow import create_pstn_voice_loop
from server.services.usage_pricing import cost_llm_usd


def test_pipeline_mode_realtime_voice_from_stack():
    assert pipeline_mode(stack_override={"pipeline": "realtime_voice"}) == "realtime_voice"
    assert uses_realtime_voice(stack_override={"voice_flow": "realtime_e2e"})
    assert not uses_realtime_text(stack_override={"pipeline": "realtime_voice"})
    assert pipeline_mode(stack_override={"pipeline": "realtime_text"}) == "realtime_text"
    assert uses_realtime_text(stack_override={"pipeline": "realtime_text"})
    assert pipeline_mode(stack_override={"pipeline": "realtime_text", "voice_flow": "realtime_e2e"}) == "realtime_text"


def test_composed_pstn_stack_still_strips_llm():
    raw = {
        "stt": {"provider": "sarvam", "model": "saaras:v3", "config": {"mode": "transcribe"}},
        "tts": {"provider": "sarvam", "model": "bulbul:v3", "config": {"speaker": "shubh"}},
        "llm": {"provider": "openai", "model": "gpt-5.6-luna"},
    }
    out, _adj = normalize_pstn_stack_override(raw, language="te-IN")
    assert out is not None
    assert out.get("pipeline") == "realtime_text"
    assert "llm" not in out
    assert out["stt"]["model"] == "saaras:v3-realtime"


def test_realtime_voice_stack_keeps_mini_and_voice():
    raw = {
        "pipeline": "realtime_voice",
        "voice_flow": "realtime_e2e",
        "llm": {"provider": "openai", "model": "gpt-realtime-2.1-mini"},
        "realtime_voice": {
            "voice": "marin",
            "turn_detection": "semantic_vad",
            "vad_eagerness": "high",
            "noise_reduction": "far_field",
            "speed": 1.05,
        },
        "stt": {"provider": "sarvam", "model": "saaras:v3"},
    }
    out, _adj = normalize_pstn_stack_override(raw, language="te-IN")
    assert out["pipeline"] == "realtime_voice"
    assert out["voice_flow"] == "realtime_e2e"
    assert out["llm"]["model"] == "gpt-realtime-2.1-mini"
    assert out["realtime_voice"]["voice"] == "marin"
    assert out["realtime_voice"]["vad_eagerness"] == "high"
    assert out["realtime_voice"]["noise_reduction"] == "far_field"
    assert out["realtime_voice"]["speed"] == 1.05
    assert "stt" not in out
    assert "tts" not in out


def test_realtime_voice_session_omits_noise_reduction_when_off():
    session = build_realtime_voice_session(
        model="gpt-realtime-2.1-mini",
        instructions="You are a helpful agent.",
        voice="marin",
        noise_reduction="off",
    )
    assert "noise_reduction" not in session["audio"]["input"]


def test_realtime_voice_config_reads_top_level_noise_reduction():
    from server.realtime.models import realtime_voice_config

    cfg = realtime_voice_config({"pipeline": "realtime_voice", "noise_reduction": "off"})
    assert cfg["noise_reduction"] == "off"


def test_realtime_voice_session_is_audio_pcm_24k():
    session = build_realtime_voice_session(
        model="gpt-realtime-2.1-mini",
        instructions="You are a helpful agent.",
        voice="marin",
        turn_detection="semantic_vad",
        vad_eagerness="medium",
        noise_reduction="far_field",
        speed=1.0,
    )
    assert session["type"] == "realtime"
    assert session["output_modalities"] == ["audio"]
    assert session["audio"]["input"]["format"]["type"] == "audio/pcm"
    assert session["audio"]["input"]["format"]["rate"] == 24000
    assert session["audio"]["output"]["format"]["rate"] == 24000
    assert session["audio"]["output"]["voice"] == "marin"
    assert session["audio"]["output"]["speed"] == 1.0
    assert session["audio"]["input"]["turn_detection"]["type"] == "semantic_vad"
    assert session["audio"]["input"]["turn_detection"]["interrupt_response"] is False
    assert session["audio"]["input"]["noise_reduction"]["type"] == "far_field"
    assert session["max_output_tokens"] == 4096
    assert any(t.get("name") == "end_call" for t in session["tools"])


def test_realtime_voice_ignores_text_turn_token_cap():
    from server.realtime.models import REALTIME_VOICE_MAX_OUTPUT_TOKENS, resolve_realtime_voice_max_output_tokens

    assert resolve_realtime_voice_max_output_tokens(None) == REALTIME_VOICE_MAX_OUTPUT_TOKENS
    assert resolve_realtime_voice_max_output_tokens(240) == REALTIME_VOICE_MAX_OUTPUT_TOKENS
    assert resolve_realtime_voice_max_output_tokens(8192) == 8192
    session = build_realtime_voice_session(
        model="gpt-realtime-2.1-mini",
        instructions="You are a helpful agent.",
        max_output_tokens=240,
    )
    assert session["max_output_tokens"] == 4096


def test_audio_instructions_reuse_compiled_brain():
    brain = "--- AGENT IDENTITY ---\nYou are Priya, representing SKM Plants."
    text = build_session_instructions(brain, language="te-IN")
    audio = build_audio_session_instructions(brain, language="te-IN")
    assert "You are Priya, representing SKM Plants." in audio
    assert "OUTPUT MODALITY RULES" in audio
    assert "Speak the reply as natural speech" in audio
    for marker in ("PHONE CALL POLICY", "end_call", "LENGTH"):
        if marker in text:
            assert marker in audio or "end_call" in audio


def test_outbound_audio_instructions_wait_for_callee():
    brain = (
        "--- AGENT IDENTITY ---\nYou are Priya, representing Bindusara Agencies.\n\n"
        "--- CANONICAL OPENING ---\nHi, this is Priya calling from Bindusara Agencies. Do you have a moment?"
    )
    audio = build_audio_session_instructions(
        brain,
        language="en-IN",
        direction="outbound",
        opening_greeting="Hi, this is Priya calling from Bindusara Agencies. Do you have a moment?",
    )
    assert "FIRST TURN / IDENTITY (outbound" in audio
    assert "Do NOT speak until the callee" in audio
    assert "help-desk" in audio.lower()
    assert "Inbound caller connected" not in audio
    assert "Do you have a moment?" in audio
    assert "maximum 20 spoken words" in audio
    assert "Ask at most one question" in audio


def test_audio_token_cost_uses_mini_audio_rates():
    cost = cost_llm_usd(
        input_tokens=600,
        output_tokens=1200,
        llm_model="gpt-realtime-2.1-mini",
        input_audio_tokens=600,
        output_audio_tokens=1200,
    )
    assert cost["audio_input_usd"] == pytest.approx(0.006, rel=1e-6)
    assert cost["audio_output_usd"] == pytest.approx(0.024, rel=1e-6)
    assert cost["total_usd"] == pytest.approx(0.03, rel=1e-6)


def test_cached_audio_tokens_use_cached_audio_rate():
    full = cost_llm_usd(
        input_tokens=600,
        output_tokens=0,
        llm_model="gpt-realtime-2.1-mini",
        input_audio_tokens=600,
        cached_audio_tokens=0,
    )
    cached = cost_llm_usd(
        input_tokens=600,
        output_tokens=0,
        llm_model="gpt-realtime-2.1-mini",
        input_audio_tokens=600,
        cached_audio_tokens=600,
    )
    assert full["audio_input_usd"] == pytest.approx(0.006, rel=1e-6)
    assert cached["audio_input_usd"] == pytest.approx(600 * 0.30 / 1_000_000, rel=1e-6)
    assert cached["audio_input_usd"] < full["audio_input_usd"]


def test_factory_keeps_composed_loop_for_realtime_text():
    async def _wire(_b: bytes) -> None:
        return None

    composed = create_pstn_voice_loop(
        stack_override={"pipeline": "realtime_text"},
        session_id="s",
        call_id="c",
        on_agent_wire=_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
    )
    assert isinstance(composed, PstnVoiceLoop)
    voice = create_pstn_voice_loop(
        stack_override={"pipeline": "realtime_voice"},
        session_id="s",
        call_id="c",
        on_agent_wire=_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=FakeRealtimeVoiceAdapter(),
    )
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    assert isinstance(voice, PstnRealtimeVoiceLoop)


@pytest.mark.asyncio
async def test_realtime_loop_appends_resampled_pcm():
    chunks: list[bytes] = []

    async def on_wire(wire: bytes) -> None:
        chunks.append(wire)

    adapter = FakeRealtimeVoiceAdapter()
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id="c-rt",
        on_agent_wire=on_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice"},
    )
    await loop.start_call(play_greeting=False)
    assert adapter.max_output_tokens == 4096
    silence_16k = b"\x00\x00" * 320  # 20 ms @ 16 kHz
    await loop.feed_user_pcm16(silence_16k)
    assert adapter.appended, "user PCM should be appended to Realtime as 24 kHz"
    await loop.close()


@pytest.mark.asyncio
async def test_realtime_loop_echo_does_not_barge():
    barged: list[int] = []

    async def on_wire(_wire: bytes) -> None:
        return None

    async def on_barge() -> None:
        barged.append(1)

    adapter = FakeRealtimeVoiceAdapter()
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id="c-echo",
        on_agent_wire=on_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice"},
    )
    loop.set_barge_handler(on_barge)
    await loop.start_call(play_greeting=False)
    loop._set_tts_active(True)
    await loop._handle_event({"type": "speech_started"})
    assert barged == []
    assert adapter.cancelled == 0
    await loop.close()


@pytest.mark.asyncio
async def test_realtime_loop_barge_clears_telnyx():
    barged: list[int] = []

    async def on_wire(_wire: bytes) -> None:
        return None

    async def on_barge() -> None:
        barged.append(1)

    adapter = FakeRealtimeVoiceAdapter()
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id="c-barge",
        on_agent_wire=on_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice"},
    )
    loop.set_barge_handler(on_barge)
    await loop.start_call(play_greeting=False)
    loop._set_tts_active(True)
    loop._aec_barge_open = True
    await loop._handle_event({"type": "speech_started"})
    assert barged
    assert adapter.cancelled >= 1
    await loop.close()


@pytest.mark.asyncio
async def test_realtime_loop_holds_echo_pcm_during_agent_speech():
    import struct

    async def on_wire(_wire: bytes) -> None:
        return None

    adapter = FakeRealtimeVoiceAdapter()
    from server.services.pstn_realtime_voice_core import (
        REALTIME_AEC_LOUD_OPEN_FRAMES,
        PstnRealtimeVoiceLoop,
    )

    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id="c-aec",
        on_agent_wire=on_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice"},
    )
    await loop.start_call(play_greeting=False)
    loop._set_tts_active(True)
    quiet = b"\x00\x00" * 320
    await loop.feed_user_pcm16(quiet)
    assert adapter.appended == []
    subthreshold = struct.pack("<" + "h" * 320, *([800] * 320))
    await loop.feed_user_pcm16(subthreshold)
    assert adapter.appended == []
    loud = struct.pack("<" + "h" * 320, *([2200] * 320))
    for _ in range(REALTIME_AEC_LOUD_OPEN_FRAMES):
        await loop.feed_user_pcm16(loud)
    assert adapter.appended, "normal phone speech should reach OpenAI after the loud-frame gate"
    assert adapter.cancelled >= 1, "barge_open must cut the in-flight agent response immediately"
    await loop.close()


def test_resolve_realtime_voice_model_prefers_stack_over_runtime():
    assert (
        resolve_realtime_voice_model(
            {"llm": {"model": "gpt-realtime-2.1"}},
            "gpt-realtime-2.1-mini",
        )
        == "gpt-realtime-2.1"
    )
    assert resolve_realtime_voice_model({"pipeline": "realtime_voice"}, "gpt-5.6-luna") == "gpt-realtime-2.1-mini"
    assert resolve_realtime_voice_model(None, "gpt-realtime-2") == "gpt-realtime-2"


@pytest.mark.asyncio
async def test_realtime_loop_uses_stack_model_and_records_audio_cost():
    from server.call.call_ledger import call_ledger
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    call_id = "c-usage-rt"
    await call_ledger.init(call_id, {"call_id": call_id})

    async def on_wire(_wire: bytes) -> None:
        return None

    adapter = FakeRealtimeVoiceAdapter(
        events=[
            {"type": "response_created"},
            {"type": "assistant_transcript", "text": "Hello from Realtime."},
            {
                "type": "response_done",
                "usage": {
                    "input_tokens": 600,
                    "output_tokens": 1200,
                    "cached_tokens": 0,
                    "cache_write_tokens": 0,
                    "input_audio_tokens": 600,
                    "output_audio_tokens": 1200,
                },
            },
        ]
    )
    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id=call_id,
        on_agent_wire=on_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={
            "pipeline": "realtime_voice",
            "llm": {"provider": "openai", "model": "gpt-realtime-2.1"},
        },
    )
    await loop.start_call(play_greeting=False)
    await asyncio_wait_pump()
    assert adapter.model == "gpt-realtime-2.1"
    trace = call_ledger.read_trace(call_id)
    assert trace["turns"]
    turn = trace["turns"][0]
    assert turn["input_audio_tokens"] == 600
    assert turn["output_audio_tokens"] == 1200
    assert turn["pipeline"] == "realtime_voice"
    assert turn["cost_usd"] == pytest.approx(0.096, rel=1e-6)
    meta = call_ledger.read_meta(call_id)
    assert meta["usage"]["turns"] == 1
    assert meta["usage"]["cost_usd"] == pytest.approx(0.096, rel=1e-6)
    await loop.close()


@pytest.mark.asyncio
async def test_save_config_realtime_voice_writes_openai_model_not_sarvam(monkeypatch):
    from server.routes import test_studio
    from server.services.session_persist import SessionPersist

    captured: dict = {}

    class _Store:
        def get_ui(self, _sid: str):
            return {}

        def set_ui(self, _sid: str, _prefs: dict) -> None:
            return None

    class _Runtime:
        def update(self, _sid: str, patch: dict) -> dict:
            captured.update(patch)
            return patch

    monkeypatch.setattr(test_studio, "session_persist", _Store())
    monkeypatch.setattr("server.services.runtime_settings.runtime_settings", _Runtime())

    result = await test_studio.save_test_studio_prefs(
        test_studio.TestStudioUiPrefs(
            sessionId="test-studio:agent",
            saveConfig=True,
            stack={"llmModel": "gpt-realtime-2.1", "ttsVoiceId": "shubh", "sttModel": "saaras:v3"},
            stackOverride={"pipeline": "realtime_voice", "llm": {"model": "gpt-realtime-2.1"}},
        )
    )
    assert result["ok"]
    assert captured.get("openaiModel") == "gpt-realtime-2.1"
    assert "ttsSpeaker" not in captured
    assert "sttModel" not in captured


@pytest.mark.asyncio
async def test_realtime_loop_archives_user_and_agent_pcm(monkeypatch, tmp_path):
    import struct
    import wave

    from server.call.audio_archive import audio_archive
    from server.call.call_ledger import call_ledger
    from server.config.env import get_settings
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_CALL_ARCHIVE", "true")
    get_settings.cache_clear()
    audio_archive.reset_for_tests()
    call_ledger.reset_for_tests()

    call_id = "c-archive-rt"
    audio_archive.init(call_id)
    await call_ledger.init(call_id, {"call_id": call_id, "pipeline": "realtime_voice"})

    async def on_wire(_wire: bytes) -> None:
        return None

    pcm24 = struct.pack("<" + "h" * 480, *([1200] * 480))
    adapter = FakeRealtimeVoiceAdapter(
        events=[
            {"type": "response_created"},
            {"type": "audio_delta", "pcm": pcm24},
            {
                "type": "response_done",
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 10,
                    "input_audio_tokens": 10,
                    "output_audio_tokens": 10,
                },
            },
        ]
    )
    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id=call_id,
        on_agent_wire=on_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice"},
    )
    await loop.start_call(play_greeting=False)
    user = struct.pack("<" + "h" * 320, *([800] * 320))
    await loop.feed_user_pcm16(user)
    import asyncio

    await asyncio.sleep(0.15)
    await loop.close()
    status = await audio_archive.flush(call_id)
    assert status["user"] == "complete"
    assert status["agent"] == "complete"
    with wave.open(str(audio_archive.mix_path(call_id)), "rb") as wf:
        assert wf.getframerate() == 16000
        assert wf.getnframes() >= 320
    assert audio_archive.file_for(call_id, "user").suffix == ".wav"
    assert audio_archive.file_for(call_id, "agent").suffix == ".wav"
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_agent_hangup_drains_archive_before_lifecycle_end(monkeypatch, tmp_path):
    monkeypatch.setattr("server.call.natural_hangup.HANGUP_TRAIL_SILENCE_SEC", 0.01)
    import struct

    from server.call.audio_archive import _agent_buffers, _user_buffers, audio_archive
    from server.call.call_ledger import call_ledger
    from server.call.call_lifecycle_service import call_lifecycle_service
    from server.config.env import get_settings
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_CALL_ARCHIVE", "true")
    get_settings.cache_clear()
    audio_archive.reset_for_tests()
    call_ledger.reset_for_tests()

    call_id = "c-hangup-rt"
    audio_archive.init(call_id)
    await call_ledger.init(call_id, {"call_id": call_id, "pipeline": "realtime_voice"})

    seen: dict[str, int | str] = {}

    async def fake_end(cid: str, *, reason: str = "user_stop"):
        seen["user"] = len(_user_buffers.get(cid, b""))
        seen["agent"] = len(_agent_buffers.get(cid, b""))
        seen["reason"] = reason
        return {"call_id": cid, "status": "processing"}

    monkeypatch.setattr(call_lifecycle_service, "end", fake_end)

    async def on_wire(_wire: bytes) -> None:
        return None

    pcm24 = struct.pack("<" + "h" * 960, *([900] * 960))
    adapter = FakeRealtimeVoiceAdapter(
        events=[
            {"type": "user_transcript", "text": "Goodbye.", "final": True},
            {"type": "response_created"},
            {"type": "audio_delta", "pcm": pcm24},
            {
                "type": "function_call",
                "name": "end_call",
                "call_id": "fn1",
                "arguments": '{"should_end": true, "reason": "goodbye", "farewell": "Bye."}',
            },
            {
                "type": "response_done",
                "usage": {
                    "input_tokens": 8,
                    "output_tokens": 4,
                    "input_audio_tokens": 8,
                    "output_audio_tokens": 4,
                },
            },
        ]
    )
    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id=call_id,
        on_agent_wire=on_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice"},
    )
    await loop.start_call(play_greeting=False)
    user = struct.pack("<" + "h" * 320, *([500] * 320))
    await loop.feed_user_pcm16(user)
    import asyncio

    for _ in range(40):
        if seen.get("reason"):
            break
        await asyncio.sleep(0.05)
    assert seen.get("agent", 0) > 0
    assert seen.get("user", 0) > 0
    assert seen.get("reason") == "goodbye"
    await loop.close()
    get_settings.cache_clear()


def test_voice_adapter_drops_stale_audio_but_not_on_speech_started():
    import base64

    from server.realtime.providers.openai_voice import OpenAIRealtimeVoiceAdapter

    adapter = OpenAIRealtimeVoiceAdapter()
    adapter._accepting = True
    adapter._active_response_id = "resp-1"
    started = adapter._normalize({"type": "input_audio_buffer.speech_started"})
    assert started == {"type": "speech_started"}
    assert adapter._accepting is True

    pcm = b"\x00\x00" * 8
    delta = {
        "type": "response.output_audio.delta",
        "response_id": "resp-1",
        "delta": base64.b64encode(pcm).decode("ascii"),
    }
    accepted = adapter._normalize(delta)
    assert accepted is not None
    assert accepted["type"] == "audio_delta"
    adapter._accepting = False
    assert adapter._normalize(delta) is None


@pytest.mark.asyncio
async def test_voice_adapter_auto_response_toggle_preserves_full_session():
    from server.realtime.providers.openai_voice import OpenAIRealtimeVoiceAdapter

    class Conn:
        def __init__(self):
            self.sent = []

        async def send(self, event):
            self.sent.append(event)

    adapter = OpenAIRealtimeVoiceAdapter()
    adapter._conn = Conn()
    adapter._closed = False
    adapter.last_session = build_realtime_voice_session(
        model="gpt-realtime-2.1-mini",
        instructions="original",
        voice="marin",
        turn_detection="server_vad",
        silence_ms=325,
        speed=1.1,
        max_output_tokens=321,
    )
    before_output = dict(adapter.last_session["audio"]["output"])
    before_max_tokens = adapter.last_session["max_output_tokens"]
    await adapter.set_auto_response(False)
    assert adapter.last_session["audio"]["input"]["turn_detection"]["create_response"] is False
    assert adapter.last_session["audio"]["output"] == before_output
    assert adapter.last_session["max_output_tokens"] == before_max_tokens
    await adapter.update_instructions("updated")
    assert adapter.last_session["instructions"] == "updated"
    assert adapter.last_session["audio"]["input"]["turn_detection"]["create_response"] is False

    sent_before_clear = len(adapter._conn.sent)
    await adapter.clear_output_audio()
    assert len(adapter._conn.sent) == sent_before_clear


@pytest.mark.asyncio
async def test_start_call_outbound_natural_vad_no_forced_greeting():
    """Outbound: VAD on at lift — no start_response until callee speaks."""
    wires: list[bytes] = []

    async def on_wire(wire: bytes) -> None:
        wires.append(wire)

    adapter = FakeRealtimeVoiceAdapter()
    adapter.connected = True
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop
    from server.services.pstn_voice_core import PHASE_LISTENING

    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id="c-natural-outbound",
        on_agent_wire=on_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice", "direction": "outbound"},
    )
    await loop.start_call(
        play_greeting=True,
        greeting_wire_frames=[b"\x00" * 640],
        greeting_text="Hi, this is Priya. Do you have a moment?",
    )
    assert adapter.started_responses == []
    assert wires == []
    assert loop._phase == PHASE_LISTENING
    assert loop._deferred_greeting_armed is True
    assert len(loop._deferred_greeting_frames or []) == 1
    assert adapter.auto_response_states == [False]
    assert "FIRST TURN / IDENTITY (outbound" in adapter.instructions
    assert "Do NOT speak until the callee" in adapter.instructions
    await loop.close()


@pytest.mark.asyncio
async def test_deferred_greeting_waits_until_user_finishes():
    wires: list[bytes] = []

    async def on_wire(wire: bytes) -> None:
        wires.append(wire)

    adapter = FakeRealtimeVoiceAdapter()
    adapter.connected = True
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop
    from server.services.pstn_voice_core import PHASE_LISTENING

    frames = [b"\x01" * 640, b"\x02" * 640]
    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id="c-deferred",
        on_agent_wire=on_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice", "direction": "outbound"},
    )
    await loop.start_call(
        play_greeting=True,
        greeting_wire_frames=frames,
        greeting_text="Hi, this is Tis. Do you have a moment?",
    )
    assert wires == []
    assert adapter.auto_response_states == [False]
    loud = struct.pack("<320h", *([1200] * 320))
    for _ in range(15):
        await loop.feed_user_pcm16(loud)
    assert wires == []
    assert loop._deferred_greeting_task is None
    assert adapter.appended == []
    # High-eagerness VAD can fire this ~60ms into hello — 15 frames is real speech,
    # but playback still waits for the debounce after speech_stopped.
    await loop._handle_event({"type": "speech_started"})
    for _ in range(3):
        await loop.feed_user_pcm16(loud)
    await loop._handle_event({"type": "speech_stopped"})
    await asyncio.sleep(0.05)
    assert wires == []
    await asyncio.sleep(0.35)
    await asyncio.wait_for(loop._deferred_greeting_task, timeout=1.0)
    assert wires == frames
    assert adapter.noted_assistant == ["Hi, this is Tis. Do you have a moment?"]
    assert adapter.auto_response_states == [False, True]
    assert loop._intro_noted is True
    assert loop._phase == PHASE_LISTENING
    await loop.close()


@pytest.mark.asyncio
async def test_first_turn_speech_never_reaches_llm():
    adapter = FakeRealtimeVoiceAdapter()
    adapter.connected = True
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id="c-first-q",
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice", "direction": "outbound"},
    )
    await loop.start_call(
        play_greeting=True,
        greeting_wire_frames=[b"\x01" * 640],
        greeting_text="Hi, this is Tis. Do you have a moment?",
    )
    loud = struct.pack("<320h", *([1200] * 320))
    for _ in range(15):
        await loop.feed_user_pcm16(loud)
    assert adapter.appended == []
    await loop._handle_event(
        {"type": "user_transcript", "text": "Hello, who is this?", "final": True}
    )
    await loop._handle_event({"type": "speech_stopped"})
    await asyncio.sleep(0.35)
    await asyncio.wait_for(loop._deferred_greeting_task, timeout=1.0)
    assert adapter.auto_response_states[-1] is True
    assert adapter.started_responses == []
    assert adapter.cleared_input >= 1
    assert adapter.appended == []
    await loop.close()


@pytest.mark.asyncio
async def test_pickup_quiet_plays_greeting_without_sending_audio_to_llm():
    adapter = FakeRealtimeVoiceAdapter()
    adapter.connected = True
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    wires: list[bytes] = []

    async def on_wire(wire: bytes) -> None:
        wires.append(wire)

    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id="c-pickup-quiet",
        on_agent_wire=on_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice", "direction": "outbound"},
    )
    frames = [b"\x09" * 640]
    await loop.start_call(
        play_greeting=True,
        greeting_wire_frames=frames,
        greeting_text="Hi, this is Tis. Do you have a moment?",
    )
    loud = struct.pack("<320h", *([1200] * 320))
    quiet = struct.pack("<320h", *([0] * 320))
    for _ in range(15):
        await loop.feed_user_pcm16(loud)
    assert wires == []
    for _ in range(25):
        await loop.feed_user_pcm16(quiet)
    await asyncio.wait_for(loop._deferred_greeting_task, timeout=1.0)
    assert wires == frames
    assert adapter.appended == []
    assert adapter.started_responses == []
    assert adapter.auto_response_states[-1] is True
    await loop.close()


@pytest.mark.asyncio
async def test_deferred_greeting_ignores_early_speech_stopped():
    wires: list[bytes] = []

    async def on_wire(wire: bytes) -> None:
        wires.append(wire)

    adapter = FakeRealtimeVoiceAdapter()
    adapter.connected = True
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id="c-early-stop",
        on_agent_wire=on_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice", "direction": "outbound"},
    )
    await loop.start_call(
        play_greeting=True,
        greeting_wire_frames=[b"\x01" * 640],
        greeting_text="Hello there.",
    )
    await loop._handle_event({"type": "speech_stopped"})
    await asyncio.sleep(0.05)
    assert wires == []
    assert loop._deferred_greeting_task is None
    await loop.close()


@pytest.mark.asyncio
async def test_deferred_greeting_cancels_vad_response():
    adapter = FakeRealtimeVoiceAdapter()
    adapter.connected = True
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id="c-cancel-vad",
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice", "direction": "outbound"},
    )
    await loop.start_call(
        play_greeting=True,
        greeting_wire_frames=[b"\x00" * 640],
        greeting_text="Hello there.",
    )
    await loop._handle_event({"type": "response_created", "response_id": "r1"})
    assert adapter.cancelled >= 1
    await asyncio.sleep(0.05)
    assert loop._deferred_greeting_task is None
    loop.on_agent_wire.assert_not_awaited()
    await loop.close()


@pytest.mark.asyncio
async def test_no_deferred_greeting_when_frames_missing():
    wires: list[bytes] = []

    async def on_wire(wire: bytes) -> None:
        wires.append(wire)

    adapter = FakeRealtimeVoiceAdapter()
    adapter.connected = True
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id="c-no-frames",
        on_agent_wire=on_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice", "direction": "outbound"},
    )
    await loop.start_call(play_greeting=True, greeting_text="Hello.")
    assert loop._deferred_greeting_armed is False
    await loop._handle_event({"type": "speech_stopped"})
    await asyncio.sleep(0.05)
    assert wires == []
    await loop.close()


async def asyncio_wait_pump() -> None:
    import asyncio

    await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_simple_callback_hangup_is_accepted(monkeypatch, tmp_path):
    from server.call.call_ledger import call_ledger
    from server.call.memory_manager import memory_manager
    from server.config.env import get_settings
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    call_ledger.reset_for_tests()
    memory_manager.reset_for_tests()
    call_id = "c-callback-simple"
    await call_ledger.init(
        call_id,
        {"call_id": call_id, "pipeline": "realtime_voice", "caller_id": "+13526146416"},
    )
    memory_manager.init(call_id)

    async def on_wire(_wire: bytes) -> None:
        return None

    adapter = FakeRealtimeVoiceAdapter()
    remote_hangup = AsyncMock()
    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id=call_id,
        on_agent_wire=on_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice", "language": "en-IN"},
    )
    loop._adapter = adapter
    loop._on_remote_hangup = remote_hangup

    await loop._handle_event(
        {"type": "user_transcript", "text": "I am busy, please call me tomorrow.", "final": True}
    )
    await loop._handle_event({"type": "response_created"})
    await loop._handle_event(
        {
            "type": "function_call",
            "name": "end_call",
            "call_id": "fn-callback",
            "arguments": (
                '{"should_end": true, "reason": "goal_complete", '
                '"farewell": "Our team will call you tomorrow. Thank you. Goodbye."}'
            ),
        }
    )

    assert loop._pending_end_call is not None
    assert loop._callback_close_phase == "closing_allowed"
    assert loop._callback_collecting_field is None
    remote_hangup.assert_not_awaited()

    call_ledger.reset_for_tests()
    memory_manager.reset_for_tests()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_record_name_and_contact_tomorrow_collects_then_hangs_up(monkeypatch, tmp_path):
    from server.call.call_ledger import call_ledger
    from server.call.memory_manager import memory_manager
    from server.config.env import get_settings
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    call_ledger.reset_for_tests()
    memory_manager.reset_for_tests()
    call_id = "c-record-details"
    await call_ledger.init(
        call_id,
        {"call_id": call_id, "pipeline": "realtime_voice", "caller_id": "+13526146416"},
    )
    memory_manager.init(call_id)

    async def on_wire(_wire: bytes) -> None:
        return None

    adapter = FakeRealtimeVoiceAdapter()
    remote_hangup = AsyncMock()
    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id=call_id,
        on_agent_wire=on_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice", "language": "en-IN"},
    )
    loop._adapter = adapter
    loop._on_remote_hangup = remote_hangup

    phrase = "record my name and phone number and contact me tomorrow"
    await loop._handle_event({"type": "user_transcript", "text": phrase, "final": True})
    await loop._handle_event({"type": "response_created"})
    await loop._handle_event(
        {
            "type": "assistant_transcript",
            "text": "Great, we have several plot options near the highway.",
        }
    )
    await loop._handle_event({"type": "response_done"})

    assert loop._pending_end_call is None
    assert loop._callback_collecting_field == "name"
    assert any("May I have your name" in item for item in adapter.started_responses)
    remote_hangup.assert_not_awaited()

    await loop._handle_event({"type": "user_transcript", "text": "Subhash", "final": True})
    await loop._handle_event({"type": "response_created"})
    await loop._handle_event(
        {
            "type": "function_call",
            "name": "end_call",
            "call_id": "fn-too-soon",
            "arguments": (
                '{"should_end": true, "reason": "goal_complete", '
                '"farewell": "Thank you. Goodbye."}'
            ),
        }
    )
    await loop._handle_event({"type": "response_done"})
    assert loop._pending_end_call is None
    assert loop._callback_collecting_field == "phone"

    await loop._handle_event({"type": "user_transcript", "text": "8897908470", "final": True})
    await loop._handle_event({"type": "response_created"})
    await loop._handle_event(
        {
            "type": "function_call",
            "name": "end_call",
            "call_id": "fn-ready",
            "arguments": (
                '{"should_end": true, "reason": "goal_complete", '
                '"farewell": "Thank you. Goodbye."}'
            ),
        }
    )
    assert loop._pending_end_call is not None
    assert "tomorrow" in loop._pending_end_call["farewell"].lower()
    facts = memory_manager.get_snapshot(call_id)["facts"]
    assert facts["name"] == "Subhash"
    assert "8897908470" in str(facts["phone"])

    call_ledger.reset_for_tests()
    memory_manager.reset_for_tests()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_missed_end_call_after_handoff_hangs_up(monkeypatch, tmp_path):
    from server.call.call_ledger import call_ledger
    from server.call.memory_manager import memory_manager
    from server.config.env import get_settings
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    call_ledger.reset_for_tests()
    memory_manager.reset_for_tests()
    call_id = "c-missed-hangup"
    await call_ledger.init(
        call_id,
        {"call_id": call_id, "pipeline": "realtime_voice", "caller_id": "+13526146416"},
    )
    memory_manager.init(call_id)
    memory_manager.apply_proposals(
        call_id,
        [{"op": "set_fact", "key": "caller_name", "value": "Mohan"}],
        turn_seq=1,
        source="test",
    )

    adapter = FakeRealtimeVoiceAdapter()
    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id=call_id,
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice", "language": "en-IN"},
    )
    loop._adapter = adapter
    await call_ledger.append_assistant_turn(call_id, "Hi, this is Priya.")
    await call_ledger.append_assistant_turn(call_id, "Got it, your name is Mohan.")
    await loop._handle_event({"type": "user_transcript", "text": "Ja, danke.", "final": True})
    loop._assistant_text = "All set, thanks for confirming — we'll take it from here."
    await loop._maybe_hangup_missed_end_call()
    assert loop._pending_end_call is not None
    assert loop._pending_end_call["reason"] == "goal_complete"

    call_ledger.reset_for_tests()
    memory_manager.reset_for_tests()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_tool_only_farewell_finishes_before_provider_hangup(monkeypatch):
    monkeypatch.setattr("server.call.natural_hangup.HANGUP_TRAIL_SILENCE_SEC", 0.01)
    import struct

    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    async def on_wire(_wire: bytes) -> None:
        return None

    adapter = FakeRealtimeVoiceAdapter()
    remote_hangup = AsyncMock()
    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id=None,
        on_agent_wire=on_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice", "language": "en-IN"},
    )
    loop._adapter = adapter
    loop._on_remote_hangup = remote_hangup
    await loop._handle_event({"type": "user_transcript", "text": "Goodbye.", "final": True})
    await loop._handle_event({"type": "response_created"})
    await loop._handle_event(
        {
            "type": "function_call",
            "name": "end_call",
            "call_id": "fn-goodbye",
            "arguments": '{"should_end": true, "reason": "goodbye", "farewell": "Thank you. Goodbye."}',
        }
    )
    await loop._handle_event({"type": "response_done"})
    remote_hangup.assert_not_awaited()
    assert any("Speak this farewell exactly" in item for item in adapter.started_responses)

    await loop._handle_event({"type": "response_created"})
    pcm24 = struct.pack("<" + "h" * 960, *([500] * 960))
    await loop._handle_event({"type": "audio_delta", "pcm": pcm24})
    await loop._handle_event({"type": "response_done"})
    remote_hangup.assert_awaited_once()


@pytest.mark.asyncio
async def test_realtime_voice_persists_caller_details_from_normal_turn(monkeypatch, tmp_path):
    from server.call.call_ledger import call_ledger
    from server.call.memory_manager import memory_manager
    from server.config.env import get_settings
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    call_ledger.reset_for_tests()
    memory_manager.reset_for_tests()
    call_id = "c-realtime-caller-detail"
    await call_ledger.init(call_id, {"call_id": call_id})
    memory_manager.init(call_id)

    async def on_wire(_wire: bytes) -> None:
        return None

    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id=call_id,
        on_agent_wire=on_wire,
        adapter=FakeRealtimeVoiceAdapter(),
        stack_override={"pipeline": "realtime_voice", "language": "en-IN"},
    )
    await loop._handle_event(
        {
            "type": "user_transcript",
            "text": "My name is Subhash and my phone number is 9876543210.",
            "final": True,
        }
    )
    facts = memory_manager.get_snapshot(call_id)["facts"]
    assert facts["caller_name"] == "Subhash"
    assert facts["callback_phone"] == "9876543210"
    assert facts["phone"] == "9876543210"

    call_ledger.reset_for_tests()
    memory_manager.reset_for_tests()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_realtime_loop_loud_pcm_interrupts_without_waiting_for_vad():
    import struct

    barged: list[int] = []

    async def on_wire(_wire: bytes) -> None:
        return None

    async def on_barge() -> None:
        barged.append(1)

    adapter = FakeRealtimeVoiceAdapter()
    from server.services.pstn_realtime_voice_core import (
        REALTIME_AEC_LOUD_OPEN_FRAMES,
        PstnRealtimeVoiceLoop,
    )

    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id="c-barge-open",
        on_agent_wire=on_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice"},
    )
    loop.set_barge_handler(on_barge)
    await loop.start_call(play_greeting=False)
    loop._set_tts_active(True)
    loop.current_generation_id = "g-speak"
    loud = struct.pack("<" + "h" * 320, *([2200] * 320))
    for _ in range(REALTIME_AEC_LOUD_OPEN_FRAMES):
        await loop.feed_user_pcm16(loud)
    assert barged
    assert adapter.cancelled >= 1
    assert loop._aec_barge_open is True
    await loop.close()


@pytest.mark.asyncio
async def test_realtime_loop_drops_stacked_response_while_speaking():
    import struct

    adapter = FakeRealtimeVoiceAdapter()
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id=None,
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice"},
    )
    loop._adapter = adapter
    await loop._handle_event({"type": "response_created"})
    pcm24 = struct.pack("<" + "h" * 960, *([500] * 960))
    await loop._handle_event({"type": "audio_delta", "pcm": pcm24})
    gen = loop.current_generation_id
    cancelled = adapter.cancelled
    await loop._handle_event({"type": "response_created"})
    assert adapter.cancelled > cancelled
    assert loop.current_generation_id == gen


@pytest.mark.asyncio
async def test_realtime_loop_drops_auto_response_until_next_user_turn():
    import struct

    adapter = FakeRealtimeVoiceAdapter()
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id=None,
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice"},
    )
    loop._adapter = adapter
    await loop._handle_event({"type": "response_created"})
    pcm24 = struct.pack("<" + "h" * 960, *([500] * 960))
    await loop._handle_event({"type": "audio_delta", "pcm": pcm24})
    await loop._handle_event({"type": "assistant_transcript", "text": "I can help with that."})
    await loop._handle_event({"type": "response_done"})
    gen = loop.current_generation_id
    cancelled = adapter.cancelled
    await loop._handle_event({"type": "response_created"})
    assert adapter.cancelled > cancelled
    assert loop.current_generation_id == gen

    await loop._handle_event({"type": "user_transcript", "text": "What is the price?", "final": True})
    await loop._handle_event({"type": "response_created"})
    assert loop.current_generation_id != gen


@pytest.mark.asyncio
async def test_rejected_end_call_speaks_instead_of_silence():
    adapter = FakeRealtimeVoiceAdapter()
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id=None,
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice", "language": "en-IN"},
    )
    loop._adapter = adapter
    await loop._handle_event({"type": "user_transcript", "text": "I want two plants", "final": True})
    await loop._handle_event({"type": "response_created"})
    await loop._handle_event(
        {
            "type": "function_call",
            "name": "end_call",
            "call_id": "fn-rej",
            "arguments": '{"should_end": true, "reason": "goodbye", "farewell": ""}',
        }
    )
    assert loop._pending_end_call is None
    assert loop._pending_followup_instruction
    await loop._handle_event({"type": "response_done"})
    assert any("Stay on the line" in item for item in adapter.started_responses)


@pytest.mark.asyncio
async def test_availability_check_after_intro_does_not_regreet():
    adapter = FakeRealtimeVoiceAdapter()
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id=None,
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice"},
    )
    loop._adapter = adapter
    loop._intro_noted = True
    await loop._handle_event({"type": "user_transcript", "text": "Are you there?", "final": True})
    assert loop._user_partial == "Are you there?"
    assert any("still on the line" in item for item in adapter.started_responses)
    await loop._handle_event({"type": "user_transcript", "text": "Hallo", "final": True})
    assert loop._user_partial == "Hallo"
    assert sum("still on the line" in item for item in adapter.started_responses) >= 2
    await loop._handle_event({"type": "user_transcript", "text": "ഹലോ", "final": True})
    assert sum("still on the line" in item for item in adapter.started_responses) >= 3
    await loop._handle_event({"type": "user_transcript", "text": "Hi Priya", "final": True})
    assert sum("still on the line" in item for item in adapter.started_responses) >= 4


@pytest.mark.asyncio
async def test_overlap_junk_transcript_dropped_while_agent_speaks():
    adapter = FakeRealtimeVoiceAdapter()
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id=None,
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice"},
    )
    loop._adapter = adapter
    loop._set_tts_active(True)
    loop._assistant_text = "Hi, this is Priya calling from Auto Cars Private Limited. Do you have a moment?"
    await loop._handle_event({"type": "user_transcript", "text": "پاناکاشم", "final": True})
    assert loop._user_partial == ""
    await loop._handle_event(
        {
            "type": "user_transcript",
            "text": "Hi, this is Priya calling from Auto Cars Private Limited",
            "final": True,
        }
    )
    assert loop._user_partial == ""
    await loop._handle_event(
        {"type": "user_transcript", "text": "I'm looking for a car services.", "final": True}
    )
    assert loop._user_partial == "I'm looking for a car services."
    loop._aec_barge_open = True
    await loop._handle_event({"type": "user_transcript", "text": "why did you call me", "final": True})
    assert loop._user_partial == "why did you call me"
    loop._aec_barge_open = False
    await loop._handle_event(
        {"type": "user_transcript", "text": "Yeah, my friend, can you tell me why did you call me?", "final": True}
    )
    assert "why did you call me" in loop._user_partial


@pytest.mark.asyncio
async def test_outbound_first_hello_is_pickup_not_availability():
    adapter = FakeRealtimeVoiceAdapter()
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id=None,
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice", "direction": "outbound"},
    )
    loop._adapter = adapter
    loop._intro_noted = True
    await loop._handle_event({"type": "user_transcript", "text": "Hallo?", "final": True})
    assert loop._user_partial == "Hallo?"
    assert adapter.cancelled >= 1
    assert not any("still on the line" in item for item in adapter.started_responses)
    await loop._handle_event({"type": "user_transcript", "text": "Who is this?", "final": True})
    assert not any("still on the line" in item for item in adapter.started_responses)


@pytest.mark.asyncio
async def test_unclear_name_asks_repeat_instead_of_inventing_channel():
    adapter = FakeRealtimeVoiceAdapter()
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id=None,
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice"},
    )
    loop._adapter = adapter
    await loop._handle_event(
        {"type": "user_transcript", "text": "Hi, my name is the recording.", "final": True}
    )
    assert any("repeat their name" in item for item in adapter.started_responses)
    assert any("messaging app" in item for item in adapter.started_responses)


@pytest.mark.asyncio
async def test_realtime_hangup_skips_when_caller_is_talking():
    adapter = FakeRealtimeVoiceAdapter()
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    remote_hangup = AsyncMock()
    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id=None,
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice"},
    )
    loop._adapter = adapter
    loop._on_remote_hangup = remote_hangup
    loop._pending_end_call = {"reason": "goal_complete", "farewell": "Goodbye."}
    loop._aec_barge_open = True
    await loop._finish_hangup()
    remote_hangup.assert_not_awaited()
    assert loop._hangup_started is False


@pytest.mark.asyncio
async def test_realtime_hangup_aborts_when_caller_barges_farewell(monkeypatch):
    monkeypatch.setattr("server.call.natural_hangup.HANGUP_TRAIL_SILENCE_SEC", 0.01)
    adapter = FakeRealtimeVoiceAdapter()
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    playing = {"on": True}

    class Playback:
        def is_active(self):
            return playing["on"]

        def clear(self):
            playing["on"] = False

        def invalidate_generation(self, _gen):
            playing["on"] = False

    remote_hangup = AsyncMock()
    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id=None,
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice"},
    )
    loop._adapter = adapter
    loop.playback = Playback()
    loop._on_remote_hangup = remote_hangup
    loop._pending_end_call = {"reason": "goal_complete", "farewell": "Goodbye."}
    loop._response_had_audio = True
    loop._farewell_response_active = True

    async def barge_soon():
        await asyncio.sleep(0.05)
        loop._aec_barge_open = True
        await loop._commit_local_barge()

    asyncio.create_task(barge_soon())
    await loop._finish_hangup()
    remote_hangup.assert_not_awaited()
    assert loop._hangup_started is False
    assert loop._pending_end_call is None


def test_availability_matcher_covers_indic_and_who_is_this():
    from server.services.pstn_realtime_voice_core import (
        _is_availability_check,
        _is_line_check,
        _is_pickup_phrase,
        _is_simple_hello,
    )

    assert _is_simple_hello("ഹലോ")
    assert _is_simple_hello("Hello")
    assert not _is_availability_check("Hello, who is this?")
    assert _is_availability_check("Hi Priya")
    assert _is_availability_check("Are you there?")
    assert _is_line_check("are you there")
    assert not _is_pickup_phrase("Hello, who is this?")
    assert _is_pickup_phrase("Hello")
    assert not _is_availability_check("I needed a service for my car")


@pytest.mark.asyncio
async def test_deferred_greeting_is_not_cut_by_hello_barge():
    import struct

    barged: list[int] = []

    async def on_wire(_wire: bytes) -> None:
        return None

    async def on_barge() -> None:
        barged.append(1)

    adapter = FakeRealtimeVoiceAdapter()
    from server.services.pstn_realtime_voice_core import (
        REALTIME_AEC_LOUD_OPEN_FRAMES,
        PstnRealtimeVoiceLoop,
    )

    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id="c-greet-barge",
        on_agent_wire=on_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice", "direction": "outbound"},
    )
    loop.set_barge_handler(on_barge)
    await loop.start_call(
        play_greeting=True,
        greeting_wire_frames=[b"\x00" * 640],
        greeting_text="Hi, this is Priya. Do you have a moment?",
    )
    loop._deferred_greeting_playing = True
    loop._set_tts_active(True)
    loud = struct.pack("<" + "h" * 320, *([2200] * 320))
    for _ in range(REALTIME_AEC_LOUD_OPEN_FRAMES + 2):
        await loop.feed_user_pcm16(loud)
    assert barged == []
    assert adapter.appended == []
    await loop.close()


@pytest.mark.asyncio
async def test_pickup_hello_cancels_leftover_vad_after_greeting():
    adapter = FakeRealtimeVoiceAdapter()
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id=None,
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice", "direction": "outbound"},
    )
    loop._adapter = adapter
    loop._intro_noted = True
    loop._pickup_suppress_until = 10**12
    await loop._handle_event({"type": "response_created", "response_id": "r-hello"})
    assert adapter.cancelled >= 1
    assert loop._response_open is False


@pytest.mark.asyncio
async def test_hangup_abort_clears_agent_hangup_armed():
    from datetime import datetime, timezone

    from server.call.call_context import CallContext, clear_all, get as get_ctx, put
    from server.providers.base import ResolvedStack, StageSelection

    clear_all()
    call_id = "c-hangup-abort"
    put(
        CallContext(
            call_id=call_id,
            tenant_id="t",
            agent_id="a",
            session_id="s",
            channel="pstn",
            direction="outbound",
            environment="development",
            tier="medium",
            resolved_stack=ResolvedStack(
                combination_id="x",
                tier="medium",
                mode="frontend",
                stt=StageSelection("sarvam", "saaras:v3-realtime", {}),
                llm=StageSelection("openai", "gpt-realtime-2.1-mini", {}),
                tts=StageSelection("sarvam", "bulbul:v3", {}),
                language="en-IN",
            ),
            compiled_brain_version="v",
            compiled_brain_text="brain",
            started_at=datetime.now(timezone.utc),
            storage_path=f"data/calls/{call_id}/",
        )
    )
    ctx = get_ctx(call_id)
    assert ctx is not None
    ctx.agent_hangup_armed = True
    adapter = FakeRealtimeVoiceAdapter()
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id=call_id,
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice"},
    )
    loop._adapter = adapter
    loop._hangup_started = True
    loop._pending_end_call = {"reason": "goal_complete"}
    loop._farewell_response_active = True
    await loop._commit_local_barge()
    assert get_ctx(call_id).agent_hangup_armed is False
    assert loop._hangup_started is False
    assert loop._pending_end_call is None
    clear_all()


@pytest.mark.asyncio
async def test_pickup_hangover_keeps_speech_across_short_dips():
    wires: list[bytes] = []

    async def on_wire(wire: bytes) -> None:
        wires.append(wire)

    adapter = FakeRealtimeVoiceAdapter()
    adapter.connected = True
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id="c-pickup-dip",
        on_agent_wire=on_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice", "direction": "outbound"},
    )
    frames = [b"\x03" * 640]
    await loop.start_call(
        play_greeting=True,
        greeting_wire_frames=frames,
        greeting_text="Hi, this is Tis. Do you have a moment?",
    )
    loud = struct.pack("<320h", *([1200] * 320))
    quiet = struct.pack("<320h", *([0] * 320))
    for _ in range(8):
        await loop.feed_user_pcm16(loud)
    for _ in range(3):
        await loop.feed_user_pcm16(quiet)
    for _ in range(8):
        await loop.feed_user_pcm16(loud)
    assert wires == []
    for _ in range(12):
        await loop.feed_user_pcm16(quiet)
    await asyncio.wait_for(loop._deferred_greeting_task, timeout=1.0)
    assert wires == frames
    assert adapter.appended == []
    await loop.close()


@pytest.mark.asyncio
async def test_pickup_fallback_plays_greeting_if_callee_stays_quiet():
    wires: list[bytes] = []

    async def on_wire(wire: bytes) -> None:
        wires.append(wire)

    adapter = FakeRealtimeVoiceAdapter()
    adapter.connected = True
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id="c-pickup-fallback",
        on_agent_wire=on_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice", "direction": "outbound"},
    )
    frames = [b"\x04" * 640]
    await loop.start_call(
        play_greeting=True,
        greeting_wire_frames=frames,
        greeting_text="Hi, this is Tis. Do you have a moment?",
    )
    await asyncio.sleep(0.95)
    await asyncio.wait_for(loop._deferred_greeting_task, timeout=1.0)
    assert wires == frames
    await loop.close()


@pytest.mark.asyncio
async def test_inbound_pcm_is_buffered_until_adapter_ready():
    adapter = FakeRealtimeVoiceAdapter()
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id="c-hold-in",
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice"},
    )
    loud = struct.pack("<320h", *([1800] * 320))
    await loop.feed_user_pcm16(loud)
    assert adapter.appended == []
    assert loop._pending_inbound
    await loop.start_call(play_greeting=False)
    assert adapter.appended
    assert loop._pending_inbound == []
    await loop.close()


@pytest.mark.asyncio
async def test_start_call_keeps_prewarm_instructions():
    adapter = FakeRealtimeVoiceAdapter()
    adapter.connected = True
    adapter.instructions = "prewarmed brain instructions"
    adapter.last_session = {"instructions": "prewarmed brain instructions"}
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id="c-keep-prewarm",
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice", "direction": "outbound"},
    )
    await loop.start_call(
        play_greeting=True,
        greeting_wire_frames=[b"\x00" * 640],
        greeting_text="Hi, this is Priya. Do you have a moment?",
    )
    assert adapter.instruction_updates == 0
    assert adapter.instructions == "prewarmed brain instructions"
    assert adapter.auto_response_states == [False]
    assert loop._deferred_greeting_armed is True
    await loop.close()


@pytest.mark.asyncio
async def test_greeting_protect_drops_inbound_after_dump():
    import time

    adapter = FakeRealtimeVoiceAdapter()
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id="c-greet-protect",
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice"},
    )
    await loop.start_call(play_greeting=False)
    loop._greeting_protect_until = time.monotonic() + 2.0
    loud = struct.pack("<320h", *([2200] * 320))
    await loop.feed_user_pcm16(loud)
    assert adapter.appended == []
    await loop.close()

