"""μ-law 8kHz ↔ PCM 16kHz transcoding for Plivo PSTN — Phase 5."""
from __future__ import annotations

import audioop
import struct

_MULAW_BIAS = 0x84
_MULAW_CLIP = 32635


def pcm16_to_mulaw(pcm16: bytes, sample_rate: int = 16000) -> bytes:
    """PCM 16-bit mono → μ-law 8kHz mono."""
    if sample_rate != 8000:
        pcm8k, _ = audioop.ratecv(pcm16, 2, 1, sample_rate, 8000, None)
    else:
        pcm8k = pcm16
    return audioop.lin2ulaw(pcm8k, 2)


def mulaw_to_pcm16(mulaw: bytes, target_rate: int = 16000) -> bytes:
    """μ-law 8kHz mono → PCM 16-bit mono at target_rate."""
    pcm8k = audioop.ulaw2lin(mulaw, 2)
    if target_rate != 8000:
        pcm, _ = audioop.ratecv(pcm8k, 2, 1, 8000, target_rate, None)
        return pcm
    return pcm8k


def mulaw_frame_to_pcm16(frame: bytes) -> bytes:
    return mulaw_to_pcm16(frame, 16000)


def pcm16_chunk_to_mulaw_frames(pcm16: bytes, sample_rate: int = 16000, frame_ms: int = 20) -> list[bytes]:
    """Split PCM into 20ms μ-law frames for Plivo playAudio."""
    if sample_rate != 8000:
        pcm8k, _ = audioop.ratecv(pcm16, 2, 1, sample_rate, 8000, None)
    else:
        pcm8k = pcm16
    samples_per_frame = int(8000 * frame_ms / 1000)
    bytes_per_frame = samples_per_frame * 2
    frames: list[bytes] = []
    for i in range(0, len(pcm8k), bytes_per_frame):
        chunk = pcm8k[i:i + bytes_per_frame]
        if len(chunk) < bytes_per_frame:
            chunk = chunk + b"\x00" * (bytes_per_frame - len(chunk))
        frames.append(audioop.lin2ulaw(chunk, 2))
    return frames


def encode_mulaw_base64(mulaw: bytes) -> str:
    import base64

    return base64.b64encode(mulaw).decode("ascii")
