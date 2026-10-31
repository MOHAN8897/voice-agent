import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.routes.web_agent_ws import _drive_browser_voice


@pytest.mark.asyncio
async def test_microphone_can_arrive_during_provider_startup():
    microphone = asyncio.Event()
    ready = asyncio.Event()
    received = []

    async def start_call(**_kwargs):
        await microphone.wait()

    async def feed_user_pcm16(data):
        received.append(data)
        microphone.set()

    async def receive():
        if not microphone.is_set():
            return {"bytes": b"\x01\x00" * 320}
        await ready.wait()
        return {"type": "websocket.disconnect"}

    async def notify():
        ready.set()

    loop = SimpleNamespace(start_call=start_call, feed_user_pcm16=feed_user_pcm16)
    await asyncio.wait_for(_drive_browser_voice(SimpleNamespace(receive=receive), loop, notify), 1)
    assert ready.is_set() and len(received) == 1


@pytest.mark.asyncio
async def test_stop_cancels_an_unfinished_opening():
    cancelled = asyncio.Event()

    async def startup(**_kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def receive():
        await asyncio.sleep(0)
        return {"text": '{"type":"stop"}'}

    ready = AsyncMock()
    await asyncio.wait_for(_drive_browser_voice(SimpleNamespace(receive=receive), SimpleNamespace(start_call=startup), ready), 1)
    assert cancelled.is_set()
    ready.assert_not_awaited()


@pytest.mark.asyncio
async def test_startup_timeout_cancels_the_socket_reader():
    reader_cancelled = asyncio.Event()

    async def startup(**_kwargs):
        await asyncio.Event().wait()

    async def receive():
        try:
            await asyncio.Event().wait()
        finally:
            reader_cancelled.set()

    with pytest.raises(TimeoutError):
        await _drive_browser_voice(SimpleNamespace(receive=receive), SimpleNamespace(start_call=startup), AsyncMock(), startup_timeout=.02)
    assert reader_cancelled.is_set()


@pytest.mark.asyncio
async def test_vobiz_startup_failure_disconnects_silent_call():
    from server.services.vobiz_pstn_bridge import VobizPstnBridge

    bridge = VobizPstnBridge(SimpleNamespace())
    bridge.agent_id = "agent"
    bridge.call_id = "call"
    bridge._voice = SimpleNamespace(start_call=AsyncMock(side_effect=RuntimeError("provider setup failed")))
    bridge.hangup = AsyncMock()
    await bridge._start_voice_loop()
    bridge.hangup.assert_awaited_once_with(reason="voice_start_failed")


@pytest.mark.asyncio
@pytest.mark.parametrize("nested", [False, True])
async def test_vobiz_media_start_identifiers_and_bidirectional_pcm(monkeypatch, nested):
    import base64
    import json
    from server.services import vobiz_pstn_bridge as module

    voice = SimpleNamespace(
        start_call=AsyncMock(), close=AsyncMock(), feed_user_pcm16=AsyncMock(),
        set_barge_handler=lambda _handler: None, set_hangup_handler=lambda _handler: None,
        set_turn_audio_done_handler=lambda _handler: None, current_generation_id=None,
    )
    monkeypatch.setattr(module, "create_pstn_voice_loop", lambda **_kwargs: voice)
    monkeypatch.setattr("server.services.pstn_prewarm.take_prewarm_for_answer", AsyncMock(return_value=None))
    monkeypatch.setattr(module, "active_vobiz_bridges", {})
    registry = SimpleNamespace(get=lambda _key: {}, upsert=lambda *_args: None, alias=lambda *_args: None)
    monkeypatch.setattr(module, "vobiz_call_registry", registry)
    ws = SimpleNamespace(send_text=AsyncMock(), close=AsyncMock())
    bridge = module.VobizPstnBridge(ws)
    bridge._token_meta = {"call_uuid": "synthetic-call"}
    media = {"mediaFormat": {"encoding": "audio/x-l16", "sampleRate": 16000}}
    event = {"callUUID": "synthetic-call", "streamId": "synthetic-stream", **({"start": media} if nested else media)}
    try:
        await bridge._on_start(event)
        await bridge._start_voice_task
        assert bridge.call_uuid == "synthetic-call"
        assert bridge.stream_id == "synthetic-stream"
        assert bridge._wire_sample_rate == 16000
        pcm = b"\x01\x00" * 320
        await bridge._on_media({"media": {"payload": base64.b64encode(pcm).decode()}})
        voice.feed_user_pcm16.assert_awaited_once_with(pcm)
        await bridge._send_agent_wire(pcm)
        outgoing = json.loads(ws.send_text.await_args.args[0])
        assert outgoing["event"] == "playAudio"
        assert outgoing["streamId"] == "synthetic-stream"
        assert outgoing["media"]["sampleRate"] == 16000
        assert base64.b64decode(outgoing["media"]["payload"]) == pcm
    finally:
        await bridge._cleanup("test_complete")


@pytest.mark.asyncio
async def test_vobiz_disconnect_cancels_pending_startup():
    from server.services.vobiz_pstn_bridge import VobizPstnBridge

    bridge = VobizPstnBridge(SimpleNamespace(close=AsyncMock()))
    bridge.call_uuid = "synthetic-disconnect"
    bridge._voice = SimpleNamespace(close=AsyncMock())
    startup = asyncio.create_task(asyncio.Event().wait())
    bridge._start_voice_task = startup
    await bridge._cleanup("test_disconnect")
    assert startup.cancelled()
    bridge._voice.close.assert_awaited_once()
