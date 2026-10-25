"""Model failures close with TTS speech; only missing TTS audio uses the clip."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.call.live_turn_orchestrator import live_turn_orchestrator
from server.providers.llm_protocol import IncompleteTurnError
from server.services import turn_failure_log
from server.services.pstn_voice_core import PstnVoiceLoop


class _TurnTts:
    def __init__(self, loop: PstnVoiceLoop, *, emit_audio: bool):
        self._loop = loop
        self._emit_audio = emit_audio
        self._chars_sent = 0
        self._audio_bytes = 0
        self.closed = False
        self._closed = False

    @property
    def has_sent_text(self) -> bool:
        return self._chars_sent > 0

    @property
    def had_error(self) -> bool:
        return False

    @property
    def audio_emitted(self) -> bool:
        return self._audio_bytes > 0

    async def prepare_for_turn(self) -> None:
        return None

    async def open(self, **_kwargs) -> None:
        return None

    async def send_text(self, text: str) -> None:
        self._chars_sent += len(text or "")
        if self._emit_audio:
            self._audio_bytes += 320
            await self._loop._emit_agent_wire(b"\x00" * 320)

    async def finish(self) -> None:
        return None

    async def end_turn(self) -> None:
        return None

    async def close(self) -> None:
        self.closed = True
        self._closed = True


def _install_runtime(monkeypatch, loop: PstnVoiceLoop, session, fake_stream):
    failures: list[dict] = []

    async def fake_record(**kwargs):
        failures.append(kwargs)
        return kwargs

    sessions = [session]

    def make_session(_voice):
        if not sessions[0]._closed:
            return sessions[0]
        fresh = _TurnTts(loop, emit_audio=session._emit_audio)
        sessions.insert(0, fresh)
        return fresh

    monkeypatch.setattr("server.services.pstn_turn_tts.PstnTurnTtsSession", make_session)
    monkeypatch.setattr(
        "server.call.live_turn_orchestrator.live_turn_orchestrator.handle_user_turn_stream",
        fake_stream,
    )
    monkeypatch.setattr(
        "server.services.pstn_voice_core.pstn_turn_runtime",
        lambda *_a, **_k: {},
    )
    monkeypatch.setattr(
        "server.services.saas.session_failure_log.record_session_failure",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(turn_failure_log, "record_turn_failure", fake_record)
    monkeypatch.setattr("server.call.call_ledger.call_ledger.append_assistant_turn", AsyncMock())
    monkeypatch.setattr(loop, "_finish_agent_hangup", AsyncMock())
    fallback = AsyncMock()
    monkeypatch.setattr(loop, "_play_technical_fallback_and_hangup", fallback)
    return fallback, failures


def _install_turn(monkeypatch, loop: PstnVoiceLoop, *, emit_audio: bool, exc: Exception):
    session = _TurnTts(loop, emit_audio=emit_audio)

    async def fake_stream(**_kwargs):
        yield {"delta": "Namaste, I can help with that. "}
        raise exc

    fallback, failures = _install_runtime(monkeypatch, loop, session, fake_stream)
    return session, fallback, failures


@pytest.mark.asyncio
async def test_partial_audio_from_an_early_stop_closes_without_outage(monkeypatch):
    loop = PstnVoiceLoop(
        session_id="delivery",
        call_id="c-early-stop",
        on_agent_wire=AsyncMock(),
        stack_override={"pipeline": "composed_voice"},
    )
    _, fallback, failures = _install_turn(
        monkeypatch,
        loop,
        emit_audio=True,
        exc=IncompleteTurnError(
            provider="sarvam",
            finish_reason="length",
            partial_text="Namaste, I can help with that.",
            retry_used=True,
        ),
    )

    await loop._run_turn("yes please share the details")

    assert loop._turn_audio_delivered is True
    fallback.assert_not_awaited()
    loop._finish_agent_hangup.assert_awaited_once_with(reason="agent_hangup")
    assert loop._phase != "ended"
    assert failures and failures[0]["finish_reason"] == "length"
    assert failures[0]["delivered"] is False
    assert failures[0]["turn_completed"] is False
    assert failures[0]["retry_used"] is True
    assert failures[0]["transcript"] == "yes please share the details"
    await loop.close()


@pytest.mark.asyncio
async def test_call_58102ce4_refusal_gets_one_honorific_farewell_without_callback(monkeypatch):
    spoken: list[str] = []
    loop = PstnVoiceLoop(
        session_id="refusal",
        call_id="c-refusal-regression",
        on_agent_wire=AsyncMock(),
        stack_override={"pipeline": "composed_voice", "language": "te-IN"},
    )
    session = _TurnTts(loop, emit_audio=True)

    async def incomplete_stream(**_kwargs):
        raise IncompleteTurnError(
            provider="sarvam", finish_reason="length",
            partial_text="సరేనండి, no problem. Goodbye. సరేనండి, no problem. Goodbye.",
            retry_used=True,
        )
        yield  # pragma: no cover

    fallback, failures = _install_runtime(monkeypatch, loop, session, incomplete_stream)
    original_send = _TurnTts.send_text

    async def capture_send(self, text):
        spoken.append(text)
        await original_send(self, text)

    monkeypatch.setattr(_TurnTts, "send_text", capture_send)

    await loop._run_turn("అదే మొత్తం ఇప్పుడే ప్రొసీజర్ నాకు ఇప్పుడైతే ఇంట్రెస్ట్ ఏం లేదండి.")

    assert len(spoken) == 1
    assert "సరేనండి" in spoken[0] and "ధన్యవాదాలు" in spoken[0]
    assert "Goodbye" not in spoken[0]
    loop._finish_agent_hangup.assert_awaited_once_with(reason="firm_refusal")
    fallback.assert_not_awaited()
    assert failures and failures[0]["finish_reason"] == "length"
    await loop.close()


@pytest.mark.asyncio
async def test_exact_refusal_stream_speaks_once_and_drains_before_hangup(monkeypatch):
    loop = PstnVoiceLoop(
        session_id="refusal-rule", call_id="c-refusal-rule", on_agent_wire=AsyncMock(),
        stack_override={"pipeline": "composed_voice", "language": "te-IN"},
    )
    session = _TurnTts(loop, emit_audio=True)
    ctx = SimpleNamespace(
        status="active", agent_hangup_armed=False, barge_in_flight=False,
        last_stt_partial_at=None, call_end_policy=None,
        callback_request_text="", callback_close_phase="idle",
    )

    async def rule_stream(**kwargs):
        async for chunk in live_turn_orchestrator._stream_llm(ctx=ctx, **kwargs):
            yield chunk

    fallback, failures = _install_runtime(monkeypatch, loop, session, rule_stream)
    await loop._run_turn("అదే మొత్తం ఇప్పుడే ప్రొసీజర్ నాకు ఇప్పుడైతే ఇంట్రెస్ట్ ఏం లేదండి.")

    assert session._chars_sent > 0
    loop._finish_agent_hangup.assert_awaited_once_with(reason="firm_refusal")
    fallback.assert_not_awaited()
    assert not failures
    await loop.close()


@pytest.mark.asyncio
async def test_completed_turn_keeps_the_call_alive_on_late_error(monkeypatch):
    loop = PstnVoiceLoop(
        session_id="delivery",
        call_id="c-late-error",
        on_agent_wire=AsyncMock(),
        stack_override={"pipeline": "composed_voice"},
    )
    session = _TurnTts(loop, emit_audio=True)
    failures: list[dict] = []

    async def fake_stream(**_kwargs):
        yield {"delta": "Namaste, I can help with that. "}
        yield {
            "done": True,
            "text": "Namaste, I can help with that.",
            "finish_reason": "stop",
        }
        raise RuntimeError("tts reader closed after audio")

    async def fake_record(**kwargs):
        failures.append(kwargs)
        return kwargs

    monkeypatch.setattr(
        "server.services.pstn_turn_tts.PstnTurnTtsSession",
        lambda _voice: session,
    )
    monkeypatch.setattr(
        "server.call.live_turn_orchestrator.live_turn_orchestrator.handle_user_turn_stream",
        fake_stream,
    )
    monkeypatch.setattr(
        "server.services.pstn_voice_core.pstn_turn_runtime",
        lambda *_a, **_k: {},
    )
    monkeypatch.setattr(
        "server.services.saas.session_failure_log.record_session_failure",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(turn_failure_log, "record_turn_failure", fake_record)
    fallback = AsyncMock()
    monkeypatch.setattr(loop, "_play_technical_fallback_and_hangup", fallback)

    await loop._run_turn("yes please share the details")

    assert loop._turn_audio_delivered is True
    fallback.assert_not_awaited()
    assert session.closed is True
    assert loop._phase != "ended"
    # The failed turn is still kept for audit, but marked as delivered.
    assert failures and failures[0]["delivered"] is True
    assert failures[0]["turn_completed"] is True
    await loop.close()


@pytest.mark.asyncio
async def test_missing_tts_audio_still_plays_the_outage_apology(monkeypatch):
    loop = PstnVoiceLoop(
        session_id="no-delivery",
        call_id="c-empty-turn",
        on_agent_wire=AsyncMock(),
        stack_override={"pipeline": "composed_voice"},
    )
    _, fallback, failures = _install_turn(
        monkeypatch,
        loop,
        emit_audio=False,
        exc=RuntimeError("tts produced no audio"),
    )

    await loop._run_turn("yes please share the details")

    assert loop._turn_audio_delivered is False
    fallback.assert_awaited_once()
    assert fallback.await_args.kwargs["trigger"] == "tts_failure"
    assert failures and failures[0]["delivered"] is False
    await loop.close()


@pytest.mark.asyncio
async def test_completed_reply_without_tts_audio_is_recorded_and_apologized(monkeypatch):
    loop = PstnVoiceLoop(
        session_id="silent-tts",
        call_id="c-silent-tts",
        on_agent_wire=AsyncMock(),
        stack_override={"pipeline": "composed_voice"},
    )
    session = _TurnTts(loop, emit_audio=False)

    async def fake_stream(**_kwargs):
        yield {"delta": "Namaste, I can help with that. "}
        yield {
            "done": True,
            "text": "Namaste, I can help with that.",
            "finish_reason": "stop",
        }

    fallback, failures = _install_runtime(monkeypatch, loop, session, fake_stream)

    await loop._run_turn("yes please share the details")

    fallback.assert_awaited_once()
    assert fallback.await_args.kwargs["trigger"] == "tts_failure"
    assert failures and failures[0]["finish_reason"] == "tts_empty_audio"
    assert failures[0]["delivered"] is False
    assert failures[0]["turn_completed"] is True
    await loop.close()
