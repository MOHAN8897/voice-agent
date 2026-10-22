from unittest.mock import AsyncMock

import pytest

from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop


@pytest.mark.asyncio
@pytest.mark.parametrize("rate,codec,tail,silence,frame", [
    (16000, "linear16", b"\x01\x02" * 17, b"\x00", 640),
    (8000, "mulaw", b"\x81" * 17, b"\xff", 160),
])
async def test_ordinary_turn_flushes_tail_with_codec_silence(rate, codec, tail, silence, frame):
    wire = AsyncMock()
    loop = PstnRealtimeVoiceLoop(session_id="tail", call_id=None,
        on_agent_wire=wire, sample_rate=rate, tts_output_codec=codec)
    loop._out_pcm.extend(tail)
    await loop._handle_event({"type": "response_done"})
    wire.assert_awaited_once_with(tail + silence * (frame - len(tail)))
    assert not loop._out_pcm
    await loop.close()


@pytest.mark.asyncio
async def test_interruption_does_not_flush_cancelled_speech():
    wire = AsyncMock()
    loop = PstnRealtimeVoiceLoop(session_id="tail", call_id=None, on_agent_wire=wire)
    loop._out_pcm.extend(b"\x81" * 17)
    await loop._handle_event({"type": "cancelled"})
    wire.assert_not_awaited()
    await loop.close()
