"""A goodbye is revocable until the carrier hangup.

The composed pipeline used to speak the accepted farewell and disconnect even
when the caller had already asked a new question. These tests pin the
authorization rail: a question/request/wait reopens the call, while the
caller's own goodbye, thanks, or acknowledgement lets the close finish.
"""
from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.call import call_context
from server.call.close_call_executor import execute_agent_close
from server.services import pstn_voice_core as core


class Playback:
    def __init__(self, playing_for: float):
        self._until = time.monotonic() + playing_for

    def is_active(self) -> bool:
        return time.monotonic() < self._until


class SttEvents:
    def __init__(self, events):
        self.events = events

    async def __aiter__(self):
        for event in self.events:
            yield json.dumps(event)


@pytest.fixture
def armed_ctx(monkeypatch):
    ctx = SimpleNamespace(agent_hangup_armed=True)
    monkeypatch.setattr(call_context, "get", lambda call_id: ctx)
    return ctx


def _loop(call_id: str = "call-revoke") -> core.PstnVoiceLoop:
    loop = core.PstnVoiceLoop(session_id="revoke", call_id=call_id, on_agent_wire=AsyncMock())
    loop.current_generation_id = "revoke-generation"
    return loop


@pytest.mark.parametrize("text", [
    "అదే వెడ్డింగ్ కార్డ్స్ ధర ఎంత చెప్పగలరా?",
    "Tell me the price.",
    "I want the wedding cards.",
    "wait",
    "I never said no",
    "ఎంత?",
])
def test_new_caller_turn_revokes_a_pending_goodbye(text):
    assert _loop()._close_revocable_text(text) is True


@pytest.mark.parametrize("text", [
    "bye",
    "that's all, thanks",
    "thank you",
    "సరే, బాయ్",
])
def test_caller_goodbye_or_thanks_does_not_revoke(text):
    assert _loop()._close_revocable_text(text) is False


def test_backchannel_acknowledges_the_goodbye_unless_a_question_is_open():
    loop = _loop()
    assert loop._agent_expects_answer() is False
    assert loop._close_revocable_text("okay") is False
    loop._expects_answer = True
    assert loop._close_revocable_text("yes") is True


@pytest.mark.asyncio
async def test_question_during_farewell_revokes_the_disconnect(armed_ctx):
    loop = _loop()
    loop.playback = Playback(playing_for=0.18)
    provider = AsyncMock()
    loop.set_hangup_handler(provider)

    async def caller_asks_meanwhile() -> None:
        await asyncio.sleep(0.06)
        loop._pending_transcript = "అదే వెడ్డింగ్ కార్డ్స్ ధర ఎంత చెప్పగలరా?"

    question = asyncio.create_task(caller_asks_meanwhile())
    await loop._finish_agent_hangup(reason="goodbye", spoke_farewell=True)
    await question

    provider.assert_not_awaited()
    assert loop._phase == core.PHASE_LISTENING
    assert loop._hangup_started is False
    assert loop._background_hangup_task is None
    assert loop._pending_transcript == "అదే వెడ్డింగ్ కార్డ్స్ ధర ఎంత చెప్పగలరా?"
    assert armed_ctx.agent_hangup_armed is False


@pytest.mark.asyncio
async def test_pending_question_skips_the_close_before_farewell(armed_ctx):
    loop = _loop()
    loop._set_phase(core.PHASE_SPEAKING)
    loop._pending_transcript = "Tell me the price."
    provider = AsyncMock()
    loop.set_hangup_handler(provider)

    await loop._finish_agent_hangup(reason="goodbye", spoke_farewell=True)

    provider.assert_not_awaited()
    assert loop._hangup_started is False
    assert loop._phase == core.PHASE_SPEAKING
    assert loop._pending_transcript == "Tell me the price."
    assert armed_ctx.agent_hangup_armed is False


@pytest.mark.asyncio
async def test_caller_goodbye_during_farewell_disconnects_once(monkeypatch):
    loop = _loop()
    loop.playback = Playback(playing_for=0.1)
    provider = AsyncMock()
    loop.set_hangup_handler(provider)
    lifecycle_end = AsyncMock()
    monkeypatch.setattr(
        "server.call.call_lifecycle_service.call_lifecycle_service.end",
        lifecycle_end,
    )

    async def caller_says_bye() -> None:
        await asyncio.sleep(0.03)
        loop._pending_transcript = "bye"

    bye = asyncio.create_task(caller_says_bye())
    await loop._finish_agent_hangup(reason="goodbye", spoke_farewell=True)
    await bye

    provider.assert_awaited_once()
    assert loop._phase == core.PHASE_ENDED
    await loop._background_hangup_task
    lifecycle_end.assert_awaited_once_with("call-revoke", reason="goodbye")


@pytest.mark.asyncio
async def test_failure_teardown_is_not_revoked_by_pending_speech(monkeypatch):
    loop = _loop()
    loop.playback = Playback(playing_for=0.0)
    provider = AsyncMock()
    loop.set_hangup_handler(provider)
    monkeypatch.setattr(
        "server.call.call_lifecycle_service.call_lifecycle_service.end",
        AsyncMock(),
    )
    loop._pending_transcript = "Tell me the price."

    await loop._finish_agent_hangup(
        reason="technical_fallback", spoke_farewell=False, revocable=False,
    )

    provider.assert_awaited_once()
    assert loop._phase == core.PHASE_ENDED
    await loop._background_hangup_task


@pytest.mark.asyncio
async def test_question_final_during_closing_is_kept_without_voice_latch():
    loop = _loop(call_id=None)
    loop._set_phase(core.PHASE_CLOSING)
    loop._turn_busy = True
    loop._last_vad_voice_at = 0.0
    loop._stt = SttEvents([
        {"event": "transcript.final", "text": "ధర ఎంత చెప్పగలరా?"},
    ])

    await loop._stt_reader()

    assert loop._pending_transcript == "ధర ఎంత చెప్పగలరా?"


@pytest.mark.asyncio
async def test_goodbye_final_during_closing_is_not_queued():
    loop = _loop(call_id=None)
    loop._set_phase(core.PHASE_CLOSING)
    loop._turn_busy = True
    loop._last_vad_voice_at = 0.0
    loop._stt = SttEvents([
        {"event": "transcript.final", "text": "bye"},
    ])

    await loop._stt_reader()

    assert loop._pending_transcript is None


@pytest.mark.asyncio
async def test_executor_reports_cancellation_without_touching_the_provider(monkeypatch):
    monkeypatch.setattr("server.call.natural_hangup.HANGUP_TRAIL_SILENCE_SEC", 0.0)
    provider = AsyncMock()
    ended = AsyncMock()

    result = await execute_agent_close(
        call_id="call-cancelled",
        reason="goodbye",
        spoke_farewell=True,
        is_playing=lambda: False,
        on_provider_hangup=provider,
        on_ended=ended,
        can_disconnect=lambda: False,
    )

    assert result.cancelled is True
    assert result.background_task is None
    provider.assert_not_awaited()
    ended.assert_not_awaited()
