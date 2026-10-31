"""A transient TTS socket failure retries once instead of ending the call."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from server.services.pstn_voice_core import PstnVoiceLoop


@pytest.mark.asyncio
async def test_one_reconnect_retries_the_failed_sentence(monkeypatch):
    loop = PstnVoiceLoop(session_id="tts-retry", call_id=None, on_agent_wire=AsyncMock())
    loop.current_generation_id = "gen-1"
    sent: list[str] = []

    class Flaky:
        async def send_text(self, text: str) -> None:
            sent.append(text)
            if len(sent) == 1:
                raise ConnectionResetError("socket reset")

    healthy = AsyncMock()
    restarted: list[object] = []

    async def restart(failed):
        restarted.append(failed)
        return healthy

    monkeypatch.setattr(loop, "_restart_tts_session", restart)
    session = await loop._send_tts_text(Flaky(), "Namaste, how can I help?")
    assert session is healthy
    assert sent == ["Namaste, how can I help?"]
    healthy.send_text.assert_awaited_once()
    assert loop._tts_retry_used_for_turn is True
    assert restarted
    await loop.close()


@pytest.mark.asyncio
async def test_second_transport_failure_still_raises(monkeypatch):
    loop = PstnVoiceLoop(session_id="tts-retry-twice", call_id=None, on_agent_wire=AsyncMock())
    loop.current_generation_id = "gen-1"

    class AlwaysBroken:
        async def send_text(self, text: str) -> None:
            raise ConnectionResetError("socket reset")

    broken = AsyncMock()
    broken.send_text.side_effect = ConnectionResetError("still down")

    async def restart(_failed):
        return broken

    monkeypatch.setattr(loop, "_restart_tts_session", restart)
    with pytest.raises(ConnectionResetError):
        await loop._send_tts_text(AlwaysBroken(), "Namaste")
    await loop.close()
