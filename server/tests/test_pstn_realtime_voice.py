"""Realtime audio PSTN path — factory, stack, session payload, costing (no live WS)."""
from __future__ import annotations

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
    loud = struct.pack("<" + "h" * 320, *([8000] * 320))
    for _ in range(REALTIME_AEC_LOUD_OPEN_FRAMES):
        await loop.feed_user_pcm16(loud)
    assert adapter.appended, "loud barge should reach OpenAI after hysteresis"
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

    await asyncio.sleep(0.15)
    assert seen.get("agent", 0) > 0
    assert seen.get("user", 0) > 0
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
    assert "FIRST TURN / IDENTITY (outbound" in adapter.instructions
    assert "Do NOT speak until the callee" in adapter.instructions
    await loop.close()


async def asyncio_wait_pump() -> None:
    import asyncio

    await asyncio.sleep(0.05)
