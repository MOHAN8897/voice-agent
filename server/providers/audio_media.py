"""Audio media validation shared by provider adapters."""

from __future__ import annotations

import io
import struct
import wave
from dataclasses import dataclass


@dataclass(frozen=True)
class PcmWavMetadata:
    sample_rate: int
    channels: int
    sample_width_bytes: int
    frame_count: int


def parse_pcm16_wav(audio: bytes, *, require_mono: bool = True) -> PcmWavMetadata:
    """Validate a complete PCM16 WAV and return its actual media parameters."""
    if not isinstance(audio, bytes) or len(audio) < 44:
        raise ValueError("Provider returned an empty or truncated WAV file")
    if audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise ValueError("Provider returned audio without a RIFF/WAVE container")

    try:
        with wave.open(io.BytesIO(audio), "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            sample_rate = wav.getframerate()
            frame_count = wav.getnframes()
            compression = wav.getcomptype()
    except (EOFError, OSError, struct.error, wave.Error) as exc:
        raise ValueError("Provider returned a malformed WAV file") from exc

    try:
        with wave.open(io.BytesIO(audio), "rb") as wav:
            pcm = wav.readframes(frame_count)
    except (EOFError, OSError, struct.error, wave.Error) as exc:
        raise ValueError("Provider returned a malformed WAV file") from exc

    if compression != "NONE" or sample_width != 2:
        raise ValueError("Provider WAV must contain uncompressed PCM16 audio")
    if require_mono and channels != 1:
        raise ValueError("Provider WAV must contain mono audio")
    if sample_rate <= 0 or frame_count <= 0:
        raise ValueError("Provider WAV must contain audio frames and a valid sample rate")
    if len(pcm) != frame_count * channels * sample_width:
        raise ValueError("Provider WAV frame data is truncated")

    return PcmWavMetadata(
        sample_rate=sample_rate,
        channels=channels,
        sample_width_bytes=sample_width,
        frame_count=frame_count,
    )


def decode_pcm16_wav(audio: bytes, *, require_mono: bool = True) -> tuple[bytes, PcmWavMetadata]:
    """Return validated PCM frames and the media parameters from a WAV response."""
    metadata = parse_pcm16_wav(audio, require_mono=require_mono)
    try:
        with wave.open(io.BytesIO(audio), "rb") as wav:
            pcm = wav.readframes(metadata.frame_count)
    except (EOFError, OSError, struct.error, wave.Error) as exc:
        raise ValueError("Provider returned a malformed WAV file") from exc
    return pcm, metadata
