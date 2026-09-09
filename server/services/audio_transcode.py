"""μ-law 8kHz ↔ PCM 16kHz and linear PCM resampling for PSTN — Phase 5.

NOTE (7.2): For inbound hot-path (per-frame) resampling, prefer
StreamingPcmResampler which carries ratecv state across chunks to avoid
boundary discontinuities. One-shot pcm_resample() is for cold-path only.
"""
from __future__ import annotations

import math
import warnings
from typing import Any

# audioop is deprecated since Python 3.11 and removed in Python 3.13.
# Provide a graceful import with a clear warning so the server doesn't crash.
try:
    import audioop  # type: ignore[import-untyped]
except ImportError:  # Python 3.13+
    warnings.warn(
        "audioop has been removed in Python 3.13+. Install the "
        "'audioop-lts' backport package: pip install audioop-lts",
        DeprecationWarning,
        stacklevel=2,
    )
    try:
        import audioop_lts as audioop  # type: ignore[import-untyped,no-redef]
    except ImportError:
        raise ImportError(
            "audioop is unavailable and 'audioop-lts' is not installed. "
            "Run: pip install audioop-lts"
        )


class StreamingPcmResampler:
    """
    Stateful PCM16 mono resampler for streaming TTS chunks.

    Keeping audioop.ratecv state across chunks avoids boundary clicks/crackles.
    Also carries a trailing odd byte so Int16 frames stay aligned.
    """

    def __init__(self, from_rate: int, to_rate: int) -> None:
        self.from_rate = int(from_rate)
        self.to_rate = int(to_rate)
        self._state: Any = None
        self._odd = b""
        self._filters = self._make_lowpass()

    def _make_lowpass(self) -> list[list[float]]:
        """Sixth-order Butterworth anti-alias filter, with state across packets."""
        if self.from_rate <= self.to_rate:
            return []
        import math

        omega = 2 * math.pi * (0.42 * self.to_rate) / self.from_rate
        cosine, sine = math.cos(omega), math.sin(omega)
        sections = []
        for q in (0.5176380902, 0.7071067812, 1.9318516526):
            alpha = sine / (2 * q)
            a0 = 1 + alpha
            b0 = (1 - cosine) / (2 * a0)
            sections.append([b0, 2 * b0, b0, -2 * cosine / a0, (1 - alpha) / a0, 0.0, 0.0])
        return sections

    def _filter_pcm(self, data: bytes) -> bytes:
        if not self._filters:
            return data
        import struct
        from array import array
        import sys

        result = array("h")
        for (sample,) in struct.iter_unpack("<h", data):
            value = float(sample)
            for section in self._filters:
                b0, b1, b2, a1, a2, z1, z2 = section
                out = b0 * value + z1
                section[5] = b1 * value - a1 * out + z2
                section[6] = b2 * value - a2 * out
                value = out
            result.append(max(-32768, min(32767, round(value))))
        if sys.byteorder != "little":
            result.byteswap()
        return result.tobytes()

    def reset(self, *, from_rate: int | None = None, to_rate: int | None = None) -> None:
        if from_rate is not None:
            self.from_rate = int(from_rate)
        if to_rate is not None:
            self.to_rate = int(to_rate)
        self._state = None
        self._odd = b""
        self._filters = self._make_lowpass()

    def feed(self, pcm16: bytes) -> bytes:
        if not pcm16 and not self._odd:
            return b""
        data = self._odd + (pcm16 or b"")
        if len(data) % 2:
            self._odd = data[-1:]
            data = data[:-1]
        else:
            self._odd = b""
        if not data:
            return b""
        if self.from_rate == self.to_rate:
            return data
        out, self._state = audioop.ratecv(self._filter_pcm(data), 2, 1, self.from_rate, self.to_rate, self._state)
        return out

    def flush(self) -> bytes:
        if not self._odd:
            return b""
        data = self._odd + b"\x00"
        self._odd = b""
        if self.from_rate == self.to_rate:
            return data
        out, self._state = audioop.ratecv(self._filter_pcm(data), 2, 1, self.from_rate, self.to_rate, self._state)
        return out


def pcm16_to_mulaw(pcm16: bytes, sample_rate: int = 16000) -> bytes:
    """PCM 16-bit mono → μ-law 8kHz mono."""
    if sample_rate != 8000:
        pcm8k = pcm_resample(pcm16, sample_rate, 8000)
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
        return pcm_resample(pcm8k, 8000, target_rate)
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


def pcm16_rms(pcm16: bytes) -> int:
    """Mono PCM16 RMS energy (0..32768)."""
    if len(pcm16) < 2:
        return 0
    return int(audioop.rms(pcm16, 2))


def pcm16_dbfs(pcm16: bytes) -> float | None:
    """Approximate mono PCM16 RMS level in dBFS."""
    if len(pcm16) < 2:
        return None
    rms = pcm16_rms(pcm16)
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
    pcm8k = pcm_resample(pcm16, sample_rate, 8000) if sample_rate != 8000 else pcm16
    samples_per_frame = int(8000 * frame_ms / 1000)
    bytes_per_frame = samples_per_frame * 2
    frames: list[bytes] = []
    for i in range(0, len(pcm8k), bytes_per_frame):
        chunk = pcm8k[i : i + bytes_per_frame]
        if len(chunk) < bytes_per_frame:
            chunk = chunk + b"\x00" * (bytes_per_frame - len(chunk))
        frames.append(audioop.lin2ulaw(chunk, 2))
    return frames


def encode_mulaw_base64(mulaw: bytes) -> str:
    import base64

    return base64.b64encode(mulaw).decode("ascii")


def pcm_resample(pcm16: bytes, from_rate: int, to_rate: int) -> bytes:
    """PCM 16-bit mono resample (one-shot; prefer StreamingPcmResampler for chunks)."""
    if from_rate == to_rate or not pcm16:
        return pcm16
    if len(pcm16) % 2 != 0:
        pcm16 = pcm16 + b"\x00"
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
