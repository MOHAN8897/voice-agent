"""Telnyx outbound L16 wire — TEST 5 offline gates."""
from __future__ import annotations

from server.services.telnyx_client import TELNYX_RTP_CODEC, TELNYX_RTP_SAMPLE_RATE
from server.services.telnyx_pstn_bridge import _chunk_l16_rtp

FRAME_BYTES = int(TELNYX_RTP_SAMPLE_RATE * 20 / 1000) * 2


def test_telnyx_rtp_constants():
    assert TELNYX_RTP_CODEC == "L16"
    assert TELNYX_RTP_SAMPLE_RATE == 16000
    assert FRAME_BYTES == 640


def test_l16_rtp_chunks_match_telnyx_frame_size():
    # Simulates TTS PCM fed into bridge outbound path (L16 -> L16).
    pcm = b"\x01\x02" * (FRAME_BYTES // 2 * 5 + 100)
    frames = _chunk_l16_rtp(pcm, sample_rate=TELNYX_RTP_SAMPLE_RATE)
    assert len(frames) == 6
    assert all(len(f) == FRAME_BYTES for f in frames)


def test_l16_same_codec_no_transcode_path():
    """Bridge uses source_chunks unchanged when source_codec == target_codec == L16."""
    pcm = b"\x00\x00" * (FRAME_BYTES // 2)
    chunks = _chunk_l16_rtp(pcm, TELNYX_RTP_SAMPLE_RATE)
    assert len(chunks) == 1
    assert len(chunks[0]) == FRAME_BYTES
    assert chunks[0] == pcm
