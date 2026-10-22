"""PSTN L16 @ 16 kHz frame sizing — offline TEST 4 gates."""
from __future__ import annotations

from server.services.audio_transcode import chunk_pcm16_frames
from server.services.telnyx_client import TELNYX_RTP_SAMPLE_RATE
from server.services.telnyx_pstn_bridge import _chunk_l16_rtp

FRAME_BYTES = int(TELNYX_RTP_SAMPLE_RATE * 20 / 1000) * 2  # 640


def test_l16_frame_bytes_constant():
    assert FRAME_BYTES == 640


def test_chunk_pcm16_frames_exact_multiples():
    pcm = b"\x00\x01" * (FRAME_BYTES // 2) * 3
    frames = chunk_pcm16_frames(pcm, sample_rate=TELNYX_RTP_SAMPLE_RATE)
    assert len(frames) == 3
    assert all(len(f) == FRAME_BYTES for f in frames)


def test_chunk_pcm16_frames_zero_pads_tail():
    pcm = b"\x00\x01" * (FRAME_BYTES // 2 + 100)
    frames = chunk_pcm16_frames(pcm, sample_rate=TELNYX_RTP_SAMPLE_RATE)
    assert len(frames) == 2
    assert len(frames[0]) == FRAME_BYTES
    assert len(frames[1]) == FRAME_BYTES
    assert frames[1].endswith(b"\x00" * (FRAME_BYTES - 200))


def test_chunk_l16_rtp_matches_audio_transcode_chunker():
    pcm = b"\xab\xcd" * (FRAME_BYTES // 2 + 50)
    a = chunk_pcm16_frames(pcm, sample_rate=TELNYX_RTP_SAMPLE_RATE)
    b = _chunk_l16_rtp(pcm, sample_rate=TELNYX_RTP_SAMPLE_RATE)
    assert len(a) == len(b)
    assert a == b


def test_merge_pstn_tts_config_cartesia_l16_16k(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ENABLE_CARTESIA", "true")
    monkeypatch.setenv("CARTESIA_API_KEY", "cartesia-test")
    from server.config.env import get_settings
    from server.services.tts_config import merge_pstn_tts_config

    get_settings.cache_clear()
    voice = "4418bb06-8329-49a1-bb11-53bb64ca0547"
    cfg = merge_pstn_tts_config(
        "test-studio",
        {"speaker": voice},
        call_id=None,
        ws_model="sonic-3.5",
        wire_mode="rtp_l16",
    )
    assert cfg.get("provider") == "cartesia"
    assert cfg["output_audio_codec"] == "linear16"
    assert cfg["speech_sample_rate"] == "16000"
    assert cfg.get("sample_rate") == 16000
