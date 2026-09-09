"""PSTN TTS resample continuity — chipmunk / crackle guards."""
from __future__ import annotations

import audioop

from server.services.audio_transcode import StreamingPcmResampler, pcm_resample
from server.services.pstn_turn_tts import _tts_config_sample_rate


def _tone(rate: int, ms: int = 100, freq: float = 440.0) -> bytes:
    import math
    import struct

    n = int(rate * ms / 1000)
    samples = [
        int(16000 * math.sin(2 * math.pi * freq * i / rate)) for i in range(n)
    ]
    return struct.pack(f"<{n}h", *samples)


def test_streaming_resampler_matches_oneshot_length():
    pcm16 = _tone(16000, ms=200)
    one = pcm_resample(pcm16, 16000, 8000)
    stream = StreamingPcmResampler(16000, 8000)
    # Feed in small uneven chunks (mimic Cartesia WS).
    out = bytearray()
    step = 641  # odd byte sizes to exercise residue
    for i in range(0, len(pcm16), step):
        out.extend(stream.feed(pcm16[i : i + step]))
    out.extend(stream.flush())
    # Length within one sample of oneshot (ratecv filter delay).
    assert abs(len(out) - len(one)) <= 4
    assert len(out) > 0


def test_streaming_resampler_state_avoids_empty_on_tiny_chunks():
    pcm16 = _tone(16000, ms=40)
    stream = StreamingPcmResampler(16000, 8000)
    pieces = [stream.feed(pcm16[i : i + 64]) for i in range(0, len(pcm16), 64)]
    pieces.append(stream.flush())
    joined = b"".join(pieces)
    assert len(joined) >= 80  # ~20ms @ 8k PCM16
    # μ-law encode should succeed without rate mislabel.
    mulaw = audioop.lin2ulaw(joined, 2)
    assert len(mulaw) == len(joined) // 2


def test_tts_config_sample_rate_prefers_speech_sample_rate():
    assert _tts_config_sample_rate({"speech_sample_rate": "16000"}, fallback=8000) == 16000
    assert _tts_config_sample_rate({"sample_rate": 16000}, fallback=8000) == 16000
    assert _tts_config_sample_rate({}, fallback=8000) == 8000


def test_mislabelled_16k_as_8k_is_half_duration():
    """Document the chipmunk bug: 16 kHz PCM treated as 8 kHz halves duration."""
    pcm16 = _tone(16000, ms=100)
    wrong = audioop.lin2ulaw(pcm16, 2)  # no downsample
    right_pcm = pcm_resample(pcm16, 16000, 8000)
    right = audioop.lin2ulaw(right_pcm, 2)
    assert len(wrong) == 2 * len(right)
