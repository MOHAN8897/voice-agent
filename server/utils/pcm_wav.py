"""PCM int16 mono → WAV container for browser playback."""
from __future__ import annotations

import io
import wave


def pcm16_to_wav(pcm: bytes, *, sample_rate: int = 16000) -> bytes:
    if not pcm:
        pcm = b"\x00\x00"
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()
