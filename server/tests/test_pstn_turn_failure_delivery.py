"""A late turn error must not replace audio the caller already heard.

These calls played the outage apology and hung up after the reply had already
been delivered; the fallback is only valid when the turn produced no audio.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from server.services.pstn_voice_core import PstnVoiceLoop


class _TurnTts:
    def __init__(self, loop: PstnVoiceLoop, *, emit_audio: bool):
        self._loop = loop
        self._emit_audio = emit_audio
        self._chars_sent = 0
        self._audio_bytes = 0
        self.closed = False

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


def _install_turn(monkeypatch, loop: PstnVoiceLoop, *, emit_audio: bool, exc: Exception):
    session = _TurnTts(loop, emit_audio=emit_audio)

    async def fake_stream(**_kwargs):
        yield {"delta": "Namaste, I can help with that. "}
        raise exc

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
    fallback = AsyncMock()
    monkeypatch.setattr(loop, "_play_technical_fallback_and_hangup", fallback)
    return session, fallback


@pytest.mark.asyncio
async def test_delivered_audio_keeps_the_call_alive_on_late_error(monkeypatch):
    loop = PstnVoiceLoop(
        session_id="delivery",
        call_id="c-late-error",
        on_agent_wire=AsyncMock(),
        stack_override={"pipeline": "composed_voice"},
    )
    session, fallback = _install_turn(
        monkeypatch,
        loop,
        emit_audio=True,
        exc=RuntimeError("tts reader closed after audio"),
    )

    await loop._run_turn("yes please share the details")

    assert loop._turn_audio_delivered is True
    fallback.assert_not_awaited()
    assert session.closed is True
    assert loop._phase != "ended"
    await loop.close()


@pytest.mark.asyncio
async def test_missing_audio_still_plays_the_outage_apology(monkeypatch):
    loop = PstnVoiceLoop(
        session_id="no-delivery",
        call_id="c-empty-turn",
        on_agent_wire=AsyncMock(),
        stack_override={"pipeline": "composed_voice"},
    )
    _, fallback = _install_turn(
        monkeypatch,
        loop,
        emit_audio=False,
        exc=RuntimeError("tts produced no audio"),
    )

    await loop._run_turn("yes please share the details")

    assert loop._turn_audio_delivered is False
    fallback.assert_awaited_once()
    assert fallback.await_args.kwargs["trigger"] == "runtime_failure"
    await loop.close()
