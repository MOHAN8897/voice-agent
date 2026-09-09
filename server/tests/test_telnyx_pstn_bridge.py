"""Telnyx PSTN bridge — wire format and track filtering."""
from __future__ import annotations

import base64

from server.services.audio_transcode import mulaw_to_pcm16, pcm16_chunk_to_mulaw_frames
from server.services.telnyx_client import TelnyxClient


def test_dial_uses_rtp_bidirectional_and_both_legs():
    client = TelnyxClient(
        cfg={
            "api_key": "test",
            "connection_id": "conn",
            "phone_number": "+15551234567",
        }
    )
    import inspect

    src = inspect.getsource(client.create_outbound_call)
    assert 'bidirectional_mode: str = "rtp"' in src
    assert '"stream_bidirectional_mode": bidirectional_mode' in src
    assert 'target_legs: str = "self"' in src
    assert '"stream_codec": TELNYX_RTP_CODEC' in src
    assert '"stream_bidirectional_codec": TELNYX_RTP_CODEC' in src
    assert "TELNYX_RTP_SAMPLE_RATE" in src
    assert '"send_silence_when_idle": True' in src
    assert "if stream_url:" in src
    assert 'stream_url: str | None = None' in src


def test_pcm16_to_mulaw_frame_size():
    # 20ms @ 16kHz mono PCM16 → one 160-byte μ-law frame @ 8kHz
    pcm = b"\x00\x01" * 320
    frames = pcm16_chunk_to_mulaw_frames(pcm, sample_rate=16000, frame_ms=20)
    assert len(frames) == 1
    assert len(frames[0]) == 160
    back = mulaw_to_pcm16(frames[0], target_rate=16000)
    assert len(back) > 0
