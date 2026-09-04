"""μ-law 8kHz ↔ PCM 16kHz and linear PCM resampling for PSTN — Phase 5."""
from __future__ import annotations

import audioop
import math


def pcm16_to_mulaw(pcm16: bytes, sample_rate: int = 16000) -> bytes:
    """PCM 16-bit mono → μ-law 8kHz mono."""
    if sample_rate != 8000:
        pcm8k, _ = audioop.ratecv(pcm16, 2, 1, sample_rate, 8000, None)
    else:
        pcm8k = pcm16
    return audioop.lin2ulaw(pcm8k, 2)


def pcm16_to_alaw(pcm16: bytes, sample_rate: int = 8000) -> bytes:
    """PCM16 mono → G.711 A-law at 8 kHz."""
    pcm8k = pcm_resample(pcm16, sample_rate, 8000)
    return audioop.lin2alaw(pcm8k, 2)


def mulaw_to_pcm16(mulaw: bytes, target_rate: int = 16000) -> bytes:
    """μ-law 8kHz mono → PCM 16-bit mono at target_rate."""
    pcm8k = audioop.ulaw2lin(mulaw, 2)
    if target_rate != 8000:
        pcm, _ = audioop.ratecv(pcm8k, 2, 1, 8000, target_rate, None)
        return pcm
    return pcm8k


def alaw_to_pcm16(alaw: bytes, target_rate: int = 8000) -> bytes:
    """G.711 A-law 8 kHz mono → PCM16 mono."""
    pcm8k = audioop.alaw2lin(alaw, 2)
    return pcm_resample(pcm8k, 8000, target_rate)


def convert_g711(data: bytes, source_codec: str, target_codec: str) -> bytes:
    """Convert raw G.711 payloads without relabelling encoded bytes."""
    source = source_codec.upper()
    target = target_codec.upper()
    if source == target:
        return data
    if source not in {"PCMU", "PCMA"} or target not in {"PCMU", "PCMA"}:
        raise ValueError(f"unsupported G.711 conversion {source}->{target}")
    pcm = mulaw_to_pcm16(data, 8000) if source == "PCMU" else alaw_to_pcm16(data, 8000)
    return pcm16_to_mulaw(pcm, 8000) if target == "PCMU" else pcm16_to_alaw(pcm, 8000)


def pcm16_dbfs(pcm16: bytes) -> float | None:
    """Approximate mono PCM16 RMS level in dBFS."""
    if len(pcm16) < 2:
        return None
    rms = audioop.rms(pcm16, 2)
    if rms <= 0:
        return -96.0
    return max(-96.0, 20.0 * math.log10(rms / 32768.0))


def g711_dbfs(data: bytes, codec: str) -> float | None:
    normalized = codec.upper()
    if normalized == "PCMU":
        return pcm16_dbfs(mulaw_to_pcm16(data, 8000))
    if normalized == "PCMA":
        return pcm16_dbfs(alaw_to_pcm16(data, 8000))
    raise ValueError(f"unsupported G.711 codec {codec}")


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


def pcm_resample(pcm16: bytes, from_rate: int, to_rate: int) -> bytes:
    """PCM 16-bit mono resample."""
    if from_rate == to_rate or not pcm16:
        return pcm16
    out, _ = audioop.ratecv(pcm16, 2, 1, from_rate, to_rate, None)
    return out


def pcm8k_to_pcm16k(pcm8k: bytes) -> bytes:
    return pcm_resample(pcm8k, 8000, 16000)


def pcm16k_to_pcm8k(pcm16k: bytes) -> bytes:
    return pcm_resample(pcm16k, 16000, 8000)


def chunk_mulaw_frames(
    mulaw: bytes,
    *,
    sample_rate: int = 8000,
    frame_ms: int = 20,
) -> list[bytes]:
    """Split μ-law bytes into fixed RTP frames (160 bytes = 20 ms @ 8 kHz)."""
    frame_bytes = int(sample_rate * frame_ms / 1000)
    frames: list[bytes] = []
    for i in range(0, len(mulaw), frame_bytes):
        chunk = mulaw[i : i + frame_bytes]
        if len(chunk) < frame_bytes:
            chunk = chunk + b"\xff" * (frame_bytes - len(chunk))
        frames.append(chunk)
    return frames


def chunk_pcm16_frames(
    pcm16: bytes,
    *,
    sample_rate: int = 8000,
    frame_ms: int = 20,
) -> list[bytes]:
    """Split PCM16 mono into fixed frames."""
    frame_bytes = int(sample_rate * frame_ms / 1000) * 2
    frames: list[bytes] = []
    for i in range(0, len(pcm16), frame_bytes):
        chunk = pcm16[i : i + frame_bytes]
        if len(chunk) < frame_bytes:
            chunk = chunk + b"\x00" * (frame_bytes - len(chunk))
        frames.append(chunk)
    return frames


def chunk_pcm_for_exotel(pcm8k: bytes, frame_bytes: int = 3200) -> list[bytes]:
    """Split PCM 8k into Exotel-safe chunks (multiples of 320 bytes)."""
    frame_bytes = max(320, (frame_bytes // 320) * 320)
    chunks: list[bytes] = []
    for i in range(0, len(pcm8k), frame_bytes):
        chunk = pcm8k[i : i + frame_bytes]
        if len(chunk) < 320:
            continue
        rem = len(chunk) % 320
        if rem:
            chunk += b"\x00" * (320 - rem)
        chunks.append(chunk)
    return chunks


def pcm16_to_mulaw_8k(pcm16: bytes, *, source_rate: int = 8000) -> bytes:
    """PCM16 mono → μ-law 8 kHz for Telnyx PCMU RTP (pads odd byte tails)."""
    if not pcm16:
        return pcm16
    if len(pcm16) % 2 != 0:
        pcm16 = pcm16 + b"\x00"
    return pcm16_to_mulaw(pcm16, source_rate)
