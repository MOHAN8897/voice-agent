"""Realtime prewarm greeting — PCM capture and wire framing."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from server.realtime.models import REALTIME_PCM_RATE
from server.services.audio_transcode import StreamingPcmResampler
from server.services.pstn_realtime_greeting_prewarm import (
    realtime_pcm24_to_wire_frames,
    synthesize_realtime_greeting_frames,
    wire_frame_bytes,
)


def _make_pcm24(duration_ms: int = 40) -> bytes:
    samples = int(REALTIME_PCM_RATE * duration_ms / 1000)
    return b"\x00\x01" * samples


def test_wire_frame_bytes_telnyx():
    assert wire_frame_bytes(16000, linear16=True) == 640
    assert wire_frame_bytes(8000, linear16=False) == 160


def test_realtime_pcm24_to_wire_frames_telnyx_l16():
    pcm = _make_pcm24(40)
    frames = realtime_pcm24_to_wire_frames(pcm, sample_rate=16000, tts_output_codec="linear16")
    assert frames
    assert all(len(f) == 640 for f in frames)


def test_realtime_pcm24_to_wire_frames_exotel_mulaw():
    pcm = _make_pcm24(40)
    frames = realtime_pcm24_to_wire_frames(pcm, sample_rate=8000, tts_output_codec="mulaw")
    assert frames
    assert all(len(f) == 160 for f in frames)


@pytest.mark.asyncio
async def test_synthesize_collects_audio_and_deletes_items():
    pcm = _make_pcm24(60)

    class StubAdapter:
        def __init__(self) -> None:
            self.started = False
            self.deleted = False
            self.discarded = False
            self._events = [
                {"type": "audio_delta", "pcm": pcm},
                {
                    "type": "assistant_transcript",
                    "text": "Hi, this is Tis from Bindusara. Do you have a moment?",
                },
                {"type": "response_done", "status": "completed", "failed": False},
            ]
            self._idx = 0

        async def start_response(self, *, instructions: str | None = None) -> None:
            self.started = True
            self.instructions = instructions

        async def poll_event(self, timeout: float = 0.5):
            _ = timeout
            if self._idx >= len(self._events):
                return None
            ev = self._events[self._idx]
            self._idx += 1
            return ev

        async def cancel_response(self) -> None:
            return None

        async def delete_synthetic_response_items(self) -> None:
            self.deleted = True

        def discard_queued(self) -> None:
            self.discarded = True

    adapter = StubAdapter()
    frames, transcript = await synthesize_realtime_greeting_frames(
        adapter,
        greeting_text="Hi, this is Tis from Bindusara. Do you have a moment?",
        sample_rate=16000,
        tts_output_codec="linear16",
        control_id="ctrl-1",
    )
    assert adapter.started
    assert adapter.deleted
    assert adapter.discarded
    assert frames
    assert "Tis" in transcript


@pytest.mark.asyncio
async def test_synthesize_empty_on_timeout():
    class SlowAdapter:
        async def start_response(self, *, instructions: str | None = None) -> None:
            return None

        async def poll_event(self, timeout: float = 0.5):
            await asyncio.sleep(0)
            return None

        async def cancel_response(self) -> None:
            return None

    frames, transcript = await synthesize_realtime_greeting_frames(
        SlowAdapter(),
        greeting_text="Hello",
        sample_rate=16000,
        tts_output_codec="linear16",
        timeout_sec=0.05,
        control_id="ctrl-2",
    )
    assert frames == []
    assert transcript == ""


@pytest.mark.asyncio
async def test_synthesize_empty_greeting():
    frames, transcript = await synthesize_realtime_greeting_frames(
        AsyncMock(),
        greeting_text="   ",
        sample_rate=16000,
        tts_output_codec="linear16",
    )
    assert frames == []
    assert transcript == ""
