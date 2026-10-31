"""Speech-aware loudness levelling for call recordings.

Each speaker's track is levelled on its own, so a quiet caller and a loud TTS
agent land at the same listening level. Gain follows the speech (a slow,
utterance-scale AGC), stays near unity in the gaps so line hiss is not pumped
up, and a look-ahead peak limiter keeps every sample under the ceiling.

Stdlib only (audioop + wave): the API image has no numpy, and a 4-minute call
levels in well under a second.
"""
from __future__ import annotations

import io
import math
import shutil
import subprocess
import tempfile
import warnings
import wave
from pathlib import Path

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    try:
        import audioop  # type: ignore[import-untyped]
    except ImportError:  # Python 3.13+ ships it as the audioop-lts backport
        import audioop_lts as audioop  # type: ignore[import-untyped,no-redef]

from server.utils.logger import logger

FULL_SCALE = 32767
#: Speech RMS each speaker is levelled to; lands around -17 LUFS on phone speech.
TARGET_DBFS = -20.0
MAX_GAIN_DB = 24.0
MIN_GAIN_DB = -12.0
#: Gaps between words get at most this much gain, so line noise stays put.
NOISE_MAX_GAIN_DB = 3.0
CEILING_DBFS = -1.0
#: A 10 ms frame is speech when it clears both the absolute and the noise-relative gate.
GATE_ABS_DBFS = -50.0
GATE_ABOVE_FLOOR_DB = 12.0
#: Speech gain carries this far past a word (tails) and this far before it (onsets).
HANGOVER_MS = 200
ONSET_MS = 50
#: Level is measured over this much speech either side, pulled toward the call-wide level.
WINDOW_MS = 1500
PRIOR_MS = 500
#: Largest gain change between consecutive 10 ms frames.
SLEW_DB_PER_FRAME = 3.0
_SUBCHUNKS = 4


def _gain(db: float) -> float:
    return 10.0 ** (db / 20.0)


def _dbfs(value: float) -> float:
    return 20.0 * math.log10(value / FULL_SCALE) if value > 0 else float("-inf")


def _frames(pcm: bytes, rate: int) -> list[bytes]:
    step = max(1, rate // 100) * 2
    return [pcm[i : i + step] for i in range(0, len(pcm), step)]


def _speech_mask(rms: list[int]) -> list[bool]:
    if not rms:
        return []
    floor = sorted(rms)[len(rms) // 10]
    abs_gate = FULL_SCALE * _gain(GATE_ABS_DBFS)
    gate = max(abs_gate, floor * _gain(GATE_ABOVE_FLOOR_DB))
    mask = [r >= gate for r in rms]
    if not any(mask):
        # A steady signal has no noise floor to stand out from; take it whole.
        mask = [r >= abs_gate for r in rms]
    return mask


def speech_stats(pcm: bytes, rate: int) -> dict[str, float]:
    """Speech RMS, peak and noise floor of one mono PCM16 track, in dBFS."""
    pcm = pcm[: len(pcm) // 2 * 2]
    frames = _frames(pcm, rate)
    rms = [audioop.rms(f, 2) for f in frames]
    mask = _speech_mask(rms)
    speech = [r * r for r, m in zip(rms, mask) if m]
    level = math.sqrt(sum(speech) / len(speech)) if speech else 0.0
    return {
        "speech_dbfs": round(_dbfs(level), 1),
        "peak_dbfs": round(_dbfs(audioop.max(pcm, 2)) if pcm else float("-inf"), 1),
        "noise_dbfs": round(_dbfs(sorted(rms)[len(rms) // 10]) if rms else float("-inf"), 1),
        "speech_pct": round(100.0 * len(speech) / max(1, len(rms)), 1),
    }


def level_speech_pcm16(pcm: bytes, rate: int, *, target_dbfs: float = TARGET_DBFS) -> bytes:
    """Level one mono PCM16 speaker track to ``target_dbfs`` speech RMS without clipping."""
    pcm = pcm[: len(pcm) // 2 * 2]
    if not pcm:
        return pcm
    frames = _frames(pcm, rate)
    count = len(frames)
    rms = [audioop.rms(f, 2) for f in frames]
    peaks = [audioop.max(f, 2) for f in frames]
    speech = _speech_mask(rms)
    if not any(speech):
        return pcm

    # Speech-weighted level over a sliding window, blended toward the call-wide
    # level so a lone word does not get its own extreme gain.
    power = [r * r if s else 0 for r, s in zip(rms, speech)]
    speech_count = sum(speech)
    global_power = sum(power) / speech_count
    prior = PRIOR_MS // 10
    half = WINDOW_MS // 10
    p_sum = [0] * (count + 1)
    c_sum = [0] * (count + 1)
    for i in range(count):
        p_sum[i + 1] = p_sum[i] + power[i]
        c_sum[i + 1] = c_sum[i] + (1 if speech[i] else 0)

    hang_after = HANGOVER_MS // 10
    hang_before = ONSET_MS // 10
    active = [False] * count
    last = -(10**9)
    for i in range(count):
        if speech[i]:
            last = i
        active[i] = i - last <= hang_after
    nxt = 10**9
    for i in range(count - 1, -1, -1):
        if speech[i]:
            nxt = i
        if nxt - i <= hang_before:
            active[i] = True

    target = FULL_SCALE * _gain(target_dbfs)
    lo, hi, noise_hi = _gain(MIN_GAIN_DB), _gain(MAX_GAIN_DB), _gain(NOISE_MAX_GAIN_DB)
    ceiling = FULL_SCALE * _gain(CEILING_DBFS)
    gains = [1.0] * count
    for i in range(count):
        a, b = max(0, i - half), min(count, i + half + 1)
        level = math.sqrt((p_sum[b] - p_sum[a] + prior * global_power) / (c_sum[b] - c_sum[a] + prior))
        g = min(hi, max(lo, target / level)) if level > 0 else 1.0
        if not active[i]:
            g = min(g, noise_hi)
        # Limiter bound covers this frame and the previous one, because frame
        # i-1 ramps toward gains[i] over its length.
        peak = max(peaks[i], peaks[i - 1] if i else 0)
        if peak > 0:
            g = min(g, ceiling / peak)
        gains[i] = g

    # Slew limits in both directions only ever lower gain, so the limiter bound holds.
    up = _gain(SLEW_DB_PER_FRAME)
    for i in range(1, count):
        gains[i] = min(gains[i], gains[i - 1] * up)
    for i in range(count - 2, -1, -1):
        gains[i] = min(gains[i], gains[i + 1] * up)

    out = []
    for i, frame in enumerate(frames):
        g0 = gains[i]
        g1 = gains[i + 1] if i + 1 < count else g0
        if abs(g1 - g0) < 1e-4 or len(frame) < _SUBCHUNKS * 2:
            out.append(audioop.mul(frame, 2, g0))
            continue
        step = len(frame) // 2 // _SUBCHUNKS * 2
        ratio = g1 / g0
        for k in range(_SUBCHUNKS):
            part = frame[k * step : (k + 1) * step if k < _SUBCHUNKS - 1 else len(frame)]
            out.append(audioop.mul(part, 2, g0 * ratio ** (k / _SUBCHUNKS)))
    return b"".join(out)


def level_interleaved_pcm16(pcm: bytes, rate: int, channels: int) -> bytes:
    """Level each channel of interleaved PCM16 on its own (L=caller, R=agent on calls)."""
    if channels <= 1:
        return level_speech_pcm16(pcm, rate)
    if channels != 2:
        return pcm
    pcm = pcm[: len(pcm) // 4 * 4]
    left = level_speech_pcm16(audioop.tomono(pcm, 2, 1, 0), rate)
    right = level_speech_pcm16(audioop.tomono(pcm, 2, 0, 1), rate)
    return audioop.add(audioop.tostereo(left, 2, 1, 0), audioop.tostereo(right, 2, 0, 1), 2)


def read_pcm16(path: Path) -> tuple[bytes, int, int] | None:
    """Decode a recording to interleaved PCM16: (pcm, rate, channels), or None."""
    try:
        with wave.open(str(path), "rb") as wf:
            width, rate, channels = wf.getsampwidth(), wf.getframerate(), wf.getnchannels()
            raw = wf.readframes(wf.getnframes())
        if width == 1:
            raw = audioop.bias(raw, 1, -128)  # 8-bit WAV is unsigned
        if width != 2:
            raw = audioop.lin2lin(raw, width, 2)
        return raw, rate, channels
    except (wave.Error, EOFError):
        pass
    except OSError:
        return None
    return _decode_pyav(path) or _decode_ffmpeg(path)


def _decode_pyav(path: Path) -> tuple[bytes, int, int] | None:
    try:
        import av
    except ImportError:
        return None
    try:
        with av.open(str(path)) as container:
            stream = container.streams.audio[0]
            channels = min(2, stream.channels or 1)
            rate = stream.rate
            resampler = av.AudioResampler(format="s16", layout="stereo" if channels == 2 else "mono", rate=rate)
            buf = bytearray()
            for frame in container.decode(stream):
                for out in resampler.resample(frame):
                    buf.extend(bytes(out.planes[0])[: out.samples * channels * 2])
            for out in resampler.resample(None):
                buf.extend(bytes(out.planes[0])[: out.samples * channels * 2])
        return bytes(buf), rate, channels
    except Exception as exc:
        logger.warning("[AUDIO] PyAV decode failed for %s: %s", path.name, str(exc)[:200])
        return None


def _decode_ffmpeg(path: Path) -> tuple[bytes, int, int] | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "decoded.wav"
        try:
            subprocess.run(
                [ffmpeg, "-v", "error", "-y", "-i", str(path), "-acodec", "pcm_s16le", str(dest)],
                check=True,
                capture_output=True,
                timeout=120,
            )
            with wave.open(str(dest), "rb") as wf:
                return wf.readframes(wf.getnframes()), wf.getframerate(), wf.getnchannels()
        except Exception as exc:
            logger.warning("[AUDIO] ffmpeg decode failed for %s: %s", path.name, str(exc)[:200])
            return None


def write_pcm16_wav(dest: Path, pcm: bytes, rate: int, channels: int) -> None:
    """Write via a sibling temp file and an atomic replace, so readers never see half a file."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm)
    tmp = dest.with_name(f"{dest.name}.{id(buf):x}.part")
    tmp.write_bytes(buf.getvalue())
    tmp.replace(dest)
