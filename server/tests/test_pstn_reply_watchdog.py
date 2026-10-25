"""Post-final silence watchdog: one re-ask, then a spoken close."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from server.services import pstn_voice_core, turn_failure_log
from server.services.pstn_voice_core import PstnVoiceLoop


class _TurnTts:
    def __init__(self, loop: PstnVoiceLoop):
        self._loop = loop
        self._chars_sent = 0
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
        return self._chars_sent > 0

    async def prepare_for_turn(self) -> None:
        return None

    async def open(self, **_kwargs) -> None:
        return None

    async def send_text(self, text: str) -> None:
        self._chars_sent += len(text or "")
        await self._loop._emit_agent_wire(b"\x00" * 320)

    async def finish(self) -> None:
        return None

    async def end_turn(self) -> None:
        return None

    async def close(self) -> None:
        self.closed = True
        self._closed = True


def _install(monkeypatch, loop: PstnVoiceLoop, fake_stream):
    failures: list[dict] = []
    events: list[tuple[str, dict]] = []

    async def fake_record(**kwargs):
        failures.append(kwargs)
        return kwargs

    monkeypatch.setattr(pstn_voice_core, "PSTN_REPLY_WATCHDOG_S", 0.05)
    monkeypatch.setattr(pstn_voice_core, "PSTN_REPLY_WATCHDOG_TOOL_S", 0.05)
    monkeypatch.setattr(pstn_voice_core, "log_pstn", lambda phase, **kw: events.append((phase, kw)))
    monkeypatch.setattr(
        "server.services.pstn_turn_tts.PstnTurnTtsSession",
        lambda _voice: _TurnTts(loop),
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
    monkeypatch.setattr("server.call.call_ledger.call_ledger.append_assistant_turn", AsyncMock())
    monkeypatch.setattr(loop, "_finish_agent_hangup", AsyncMock())
    fallback = AsyncMock()
    monkeypatch.setattr(loop, "_play_technical_fallback_and_hangup", fallback)
    return fallback, failures, events


@pytest.mark.asyncio
async def test_silent_first_attempt_is_reasked_once_and_recovers(monkeypatch):
    calls: list[dict] = []

    async def fake_stream(**kwargs):
        calls.append(kwargs)
        if not kwargs.get("retry_attempt"):
            await asyncio.sleep(5)
            yield {"delta": "never spoken"}
        yield {"delta": "Sure, I can help with that."}
        yield {"done": True, "text": "Sure, I can help with that.", "finish_reason": "stop"}

    loop = PstnVoiceLoop(
        session_id="watchdog",
        call_id="c-watchdog-retry",
        on_agent_wire=AsyncMock(),
        stack_override={"pipeline": "composed_voice"},
    )
    fallback, failures, events = _install(monkeypatch, loop, fake_stream)

    await loop._run_turn("are you still there")

    assert len(calls) == 2
    assert calls[1]["retry_attempt"] is True
    assert loop._watchdog_retry_used is True
    assert loop._turn_audio_delivered is True
    fallback.assert_not_awaited()
    assert any(phase == "turn.watchdog" and kw.get("event") == "reask" for phase, kw in events)
    assert failures and failures[0]["watchdog_retry"] is True
    assert failures[0]["delivered"] is True
    await loop.close()


@pytest.mark.asyncio
async def test_second_silent_attempt_falls_back_through_the_normal_goodbye(monkeypatch):
    calls: list[dict] = []

    async def fake_stream(**kwargs):
        calls.append(kwargs)
        await asyncio.sleep(5)
        yield {"delta": "late reply"}

    loop = PstnVoiceLoop(
        session_id="watchdog",
        call_id="c-watchdog-giveup",
        on_agent_wire=AsyncMock(),
        stack_override={"pipeline": "composed_voice"},
    )
    fallback, failures, events = _install(monkeypatch, loop, fake_stream)

    await loop._run_turn("hello")

    assert len(calls) == 2
    fallback.assert_not_awaited()
    loop._finish_agent_hangup.assert_awaited_once_with(reason="agent_hangup", revocable=False)
    assert any(phase == "turn.watchdog" and kw.get("event") == "gave_up" for phase, kw in events)
    assert failures and failures[0]["error_type"] == "TimeoutError"
    assert failures[0]["watchdog_retry"] is True
    assert failures[0]["delivered"] is False
    await loop.close()
