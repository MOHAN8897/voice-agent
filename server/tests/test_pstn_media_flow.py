"""Codec correctness, media validation, telemetry, and queue behavior."""
from __future__ import annotations

import asyncio
import base64
import json
import math
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.services.audio_transcode import (
    alaw_to_pcm16,
    convert_g711,
    pcm16_dbfs,
    pcm16_to_alaw,
    pcm16_to_mulaw,
    mulaw_to_pcm16,
)
from server.services.pstn_media_flow import CallMediaConfig, PstnMediaFlowStore
from server.services.telnyx_pstn_bridge import (
    MAX_AUDIO_QUEUE_FRAMES,
    OutboundFrame,
    PLAYOUT_PRIME_FRAMES,
    QUEUE_HIGH_WATERMARK,
    QUEUE_LOW_WATERMARK,
    TelnyxPstnBridge,
)


def tone(sample_rate: int = 8000, ms: int = 20) -> bytes:
    count = sample_rate * ms // 1000
    samples = (int(10000 * math.sin(2 * math.pi * 440 * i / sample_rate)) for i in range(count))
    return b"".join(sample.to_bytes(2, "little", signed=True) for sample in samples)


def test_g711_encode_decode_and_cross_conversion():
    pcm = tone()
    pcmu = pcm16_to_mulaw(pcm, 8000)
    pcma = pcm16_to_alaw(pcm, 8000)
    assert len(pcmu) == len(pcma) == 160
    assert len(mulaw_to_pcm16(pcmu, 8000)) == 320
    assert len(alaw_to_pcm16(pcma, 8000)) == 320
    converted = convert_g711(pcmu, "PCMU", "PCMA")
    assert len(converted) == 160
    assert pcm16_dbfs(alaw_to_pcm16(converted, 8000)) is not None


def test_call_media_config_validates_format_and_duration():
    pcmu = CallMediaConfig(codec="PCMU", sample_rate=8000, channels=1)
    pcma = CallMediaConfig(codec="PCMA", sample_rate=8000, channels=1)
    assert pcmu.frame_bytes == pcma.frame_bytes == 160
    assert pcmu.duration_ms(160) == 20
    with pytest.raises(ValueError):
        CallMediaConfig(codec="PCMU", sample_rate=16000)
    with pytest.raises(ValueError):
        CallMediaConfig(codec="PCMA", sample_rate=8000, channels=2)


def test_base64_is_encoded_exactly_once():
    raw = pcm16_to_mulaw(tone(), 8000)
    encoded = base64.b64encode(raw).decode("ascii")
    message = json.dumps({"event": "media", "media": {"payload": encoded}})
    parsed = json.loads(message)
    assert base64.b64decode(parsed["media"]["payload"]) == raw
    assert len(parsed["media"]["payload"]) == 216


def test_negotiation_mismatch_is_visible_and_health_is_honest():
    store = PstnMediaFlowStore()
    store.start(
        external_id="control-1",
        ws_id="ws-1",
        configured=CallMediaConfig(codec="PCMU"),
    )
    failures = store.negotiate("control-1", CallMediaConfig(codec="PCMA"))
    assert failures == ["CODEC_MISMATCH expected=PCMU negotiated=PCMA"]
    snap = store.snapshot("control-1")
    assert snap is not None
    assert snap["health"]["claim"] is None
    assert snap["health"]["score"] < 100


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send_text(self, message: str) -> None:
        self.messages.append(message)


@pytest.mark.asyncio
async def test_bounded_queue_backpressure_and_barge_in_clears_frames():
    ws = FakeWebSocket()
    bridge = TelnyxPstnBridge(ws)  # type: ignore[arg-type]
    bridge._voice = SimpleNamespace(
        current_turn_id="turn-1",
        current_generation_id="generation-1",
        current_output_codec="PCMU",
    )
    assert bridge._out_queue.maxsize == MAX_AUDIO_QUEUE_FRAMES
    assert MAX_AUDIO_QUEUE_FRAMES <= 28
    for _ in range(QUEUE_HIGH_WATERMARK):
        await bridge._send_agent_wire(b"\xff" * 160)
    assert bridge._out_queue.qsize() == QUEUE_HIGH_WATERMARK
    blocked = asyncio.create_task(bridge._send_agent_wire(b"\xff" * 160))
    await asyncio.sleep(0.05)
    assert not blocked.done()
    assert bridge._queue_metrics["normal_speech_dropped_frames"] == 0
    await bridge._barge_in()
    await blocked
    assert bridge._out_queue.qsize() == 0
    assert json.loads(ws.messages[-1]) == {"event": "clear"}
    assert bridge._queue_metrics["barge_in_discarded_frames"] >= QUEUE_HIGH_WATERMARK
    assert bridge._queue_metrics["normal_speech_dropped_frames"] == 0


@pytest.mark.asyncio
async def test_queue_backpressure_resumes_without_dropping_speech():
    ws = FakeWebSocket()
    bridge = TelnyxPstnBridge(ws)  # type: ignore[arg-type]
    bridge._voice = SimpleNamespace(
        current_turn_id="turn-1",
        current_generation_id="generation-1",
        current_output_codec="PCMU",
    )
    for _ in range(QUEUE_HIGH_WATERMARK):
        await bridge._send_agent_wire(b"\xff" * 160)
    blocked = asyncio.create_task(bridge._send_agent_wire(b"\xff" * 160))
    await asyncio.sleep(0.05)
    assert not blocked.done()
    drain_n = QUEUE_HIGH_WATERMARK - QUEUE_LOW_WATERMARK + 1
    for _ in range(drain_n):
        bridge._out_queue.get_nowait()
    await bridge._signal_queue_space()
    await asyncio.wait_for(blocked, 1.0)
    assert bridge._queue_metrics["normal_speech_dropped_frames"] == 0
    assert bridge._queue_metrics["producer_backpressure_wait_count"] >= 1
    assert bridge._out_queue.qsize() > 0


@pytest.mark.asyncio
async def test_hangup_unblocks_backpressure_wait_and_clears_queue():
    ws = FakeWebSocket()
    bridge = TelnyxPstnBridge(ws)  # type: ignore[arg-type]
    bridge._voice = SimpleNamespace(
        current_turn_id="turn-1",
        current_generation_id="generation-1",
        current_output_codec="PCMU",
        close=AsyncMock(),
    )
    for _ in range(QUEUE_HIGH_WATERMARK):
        await bridge._send_agent_wire(b"\xff" * 160)
    blocked = asyncio.create_task(bridge._send_agent_wire(b"\xff" * 160))
    await asyncio.sleep(0.05)
    assert not blocked.done()
    await bridge._cleanup("hangup")
    await asyncio.wait_for(blocked, 1.0)
    assert bridge._out_queue.qsize() == 0
    assert bridge._queue_metrics["hangup_discarded_frames"] >= 1
    assert bridge._queue_metrics["normal_speech_dropped_frames"] == 0


@pytest.mark.asyncio
async def test_playout_prime_waits_for_jitter_buffer_before_first_send():
    ws = FakeWebSocket()
    bridge = TelnyxPstnBridge(ws)  # type: ignore[arg-type]
    bridge._voice = SimpleNamespace(
        current_turn_id="turn-1",
        current_generation_id="generation-1",
        current_output_codec="PCMU",
        _tts_active=True,
        _active_tts_session=SimpleNamespace(_closed=False),
    )
    bridge._negotiated_media = CallMediaConfig(codec="PCMU")
    for _ in range(PLAYOUT_PRIME_FRAMES - 1):
        bridge._out_queue.put_nowait(
            OutboundFrame(b"\xff" * 160, "PCMU", "turn-1", "generation-1")
        )
    worker = asyncio.create_task(bridge._out_worker())
    await asyncio.sleep(0.08)
    assert ws.messages == []
    bridge._out_queue.put_nowait(
        OutboundFrame(b"\xff" * 160, "PCMU", "turn-1", "generation-1")
    )
    for _ in range(40):
        if ws.messages:
            break
        await asyncio.sleep(0.01)
    bridge._closed = True
    worker.cancel()
    await worker
    assert len(ws.messages) >= 1


@pytest.mark.asyncio
async def test_outbound_message_matches_negotiated_pcma():
    ws = FakeWebSocket()
    bridge = TelnyxPstnBridge(ws)  # type: ignore[arg-type]
    bridge.call_control_id = "control-2"
    bridge._negotiated_media = CallMediaConfig(codec="PCMA")
    bridge._wire_codec = "PCMA"
    await bridge._send_agent_wire(b"\xff" * 160)
    bridge._out_task = asyncio.create_task(bridge._out_worker())
    for _ in range(20):
        if ws.messages:
            break
        await asyncio.sleep(0.01)
    bridge._closed = True
    bridge._out_task.cancel()
    await bridge._out_task
    body = json.loads(ws.messages[0])
    payload = base64.b64decode(body["media"]["payload"])
    assert len(payload) == 160
    assert payload != b"\xff" * 160  # explicit μ-law → A-law conversion happened
