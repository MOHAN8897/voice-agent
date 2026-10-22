import asyncio
import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.services.telnyx_pstn_bridge import OutboundFrame, TelnyxPstnBridge


@pytest.mark.asyncio
async def test_lookahead_preserves_every_frame_in_order():
    ws = SimpleNamespace(send_text=AsyncMock())
    bridge = TelnyxPstnBridge(ws)
    bridge._voice = SimpleNamespace(_response_open=True, _tts_active=True)
    frames = [bytes([i, 0]) * 320 for i in (1, 2, 3)]
    await bridge._out_queue.put(OutboundFrame(frames[0], "L16", "t", "g"))
    task = asyncio.create_task(bridge._out_worker())
    try:
        await asyncio.sleep(0.01)
        assert not ws.send_text.called
        for payload in frames[1:]:
            await bridge._out_queue.put(OutboundFrame(payload, "L16", "t", "g"))
        for _ in range(100):
            if ws.send_text.await_count == 3:
                break
            await asyncio.sleep(0.005)
        assert [base64.b64decode(json.loads(c.args[0])["media"]["payload"])
                for c in ws.send_text.await_args_list] == frames
    finally:
        bridge._closed = True
        task.cancel()
        await task


@pytest.mark.asyncio
async def test_barge_during_lookahead_drops_held_generation():
    ws = SimpleNamespace(send_text=AsyncMock())
    bridge = TelnyxPstnBridge(ws)
    bridge._voice = SimpleNamespace(_response_open=True, _tts_active=True)
    await bridge._out_queue.put(OutboundFrame(b"\x00" * 640, "L16", "t", "g"))
    task = asyncio.create_task(bridge._out_worker())
    try:
        await asyncio.sleep(0.01)
        bridge._invalid_generations.add("g")
        await asyncio.sleep(0.08)
        ws.send_text.assert_not_awaited()
    finally:
        bridge._closed = True
        task.cancel()
        await task
