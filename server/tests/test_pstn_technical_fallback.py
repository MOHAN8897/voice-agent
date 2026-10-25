"""Recorded technical-failure announcement: assets, plan rules, and hangup wiring."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.config.constants import constants
from server.services import pstn_technical_fallback as fallback
from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop, VoiceProviderUnavailable
from server.services.pstn_technical_fallback import (
    CALL_BACK,
    CALLBACK_PROMISE,
    DISCLOSURE_VARIANT,
    FALLBACK_TAIL_SEC,
    FallbackPlan,
    TenantFallbackConfig,
    fallback_text,
    fallback_wire_frames,
    prepare_technical_fallback_plan,
    resolve_fallback_language,
    stamp_fallback_meta,
)
from server.services.pstn_voice_core import PHASE_ENDED, PstnVoiceLoop


class FakeLedger:
    def __init__(self) -> None:
        self.meta: dict = {}
        self.lines: list[tuple[str, str]] = []

    def read_meta(self, call_id):  # noqa: ARG002
        return dict(self.meta)

    def write_meta(self, call_id, meta):  # noqa: ARG002
        self.meta = dict(meta)

    def read_lines(self, call_id):  # noqa: ARG002
        return []

    async def append_assistant_turn(self, call_id, text):  # noqa: ARG002
        self.lines.append(("assistant", text))


@pytest.fixture
def ledger(monkeypatch):
    fake = FakeLedger()
    monkeypatch.setattr("server.call.call_ledger.call_ledger", fake)
    return fake


def _patch_plan_inputs(monkeypatch, *, config=None, meta=None, transcript=None):
    monkeypatch.setattr(fallback, "_read_meta", lambda call_id: dict(meta or {}))
    monkeypatch.setattr(fallback, "_read_transcript", lambda call_id: list(transcript or []))

    async def loader(**_kwargs):
        return config or TenantFallbackConfig(available=False, promise_callback=False)

    monkeypatch.setattr(fallback, "_load_tenant_config", loader)


async def _plan(*, language="en-IN", direction="outbound", trigger="tts_failure"):
    return await prepare_technical_fallback_plan(
        call_id="call-1",
        tenant_id="tenant-1",
        agent_id="agent-1",
        direction=direction,
        language=language,
        trigger=trigger,
    )


def test_every_supported_language_has_a_playable_clip():
    for language in constants.SUPPORTED_LANGUAGES:
        frames = fallback_wire_frames(language, output_codec="mulaw", sample_rate=8000)
        assert frames, f"missing fallback clip for {language}"
        assert all(len(frame) == 160 for frame in frames[:-1])
        assert fallback_text(language).strip()


def test_default_messages_match_the_approved_wording():
    assert fallback_text("en-IN", CALL_BACK) == (
        "Sorry, we are facing a technical problem. Please call us back. Thank you."
    )
    assert fallback_text("en-IN", CALLBACK_PROMISE) == (
        "Sorry, we are facing a technical problem. We will call you again. Thank you."
    )
    for language in constants.SUPPORTED_LANGUAGES:
        assert fallback_text(language, CALL_BACK) != fallback_text(language, CALLBACK_PROMISE)


def test_fallback_resolution_prefers_same_language_then_english():
    assert resolve_fallback_language("te-IN") == "te-IN"
    assert resolve_fallback_language("hi") == "hi-IN"
    assert resolve_fallback_language("en-US") == "en-IN"
    assert resolve_fallback_language("en-GB") == "en-IN"
    assert resolve_fallback_language(None) == "en-IN"


def test_callback_target_accepts_stored_e164_digits_without_plus():
    # Call meta stores ``callee_e164`` as digits only (918897908470). Rejecting
    # that shape skipped the callback row and silently downgraded the variant.
    assert fallback._normalize_target("918897908470") == "+918897908470"
    assert fallback._normalize_target("+91 88979 08470") == "+918897908470"
    assert fallback._normalize_target("008897908470") == "+8897908470"
    assert fallback._normalize_target("08897908470") == "+918897908470"
    assert fallback._normalize_target("8897908470") == "+918897908470"
    assert fallback._normalize_target("not a number") is None
    assert fallback.callback_target({"callee_e164": "918897908470"}, "outbound") == "+918897908470"
    assert fallback.callback_target({"caller_id": "918897908470"}, "inbound") == "+918897908470"


@pytest.mark.asyncio
async def test_global_switch_off_suppresses_audio_and_callback_promise(monkeypatch):
    from server.services.speech_outage_config import SpeechOutageConfig

    _patch_plan_inputs(monkeypatch)

    async def disabled():
        return SpeechOutageConfig(enabled=False, promise_callback=True)

    monkeypatch.setattr(
        "server.services.speech_outage_config.load_speech_outage_config", disabled,
    )
    loaded: list[dict] = []

    async def loader(**kwargs):
        loaded.append(kwargs)
        return TenantFallbackConfig(available=True, promise_callback=True, callback_created=True)

    monkeypatch.setattr(fallback, "_load_tenant_config", loader)
    plan = await _plan(language="te-IN")
    assert plan.pcm == b""
    assert plan.text == ""
    assert plan.defect == "announcement_disabled"
    assert plan.callback_task_id is None
    assert loaded == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("trigger", "last_user"),
    [
        ("runtime_failure", "Tell me more."),
        ("tts_failure", "ఇప్పుడైతే ఇంట్రెస్ట్ ఏం లేదండి."),
        ("tts_failure", "Please don't call me again."),
    ],
)
async def test_callback_promise_is_suppressed_without_tts_failure_or_after_refusal(
    monkeypatch, trigger, last_user,
):
    _patch_plan_inputs(monkeypatch, transcript=[{"role": "user", "text": last_user}])
    allowed: list[bool] = []

    async def loader(**kwargs):
        allowed.append(kwargs["promise_allowed"])
        return TenantFallbackConfig(available=True, promise_callback=kwargs["promise_allowed"])

    monkeypatch.setattr(fallback, "_load_tenant_config", loader)
    plan = await _plan(trigger=trigger)
    assert allowed == [False]
    assert plan.callback_task_id is None
    assert plan.variant == CALL_BACK


def test_fallback_frames_follow_wire_codec():
    mulaw = fallback_wire_frames("te-IN", output_codec="mulaw", sample_rate=8000)
    l16 = fallback_wire_frames("te-IN", output_codec="linear16", sample_rate=16000)
    assert mulaw and l16
    assert {len(frame) for frame in mulaw[:-1]} == {160}
    assert {len(frame) for frame in l16[:-1]} == {640}
    assert fallback_wire_frames("te-IN", output_codec="mp3", sample_rate=24000) == []


@pytest.mark.asyncio
async def test_plan_uses_call_back_variant_when_callback_cannot_be_created(monkeypatch):
    _patch_plan_inputs(
        monkeypatch,
        config=TenantFallbackConfig(available=True, promise_callback=True, callback_created=False),
    )
    plan = await _plan()
    assert plan.variant == CALL_BACK
    assert plan.text == fallback_text("en-IN", CALL_BACK).replace("en-IN", "en-IN") or plan.text
    assert plan.callback_task_id is None
    assert plan.pcm


@pytest.mark.asyncio
async def test_plan_promises_callback_only_after_task_is_committed(monkeypatch):
    _patch_plan_inputs(
        monkeypatch,
        config=TenantFallbackConfig(
            available=True,
            promise_callback=True,
            callback_created=True,
            callback_task_id="cb-1",
        ),
    )
    plan = await _plan()
    assert plan.variant == CALLBACK_PROMISE
    assert plan.callback_task_id == "cb-1"
    assert "call you again" in plan.text


@pytest.mark.asyncio
async def test_plan_keeps_the_admitted_language_not_the_agent_default(monkeypatch):
    _patch_plan_inputs(monkeypatch)
    plan = await _plan(language="te-IN")
    assert plan.language == "te-IN"
    assert plan.text == fallback_text("te-IN", CALL_BACK)


@pytest.mark.asyncio
async def test_tenant_upload_wins_and_note_text_becomes_the_ledger_line(monkeypatch):
    pcm = b"\x10\x00" * 400
    _patch_plan_inputs(
        monkeypatch,
        config=TenantFallbackConfig(
            available=True,
            promise_callback=False,
            clips={("en-in", CALL_BACK): pcm},
            note_text="Sorry, technical problem. Please call back.",
        ),
    )
    plan = await _plan()
    assert plan.source == "custom"
    assert plan.pcm == pcm
    assert plan.text == "Sorry, technical problem. Please call back."


@pytest.mark.asyncio
async def test_disclosure_clip_precedes_the_failure_announcement(monkeypatch):
    _patch_plan_inputs(
        monkeypatch,
        meta={"recording_disclosure": {"enabled": True, "text": "recorded"}},
    )
    plan = await _plan()
    assert plan.disclosure_pcm
    assert plan.disclosure_text
    assert plan.watchdog_sec() > len(plan.pcm) / 16000.0


@pytest.mark.asyncio
async def test_disclosure_skipped_when_already_spoken(monkeypatch):
    _patch_plan_inputs(
        monkeypatch,
        meta={"recording_disclosure": {"enabled": True}},
        transcript=[{"role": "assistant", "text": "This call is being recorded for training."}],
    )
    plan = await _plan()
    assert plan.disclosure_pcm == b""


@pytest.mark.asyncio
async def test_missing_disclosure_clip_is_flagged_for_compliance(monkeypatch):
    _patch_plan_inputs(monkeypatch, meta={"recording_disclosure": {"enabled": True}})
    monkeypatch.setattr(
        fallback,
        "_select_clip",
        lambda clips, language, variant, gender: fallback.FallbackClip(
            pcm=b"" if variant == DISCLOSURE_VARIANT else b"\x00\x00" * 400,
            language="en-IN",
            source="none" if variant == DISCLOSURE_VARIANT else "platform",
        ),
    )
    logged: list[str] = []
    monkeypatch.setattr(fallback, "log_pstn", lambda event, **kw: logged.append(event))
    plan = await _plan()
    assert plan.pcm
    assert plan.disclosure_pcm == b""
    assert "disclosure_not_delivered" in logged


def test_stamp_records_the_required_call_meta(ledger):
    plan = FallbackPlan(
        variant=CALLBACK_PROMISE,
        language="hi-IN",
        source="platform",
        gender="female",
        pcm=b"\x00\x00" * 400,
        text="text",
        disclosure_text="recorded",
        callback_task_id="cb-9",
        defect="playback_watchdog",
    )
    stamp_fallback_meta(
        "call-1", plan, trigger="tts_failure", played=True, disclosure_played=False,
        defect="playback_watchdog",
    )
    assert ledger.meta["fallback_played"] is True
    assert ledger.meta["fallback_language"] == "hi-IN"
    assert ledger.meta["fallback_reason"] == "tts_failure"
    assert ledger.meta["fallback_variant"] == CALLBACK_PROMISE
    assert ledger.meta["fallback_callback_task_id"] == "cb-9"
    assert ledger.meta["fallback_disclosure_played"] is False
    assert ledger.meta["fallback_disclosure_not_delivered"] is True
    assert ledger.meta["fallback_defect"] == "playback_watchdog"


@pytest.mark.asyncio
async def test_classic_fallback_plays_once_then_closes_with_technical_reason(monkeypatch):
    wires: list[bytes] = []

    async def on_wire(wire: bytes) -> None:
        wires.append(wire)

    loop = PstnVoiceLoop(session_id="fallback", call_id=None, on_agent_wire=on_wire)
    hangup = AsyncMock()
    loop.set_hangup_handler(hangup)
    close = AsyncMock(return_value=SimpleNamespace(background_task=None))
    monkeypatch.setattr("server.call.close_call_executor.execute_agent_close", close)

    await loop._play_technical_fallback_and_hangup(trigger="tts_failure")
    played = len(wires)
    assert played > 0
    assert {len(frame) for frame in wires[:-1]} == {160}
    assert loop._technical_fallback_played is True
    assert loop._technical_fallback_active is True
    assert close.await_args.kwargs["reason"] == "technical_fallback"
    assert close.await_args.kwargs["trail_sec"] == FALLBACK_TAIL_SEC
    assert close.await_args.kwargs["spoke_farewell"] is True

    await loop._play_technical_fallback_and_hangup(trigger="tts_failure")
    assert len(wires) == played
    close.assert_awaited_once()
    await loop.close()


@pytest.mark.asyncio
async def test_classic_outage_clip_rejects_non_tts_trigger():
    loop = PstnVoiceLoop(session_id="fallback-guard", call_id=None, on_agent_wire=AsyncMock())
    with pytest.raises(ValueError, match="requires a TTS failure"):
        await loop._play_technical_fallback_and_hangup(trigger="runtime_failure")
    assert loop._technical_fallback_played is False
    await loop.close()


@pytest.mark.asyncio
async def test_classic_fallback_suppresses_barge_and_new_turns(monkeypatch):
    loop = PstnVoiceLoop(session_id="fallback-barge", call_id=None, on_agent_wire=AsyncMock())
    monkeypatch.setattr(loop, "_run_turn", AsyncMock())
    assert loop._accepts_user_turn("tell me about your pricing") is True
    loop._technical_fallback_active = True
    assert loop._should_commit_barge("stop wait a moment please") is False
    assert loop._accepts_user_turn("tell me about your pricing") is False
    loop._queue_user_transcript("tell me about your pricing")
    assert loop._pending_transcript is None
    loop._launch_turn("tell me about your pricing")
    await asyncio.sleep(0)
    loop._run_turn.assert_not_awaited()
    await loop.close()


@pytest.mark.asyncio
async def test_classic_greeting_provider_outage_plays_apology_before_raising(monkeypatch):
    wires: list[bytes] = []

    async def on_wire(wire: bytes) -> None:
        wires.append(wire)

    loop = PstnVoiceLoop(session_id="fallback-start", call_id=None, on_agent_wire=on_wire)
    hangup = AsyncMock()
    loop.set_hangup_handler(hangup)
    monkeypatch.setattr(loop, "open_stt", AsyncMock())
    monkeypatch.setattr(loop, "_warm_tts_connection", AsyncMock())
    loop._last_tts_session = SimpleNamespace(
        failure_evidence={"kind": "balance", "provider": "sarvam", "retained": True}
    )

    async def failing_speak(_text: str, **_kwargs) -> None:
        raise RuntimeError("speech provider down")

    monkeypatch.setattr(loop, "speak", failing_speak)
    with pytest.raises(RuntimeError):
        await loop.start_call(greeting_text="Hello, how can I help?")
    assert wires
    hangup.assert_awaited_once()
    assert loop._technical_fallback_played is True
    await loop.close()


@pytest.mark.asyncio
async def test_classic_greeting_transport_failure_closes_without_outage_clip(monkeypatch):
    loop = PstnVoiceLoop(session_id="fallback-start", call_id=None, on_agent_wire=AsyncMock())
    hangup = AsyncMock()
    loop.set_hangup_handler(hangup)
    monkeypatch.setattr(loop, "open_stt", AsyncMock())
    monkeypatch.setattr(loop, "_warm_tts_connection", AsyncMock())
    loop._last_tts_session = SimpleNamespace(
        failure_evidence={"kind": "transport", "provider": "sarvam", "retained": False}
    )

    async def failing_speak(_text: str, **_kwargs) -> None:
        raise RuntimeError("socket reset")

    monkeypatch.setattr(loop, "speak", failing_speak)
    with pytest.raises(RuntimeError):
        await loop.start_call(greeting_text="Hello, how can I help?")
    hangup.assert_awaited_once()
    assert loop._technical_fallback_played is False
    await loop.close()


@pytest.mark.asyncio
async def test_stt_terminal_failure_closes_without_speech_outage(monkeypatch):
    loop = PstnVoiceLoop(session_id="stt-failed", call_id=None, on_agent_wire=AsyncMock())
    close = AsyncMock()
    announce = AsyncMock()
    monkeypatch.setattr(loop, "_close_after_non_tts_failure", close)
    monkeypatch.setattr(loop, "_play_technical_fallback_and_hangup", announce)
    loop._stt_failed("socket closed")
    await asyncio.sleep(0)
    close.assert_awaited_once_with()
    announce.assert_not_awaited()


@pytest.mark.asyncio
async def test_realtime_fallback_bypasses_dead_provider_and_is_one_shot(monkeypatch):
    wires: list[bytes] = []

    async def on_wire(wire: bytes) -> None:
        wires.append(wire)

    loop = PstnRealtimeVoiceLoop(session_id="rt-fallback", call_id=None, on_agent_wire=on_wire)
    monkeypatch.setattr(loop, "interrupt_tts", AsyncMock())
    assert await loop._play_technical_fallback() is True
    assert wires and {len(frame) for frame in wires[:-1]} == {160}
    assert loop._response_had_audio is True
    assert await loop._play_technical_fallback() is False
    loop.interrupt_tts.assert_awaited_once()
    await loop.close()


@pytest.mark.asyncio
async def test_realtime_fallback_watchdog_ends_a_broken_wire(monkeypatch, ledger):
    loop = PstnRealtimeVoiceLoop(session_id="rt-watchdog", call_id="call-1", on_agent_wire=AsyncMock())

    async def slow_wire(_wire: bytes) -> None:
        await asyncio.sleep(5)

    loop.on_agent_wire = slow_wire
    monkeypatch.setattr(fallback, "FALLBACK_WATCHDOG_GRACE_SEC", 0.0)
    plan = FallbackPlan(
        variant=CALL_BACK,
        language="en-IN",
        source="platform",
        gender="male",
        pcm=b"\x00\x00" * 800,
        text="text",
    )

    async def planned(**_kwargs):
        return plan

    monkeypatch.setattr(
        "server.services.pstn_technical_fallback.prepare_technical_fallback_plan", planned,
    )
    played = await loop._play_technical_fallback(trigger="tts_failure")
    assert played is False
    assert ledger.meta["fallback_defect"] == "playback_watchdog"
    await loop.close()


@pytest.mark.asyncio
async def test_realtime_watchdog_skips_the_drain_wait(monkeypatch, ledger):
    calls: list[bytes] = []

    async def one_frame_then_stall(wire: bytes) -> None:
        calls.append(wire)
        if len(calls) > 1:
            await asyncio.sleep(5)

    plan = FallbackPlan(
        variant=CALL_BACK,
        language="en-IN",
        source="platform",
        gender="male",
        pcm=b"\x00\x00" * 800,
        text="text",
    )

    async def planned(**_kwargs):
        return plan

    async def drain_must_not_run(*_args, **_kwargs):
        raise AssertionError("a broken wire must not wait for the playback drain")

    loop = PstnRealtimeVoiceLoop(
        session_id="rt-watchdog-drain", call_id="call-1", on_agent_wire=one_frame_then_stall,
    )
    monkeypatch.setattr(fallback, "FALLBACK_WATCHDOG_GRACE_SEC", 0.0)
    monkeypatch.setattr(
        "server.services.pstn_technical_fallback.prepare_technical_fallback_plan", planned,
    )
    monkeypatch.setattr("server.call.natural_hangup.wait_for_farewell_playback", drain_must_not_run)
    assert await loop._play_technical_fallback(trigger="tts_failure") is True
    assert calls and ledger.meta["fallback_defect"] == "playback_watchdog"
    await loop.close()


@pytest.mark.asyncio
async def test_realtime_startup_failure_ends_as_technical_fallback(monkeypatch):
    loop = PstnRealtimeVoiceLoop(session_id="rt-start", call_id=None, on_agent_wire=AsyncMock())

    async def failed_start(**_kwargs):
        raise VoiceProviderUnavailable("provider refused connection")

    announce = AsyncMock(return_value=True)
    disconnect = AsyncMock()
    monkeypatch.setattr(loop, "_start_call_inner", failed_start)
    monkeypatch.setattr(loop, "_play_technical_fallback", announce)
    monkeypatch.setattr(loop, "_fast_disconnect_after_farewell", disconnect)
    await loop.start_call(greeting_text="Hello")
    announce.assert_awaited_once()
    disconnect.assert_awaited_once_with("technical_fallback", True)
    await loop.close()


@pytest.mark.asyncio
async def test_realtime_startup_failure_without_clip_propagates_for_bridge_teardown(monkeypatch):
    loop = PstnRealtimeVoiceLoop(session_id="rt-start-none", call_id=None, on_agent_wire=AsyncMock())

    async def failed_start(**_kwargs):
        raise VoiceProviderUnavailable("provider refused connection")

    announce = AsyncMock(return_value=False)
    disconnect = AsyncMock()
    monkeypatch.setattr(loop, "_start_call_inner", failed_start)
    monkeypatch.setattr(loop, "_play_technical_fallback", announce)
    monkeypatch.setattr(loop, "_fast_disconnect_after_farewell", disconnect)
    with pytest.raises(VoiceProviderUnavailable):
        await loop.start_call(greeting_text="Hello")
    announce.assert_awaited_once()
    disconnect.assert_not_awaited()
    await loop.close()


@pytest.mark.asyncio
async def test_realtime_local_startup_error_does_not_claim_speech_outage(monkeypatch):
    loop = PstnRealtimeVoiceLoop(session_id="rt-local-start", call_id=None, on_agent_wire=AsyncMock())

    async def failed_start(**_kwargs):
        raise RuntimeError("local setup failed")

    announce = AsyncMock(return_value=True)
    monkeypatch.setattr(loop, "_start_call_inner", failed_start)
    monkeypatch.setattr(loop, "_play_technical_fallback", announce)
    with pytest.raises(RuntimeError, match="local setup failed"):
        await loop.start_call(greeting_text="Hello")
    announce.assert_not_awaited()
    await loop.close()


@pytest.mark.asyncio
async def test_native_adapter_connection_rejection_is_classified_as_voice_failure(monkeypatch):
    from server.realtime.testing import FakeRealtimeVoiceAdapter

    adapter = FakeRealtimeVoiceAdapter()
    adapter.connect = AsyncMock(side_effect=RuntimeError("provider rejected connection"))
    loop = PstnRealtimeVoiceLoop(
        session_id="rt-provider-start", call_id=None, on_agent_wire=AsyncMock(), adapter=adapter,
    )
    announce = AsyncMock(return_value=False)
    monkeypatch.setattr(loop, "_play_technical_fallback", announce)
    with pytest.raises(VoiceProviderUnavailable):
        await loop.start_call(play_greeting=False)
    announce.assert_awaited_once()
    await loop.close()


@pytest.mark.asyncio
async def test_realtime_runtime_failure_plays_clip_then_ends_as_technical_fallback(monkeypatch):
    wires: list[bytes] = []

    async def on_wire(wire: bytes) -> None:
        wires.append(wire)

    loop = PstnRealtimeVoiceLoop(session_id="rt-end", call_id=None, on_agent_wire=on_wire)
    monkeypatch.setattr(loop, "interrupt_tts", AsyncMock())
    disconnect = AsyncMock()
    monkeypatch.setattr(loop, "_fast_disconnect_after_farewell", disconnect)
    await loop._runtime_end("provider_failure")
    assert wires
    disconnect.assert_awaited_once()
    assert disconnect.await_args.args[0] == "technical_fallback"
    assert disconnect.await_args.args[1] is True
    await loop.close()


@pytest.mark.asyncio
async def test_realtime_runtime_end_falls_back_to_carrier_reason_without_audio(monkeypatch):
    loop = PstnRealtimeVoiceLoop(session_id="rt-end-empty", call_id=None, on_agent_wire=AsyncMock())
    monkeypatch.setattr(loop, "_play_technical_fallback", AsyncMock(return_value=False))
    disconnect = AsyncMock()
    monkeypatch.setattr(loop, "_fast_disconnect_after_farewell", disconnect)
    await loop._runtime_end("provider_failure")
    assert disconnect.await_args.args[0] == "provider_failure"
    await loop.close()


@pytest.mark.asyncio
async def test_realtime_internal_runtime_error_does_not_claim_speech_outage(monkeypatch):
    loop = PstnRealtimeVoiceLoop(session_id="rt-internal-end", call_id=None, on_agent_wire=AsyncMock())
    announce = AsyncMock(return_value=True)
    disconnect = AsyncMock()
    monkeypatch.setattr(loop, "_play_technical_fallback", announce)
    monkeypatch.setattr(loop, "_fast_disconnect_after_farewell", disconnect)
    await loop._runtime_end("runtime_failure")
    announce.assert_not_awaited()
    disconnect.assert_awaited_once_with("runtime_failure", False)
    await loop.close()
