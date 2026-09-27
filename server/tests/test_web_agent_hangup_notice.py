"""Hangup notice callback fires without tearing down the process."""
from __future__ import annotations

import pytest

from server.realtime.testing import FakeRealtimeVoiceAdapter


@pytest.mark.asyncio
async def test_hangup_notice_callback_does_not_close_loop_server():
    notices: list[tuple[str, str]] = []

    async def on_wire(_wire: bytes) -> None:
        return None

    async def on_notice(stage: str, reason: str) -> None:
        notices.append((stage, reason))

    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    loop = PstnRealtimeVoiceLoop(
        session_id="s-web",
        call_id="c-hangup-notice",
        on_agent_wire=on_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=FakeRealtimeVoiceAdapter(),
        stack_override={"pipeline": "realtime_voice"},
    )
    loop.set_hangup_notice_handler(on_notice)
    await loop._notify_hangup("initiated", "goodbye")
    await loop._notify_hangup("initiated", "goodbye")
    assert notices == [("initiated", "goodbye")]
    await loop.close()
    assert loop._closed
