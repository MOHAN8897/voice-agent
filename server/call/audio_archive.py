"""Audio archive — user PCM, agent stream, post-call stereo mix.wav."""
from __future__ import annotations

import array
import asyncio
import io
import wave
from pathlib import Path

from server.call.paths import call_dir
from server.config.constants import constants
from server.config.env import get_settings

SAMPLE_RATE = constants.PREFERRED_SAMPLE_RATE  # 16 kHz user PCM
_AGENT_PCM_RATE = 24000  # Sarvam bulbul WS linear16 default
_locks: dict[str, asyncio.Lock] = {}
_user_buffers: dict[str, bytearray] = {}
_agent_buffers: dict[str, bytearray] = {}
_agent_rates: dict[str, int] = {}


def _lock(call_id: str) -> asyncio.Lock:
    if call_id not in _locks:
        _locks[call_id] = asyncio.Lock()
    return _locks[call_id]


def _is_mpeg(data: bytes) -> bool:
    if len(data) < 3:
        return False
    if data[:3] == b"ID3":
        return True
    return data[0] == 0xFF and (data[1] & 0xE0) == 0xE0


def _resample_int16_mono(pcm: bytes, src_rate: int, dst_rate: int) -> bytes:
    if src_rate == dst_rate or src_rate <= 0 or not pcm:
        return pcm
    src_count = len(pcm) // 2
    if src_count == 0:
        return b""
    dst_count = max(1, int(src_count * dst_rate / src_rate))
    out = bytearray(dst_count * 2)
    for i in range(dst_count):
        src_pos = i * (src_count - 1) / max(dst_count - 1, 1)
        idx = int(src_pos)
        frac = src_pos - idx
        s0 = int.from_bytes(pcm[idx * 2 : idx * 2 + 2], "little", signed=True)
        s1 = s0
        if idx + 1 < src_count:
            s1 = int.from_bytes(pcm[(idx + 1) * 2 : (idx + 1) * 2 + 2], "little", signed=True)
        sample = int(s0 + (s1 - s0) * frac)
        sample = max(-32768, min(32767, sample))
        out[i * 2 : i * 2 + 2] = sample.to_bytes(2, "little", signed=True)
    return bytes(out)


def _strip_wav_pcm(data: bytes, default_rate: int) -> tuple[bytes, int]:
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        try:
            with wave.open(io.BytesIO(data), "rb") as wf:
                return wf.readframes(wf.getnframes()), wf.getframerate()
        except Exception:
            return data, default_rate
    return data, default_rate


def _speech_peak_pcm16(pcm: bytes, *, percentile: float = 0.95) -> int:
    """Typical speech peak, ignoring a few clicks that would otherwise block gain."""
    frame_count = len(pcm) // 2
    if frame_count == 0:
        return 0
    values = [
        abs(int.from_bytes(pcm[i * 2 : i * 2 + 2], "little", signed=True))
        for i in range(frame_count)
    ]
    values.sort()
    idx = min(frame_count - 1, max(0, int(frame_count * percentile) - 1))
    return values[idx]


def _peak_normalize_pcm16(
    pcm: bytes,
    *,
    target_peak: int = 31000,
    max_gain: float = 24.0,
) -> bytes:
    """Boost quiet PSTN speech toward a comfortable listening level.

    Uses the 95th-percentile peak so one loud click cannot freeze gain at 1×.
    """
    if not pcm or len(pcm) < 2:
        return pcm
    speech_peak = _speech_peak_pcm16(pcm)
    if speech_peak == 0:
        return pcm
    gain = min(max_gain, target_peak / speech_peak)
    if gain <= 1.02:
        return pcm
    out = bytearray(len(pcm))
    frame_count = len(pcm) // 2
    for i in range(frame_count):
        sample = int.from_bytes(pcm[i * 2 : i * 2 + 2], "little", signed=True)
        boosted = int(sample * gain)
        boosted = max(-32768, min(32767, boosted))
        out[i * 2 : i * 2 + 2] = boosted.to_bytes(2, "little", signed=True)
    return bytes(out)


def _write_pcm16_wav(dest: Path, pcm: bytes, sample_rate: int, *, normalize: bool = False) -> None:
    body = _peak_normalize_pcm16(pcm) if normalize and pcm else (pcm or b"")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate) if sample_rate > 0 else SAMPLE_RATE)
        wf.writeframes(body)
    dest.write_bytes(buf.getvalue())


def _write_pcm16_stereo_wav(dest: Path, interleaved: bytes, sample_rate: int) -> None:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate) if sample_rate > 0 else SAMPLE_RATE)
        wf.writeframes(interleaved or b"")
    dest.write_bytes(buf.getvalue())


def _wav_header_channels(data: bytes) -> int:
    if len(data) >= 24 and data[8:12] == b"WAVE":
        return int.from_bytes(data[22:24], "little")
    return 0


class AudioArchive:
    def user_pcm_path(self, call_id: str) -> Path:
        return call_dir(call_id) / "user.pcm"

    def agent_mp3_path(self, call_id: str) -> Path:
        return call_dir(call_id) / "agent.mp3"

    def agent_pcm_path(self, call_id: str) -> Path:
        return call_dir(call_id) / "agent.pcm"

    def agent_path(self, call_id: str) -> Path:
        pcm = self.agent_pcm_path(call_id)
        if pcm.exists():
            return pcm
        return self.agent_mp3_path(call_id)

    def mix_path(self, call_id: str) -> Path:
        return call_dir(call_id) / "mix.wav"

    def mix_clear_path(self, call_id: str) -> Path:
        return call_dir(call_id) / "mix_clear.wav"

    def telnyx_wav_path(self, call_id: str) -> Path:
        return call_dir(call_id) / "telnyx.wav"

    def telnyx_mp3_path(self, call_id: str) -> Path:
        return call_dir(call_id) / "telnyx.mp3"

    def telnyx_review_path(self, call_id: str) -> Path:
        return call_dir(call_id) / "telnyx_review.wav"

    def save_telnyx_recording(self, call_id: str, data: bytes, *, suffix: str = ".wav") -> Path:
        """Store the provider recording as the canonical conversation file.

        Telnyx may fire two recording.saved events (voice-profile + record_start).
        Keep the dual-channel WAV, and never replace a larger file with a smaller one.
        """
        directory = call_dir(call_id)
        directory.mkdir(parents=True, exist_ok=True)
        ext = ".mp3" if str(suffix or "").lower().endswith("mp3") or (data[:3] == b"ID3") else ".wav"
        dest = self.telnyx_mp3_path(call_id) if ext == ".mp3" else self.telnyx_wav_path(call_id)
        if dest.exists() and dest.stat().st_size > 44 and data:
            existing_size = dest.stat().st_size
            old_ch = 0
            if ext == ".wav":
                with dest.open("rb") as handle:
                    old_ch = _wav_header_channels(handle.read(64))
            new_ch = _wav_header_channels(data) if ext == ".wav" else 0
            if old_ch == 2 and new_ch == 1:
                self.ensure_telnyx_review(call_id)
                return dest
            if len(data) < existing_size and (old_ch >= new_ch or old_ch == 0):
                self.ensure_telnyx_review(call_id)
                return dest
        dest.write_bytes(data)
        if ext == ".wav":
            self.ensure_telnyx_review(call_id, force=True)
        return dest

    def ensure_telnyx_review(self, call_id: str, *, force: bool = False) -> Path | None:
        """Fold Telnyx dual-channel WAV to dual-mono so history plays in both ears."""
        src = self.telnyx_wav_path(call_id)
        dest = self.telnyx_review_path(call_id)
        if not self._nonempty(src):
            return dest if self._nonempty(dest) else None
        if (
            not force
            and self._nonempty(dest)
            and dest.stat().st_mtime >= src.stat().st_mtime
        ):
            return dest
        try:
            self._write_telnyx_review(src, dest)
        except Exception:
            return dest if self._nonempty(dest) else None
        return dest if self._nonempty(dest) else None

    @staticmethod
    def _write_telnyx_review(src: Path, dest: Path) -> None:
        with wave.open(str(src), "rb") as wf:
            channels = wf.getnchannels()
            width = wf.getsampwidth()
            rate = wf.getframerate()
            raw = wf.readframes(wf.getnframes())
        if width != 2 or not raw:
            dest.write_bytes(src.read_bytes())
            return
        samples = array.array("h")
        samples.frombytes(raw)
        if channels <= 1:
            mono = samples.tobytes()
        else:
            folded = array.array("h")
            step = max(1, channels)
            for i in range(0, len(samples) - step + 1, step):
                acc = 0
                for c in range(step):
                    acc += samples[i + c]
                if acc > 32767:
                    acc = 32767
                elif acc < -32767:
                    acc = -32767
                folded.append(acc)
            mono = folded.tobytes()
        stereo = array.array("h")
        left = array.array("h")
        left.frombytes(mono)
        for sample in left:
            stereo.append(sample)
            stereo.append(sample)
        _write_pcm16_stereo_wav(dest, stereo.tobytes(), rate)

    def recording_source(self, call_id: str) -> str:
        if self._nonempty(self.telnyx_wav_path(call_id)) or self._nonempty(self.telnyx_mp3_path(call_id)):
            return "telnyx"
        if self._nonempty(self.mix_path(call_id)) or self._nonempty(self.mix_clear_path(call_id)):
            return "local"
        return "none"

    def user_wav_path(self, call_id: str) -> Path:
        return call_dir(call_id) / "user.wav"

    def user_clear_path(self, call_id: str) -> Path:
        return call_dir(call_id) / "user_clear.wav"

    def agent_wav_path(self, call_id: str) -> Path:
        return call_dir(call_id) / "agent.wav"

    def agent_clear_path(self, call_id: str) -> Path:
        return call_dir(call_id) / "agent_clear.wav"

    def init(self, call_id: str) -> None:
        _user_buffers[call_id] = bytearray()
        _agent_buffers[call_id] = bytearray()
        _agent_rates[call_id] = _AGENT_PCM_RATE

    def set_agent_sample_rate(self, call_id: str, rate: int) -> None:
        if rate > 0:
            _agent_rates[call_id] = rate

    async def append_user_pcm(self, call_id: str, pcm: bytes) -> None:
        if not pcm or not get_settings().enable_call_archive:
            return
        async with _lock(call_id):
            buf = _user_buffers.setdefault(call_id, bytearray())
            buf.extend(pcm)

    async def append_agent_audio(self, call_id: str, chunk: bytes) -> None:
        if not chunk or not get_settings().enable_call_archive:
            return
        async with _lock(call_id):
            buf = _agent_buffers.setdefault(call_id, bytearray())
            buf.extend(chunk)

    async def flush(self, call_id: str) -> dict[str, str]:
        """Write buffers to disk and generate mix.wav. Safe to call twice."""
        async with _lock(call_id):
            if call_id not in _user_buffers and call_id not in _agent_buffers:
                mix = self.mix_path(call_id)
                user_ok = self._nonempty(self.user_pcm_path(call_id)) or self._nonempty(
                    self.user_wav_path(call_id)
                )
                agent_ok = self._nonempty(self.agent_path(call_id)) or self._nonempty(
                    self.agent_wav_path(call_id)
                )
                return {
                    "user": "complete" if user_ok else "empty",
                    "agent": "complete" if agent_ok else "empty",
                    "mix": "complete" if self._nonempty(mix) else "empty",
                }
            user = bytes(_user_buffers.get(call_id, b""))
            agent = bytes(_agent_buffers.get(call_id, b""))
            agent_rate = _agent_rates.get(call_id, _AGENT_PCM_RATE)
            directory = call_dir(call_id)
            directory.mkdir(parents=True, exist_ok=True)
            self.user_pcm_path(call_id).write_bytes(user)
            if user:
                _write_pcm16_wav(self.user_wav_path(call_id), user, SAMPLE_RATE)
                _write_pcm16_wav(self.user_clear_path(call_id), user, SAMPLE_RATE, normalize=True)
            agent_pcm = b""
            if agent and _is_mpeg(agent):
                self.agent_mp3_path(call_id).write_bytes(agent)
            else:
                pcm, pcm_rate = _strip_wav_pcm(agent, agent_rate)
                self.agent_pcm_path(call_id).write_bytes(pcm)
                agent_pcm = pcm
                if pcm_rate != agent_rate:
                    agent_rate = pcm_rate
                if agent_pcm:
                    _write_pcm16_wav(self.agent_wav_path(call_id), agent_pcm, agent_rate)
                    _write_pcm16_wav(self.agent_clear_path(call_id), agent_pcm, agent_rate, normalize=True)
            self._write_mix_wav(self.mix_path(call_id), user, agent_pcm, agent_rate)
            self._write_mix_wav(
                self.mix_clear_path(call_id),
                user,
                agent_pcm,
                agent_rate,
                normalize=True,
            )
            self._clear_gain_mark(call_id).write_text("3", encoding="utf-8")
            legacy = call_dir(call_id) / ".clear_gain_v2"
            if legacy.exists():
                legacy.unlink()
            status = {
                "user": "complete" if user else "empty",
                "agent": "complete" if agent else "empty",
                "mix": "complete",
            }
            _user_buffers.pop(call_id, None)
            _agent_buffers.pop(call_id, None)
            _agent_rates.pop(call_id, None)
            return status

    @staticmethod
    def _write_mix_wav(
        dest: Path,
        user_pcm: bytes,
        agent_pcm: bytes,
        agent_rate: int,
        *,
        normalize: bool = False,
    ) -> None:
        """Stereo WAV at 16 kHz: L=user, R=agent (resampled) or silence."""
        left_pcm = user_pcm
        right_pcm = _resample_int16_mono(agent_pcm, agent_rate, SAMPLE_RATE) if agent_pcm else b""
        if normalize:
            left_pcm = _peak_normalize_pcm16(left_pcm)
            right_pcm = _peak_normalize_pcm16(right_pcm)
        user_frames = len(left_pcm) // 2
        agent_frames = len(right_pcm) // 2
        frame_count = max(user_frames, agent_frames, 1)
        stereo = bytearray(frame_count * 4)
        for i in range(frame_count):
            if i < user_frames:
                stereo[i * 4] = left_pcm[i * 2]
                stereo[i * 4 + 1] = left_pcm[i * 2 + 1]
            if i < agent_frames:
                stereo[i * 4 + 2] = right_pcm[i * 2]
                stereo[i * 4 + 3] = right_pcm[i * 2 + 1]
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(bytes(stereo) if frame_count else b"")
        dest.write_bytes(buf.getvalue())

    def _clear_gain_mark(self, call_id: str) -> Path:
        return call_dir(call_id) / ".clear_gain_v3"

    def refresh_clear_tracks(self, call_id: str) -> None:
        """Rebuild loud review WAVs from archived caller/agent audio (existing calls)."""
        if not call_id or self._clear_gain_mark(call_id).exists():
            return
        user_pcm, user_rate = b"", SAMPLE_RATE
        agent_pcm, agent_rate = b"", SAMPLE_RATE
        if self._nonempty(self.user_wav_path(call_id)):
            user_pcm, user_rate = _strip_wav_pcm(self.user_wav_path(call_id).read_bytes(), SAMPLE_RATE)
        elif self._nonempty(self.user_pcm_path(call_id)):
            user_pcm = self.user_pcm_path(call_id).read_bytes()
        if self._nonempty(self.agent_wav_path(call_id)):
            agent_pcm, agent_rate = _strip_wav_pcm(self.agent_wav_path(call_id).read_bytes(), SAMPLE_RATE)
        elif self._nonempty(self.agent_pcm_path(call_id)):
            agent_pcm = self.agent_pcm_path(call_id).read_bytes()
            agent_rate = SAMPLE_RATE
        if not user_pcm and not agent_pcm:
            return
        if user_pcm:
            _write_pcm16_wav(
                self.user_clear_path(call_id),
                user_pcm,
                user_rate or SAMPLE_RATE,
                normalize=True,
            )
        if agent_pcm:
            _write_pcm16_wav(
                self.agent_clear_path(call_id),
                agent_pcm,
                agent_rate or SAMPLE_RATE,
                normalize=True,
            )
        self._write_mix_wav(
            self.mix_clear_path(call_id),
            user_pcm,
            agent_pcm,
            agent_rate or SAMPLE_RATE,
            normalize=True,
        )
        self._clear_gain_mark(call_id).write_text("3", encoding="utf-8")
        legacy = call_dir(call_id) / ".clear_gain_v2"
        if legacy.exists():
            legacy.unlink()

    @staticmethod
    def _nonempty(path: Path) -> bool:
        return path.exists() and path.stat().st_size > 0

    def file_for(self, call_id: str, kind: str) -> Path | None:
        if kind == "user":
            wav = self.user_wav_path(call_id)
            if self._nonempty(wav):
                return wav
            path = self.user_pcm_path(call_id)
        elif kind == "user_clear":
            path = self.user_clear_path(call_id)
            if self._nonempty(path):
                return path
            wav = self.user_wav_path(call_id)
            if self._nonempty(wav):
                return wav
            path = self.user_pcm_path(call_id)
        elif kind == "agent":
            wav = self.agent_wav_path(call_id)
            if self._nonempty(wav):
                return wav
            path = self.agent_path(call_id)
        elif kind == "agent_clear":
            path = self.agent_clear_path(call_id)
            if self._nonempty(path):
                return path
            wav = self.agent_wav_path(call_id)
            if self._nonempty(wav):
                return wav
            path = self.agent_path(call_id)
        elif kind in ("mix", "mix_clear"):
            for candidate in (
                self.telnyx_review_path(call_id),
                self.telnyx_wav_path(call_id),
                self.telnyx_mp3_path(call_id),
                self.mix_clear_path(call_id) if kind == "mix_clear" else None,
                self.mix_path(call_id),
            ):
                if candidate is not None and self._nonempty(candidate):
                    return candidate
            return None
        else:
            return None
        if path is None or not self._nonempty(path):
            return None
        return path

    def reset_for_tests(self) -> None:
        _locks.clear()
        _user_buffers.clear()
        _agent_buffers.clear()
        _agent_rates.clear()


audio_archive = AudioArchive()
