"""Audio archive — user PCM, agent stream, post-call stereo mix.wav."""
from __future__ import annotations

import array
import asyncio
import io
import wave
from pathlib import Path

from server.call.audio_levels import (
    audioop,
    level_interleaved_pcm16,
    level_speech_pcm16,
    read_pcm16,
    write_pcm16_wav,
)
from server.call.paths import call_dir
from server.config.constants import constants
from server.config.env import get_settings
from server.utils.logger import logger

SAMPLE_RATE = constants.PREFERRED_SAMPLE_RATE  # 16 kHz user PCM
_AGENT_PCM_RATE = 24000  # Sarvam bulbul WS linear16 default
#: Bump to rebuild the levelled review tracks (mix_clear, *_clear) on next play.
_CLEAR_GAIN_VERSION = 4
#: Bump to rebuild conversation_balanced.wav (levelled carrier recording) on next play.
_BALANCE_VERSION = 1
#: Carrier recordings in the order playback prefers them; each is split L=caller, R=agent.
_CARRIER_RECORDINGS = (
    "vobiz_recording.mp4",
    "vobiz_recording.mp3",
    "vobiz_recording.wav",
    "telnyx.wav",
    "telnyx.mp3",
)
_locks: dict[str, asyncio.Lock] = {}
_user_buffers: dict[str, bytearray] = {}
_agent_buffers: dict[str, bytearray] = {}
_agent_rates: dict[str, int] = {}
#: Calls that must never be written to disk (browser practice sessions). Real PSTN
#: calls stay recorded; test sessions are not conversations worth keeping audio of.
_no_record: set[str] = set()


def _lock(call_id: str) -> asyncio.Lock:
    if call_id not in _locks:
        _locks[call_id] = asyncio.Lock()
    return _locks[call_id]


_MP3_KBPS = {
    3: (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320),  # MPEG-1
    2: (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160),  # MPEG-2
}
_MP3_RATES = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}


def _mp3_frame_len(data: bytes, pos: int) -> int:
    """Length of the MPEG Layer III frame whose header starts at ``pos``; 0 if none."""
    if pos + 4 > len(data) or data[pos] != 0xFF or (data[pos + 1] & 0xE0) != 0xE0:
        return 0
    b1, b2 = data[pos + 1], data[pos + 2]
    version, layer, kbps_idx, rate_idx = (b1 >> 3) & 3, (b1 >> 1) & 3, b2 >> 4, (b2 >> 2) & 3
    if version == 1 or layer != 1 or kbps_idx in (0, 15) or rate_idx == 3:
        return 0
    kbps = _MP3_KBPS[3 if version == 3 else 2][kbps_idx]
    rate = _MP3_RATES[version][rate_idx]
    return (144 if version == 3 else 72) * kbps * 1000 // rate + ((b2 >> 1) & 1)


def _is_mpeg(data: bytes) -> bool:
    # A bare 0xFFEx check misreads raw PCM that opens on a -1 sample as MP3, which
    # used to drop the whole agent track from the mix. Require a real frame header
    # followed by the next frame's sync.
    if data[:3] == b"ID3":
        return True
    length = _mp3_frame_len(data, 0)
    if not length:
        return False
    return len(data) < length + 4 or _mp3_frame_len(data, length) > 0


def _resample_int16_mono(pcm: bytes, src_rate: int, dst_rate: int) -> bytes:
    if src_rate == dst_rate or src_rate <= 0 or dst_rate <= 0 or len(pcm) < 2:
        return pcm
    out, _ = audioop.ratecv(pcm[: len(pcm) // 2 * 2], 2, 1, src_rate, dst_rate, None)
    return out


def _strip_wav_pcm(data: bytes, default_rate: int) -> tuple[bytes, int]:
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        try:
            with wave.open(io.BytesIO(data), "rb") as wf:
                return wf.readframes(wf.getnframes()), wf.getframerate()
        except Exception:
            return data, default_rate
    return data, default_rate


def _write_pcm16_wav(dest: Path, pcm: bytes, sample_rate: int, *, normalize: bool = False) -> None:
    rate = int(sample_rate) if sample_rate > 0 else SAMPLE_RATE
    body = level_speech_pcm16(pcm, rate) if normalize and pcm else (pcm or b"")
    write_pcm16_wav(dest, body, rate, 1)


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

    def mix_mp3_path(self, call_id: str) -> Path:
        return call_dir(call_id) / "mix.mp3"

    def mix_clear_mp3_path(self, call_id: str) -> Path:
        return call_dir(call_id) / "mix_clear.mp3"

    def conversation_mp3_path(self, call_id: str) -> Path:
        return call_dir(call_id) / "conversation.mp3"

    def conversation_mp4_path(self, call_id: str) -> Path:
        return call_dir(call_id) / "conversation.mp4"

    def balanced_path(self, call_id: str) -> Path:
        """Carrier recording with each speaker levelled; the raw file is never touched."""
        return call_dir(call_id) / "conversation_balanced.wav"

    def _balance_mark(self, call_id: str) -> Path:
        return call_dir(call_id) / f".balanced_v{_BALANCE_VERSION}"

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
        if any(self._nonempty(call_dir(call_id) / f"vobiz_recording.{ext}") for ext in ("wav", "mp3")):
            return "vobiz"
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

    def init(self, call_id: str, *, record: bool = True) -> None:
        _user_buffers[call_id] = bytearray()
        _agent_buffers[call_id] = bytearray()
        _agent_rates[call_id] = _AGENT_PCM_RATE
        if not record:
            # Test sessions keep the buffers so the voice loop's bookkeeping is
            # unchanged, but nothing is ever written to disk for them.
            _no_record.add(call_id)

    def set_agent_sample_rate(self, call_id: str, rate: int) -> None:
        if rate > 0:
            _agent_rates[call_id] = rate

    async def append_user_pcm(self, call_id: str, pcm: bytes) -> None:
        if not pcm or not get_settings().enable_call_archive or call_id in _no_record:
            return
        async with _lock(call_id):
            buf = _user_buffers.setdefault(call_id, bytearray())
            buf.extend(pcm)

    async def append_agent_audio(self, call_id: str, chunk: bytes) -> None:
        if not chunk or not get_settings().enable_call_archive or call_id in _no_record:
            return
        async with _lock(call_id):
            buf = _agent_buffers.setdefault(call_id, bytearray())
            buf.extend(chunk)

    async def flush(self, call_id: str) -> dict[str, str]:
        """Write buffers to disk and generate mix.wav. Safe to call twice."""
        if call_id in _no_record:
            # Nothing was buffered, so drop the (empty) buffers and leave disk clean.
            async with _lock(call_id):
                _user_buffers.pop(call_id, None)
                _agent_buffers.pop(call_id, None)
                _agent_rates.pop(call_id, None)
                _no_record.discard(call_id)
            return {"user": "empty", "agent": "empty", "mix": "empty"}
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
            # Levelling and resampling a long call takes a moment; keep it off the loop.
            await asyncio.to_thread(self._write_tracks, call_id, user, agent, agent_rate)
            status = {
                "user": "complete" if user else "empty",
                "agent": "complete" if agent else "empty",
                "mix": "complete",
            }
            _user_buffers.pop(call_id, None)
            _agent_buffers.pop(call_id, None)
            _agent_rates.pop(call_id, None)
            return status

    def _write_tracks(self, call_id: str, user: bytes, agent: bytes, agent_rate: int) -> None:
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
        self._mark_clear_gain(call_id)

    @staticmethod
    def _write_mix_wav(
        dest: Path,
        user_pcm: bytes,
        agent_pcm: bytes,
        agent_rate: int,
        *,
        normalize: bool = False,
    ) -> None:
        """Stereo WAV at 16 kHz: L=user, R=agent (resampled) or silence.

        ``normalize`` levels each speaker on its own (see audio_levels), so the
        review mix plays a quiet caller and a loud agent at the same level.
        """
        left_pcm = user_pcm[: len(user_pcm) // 2 * 2]
        right_pcm = _resample_int16_mono(agent_pcm, agent_rate, SAMPLE_RATE) if agent_pcm else b""
        if normalize:
            left_pcm = level_speech_pcm16(left_pcm, SAMPLE_RATE)
            right_pcm = level_speech_pcm16(right_pcm, SAMPLE_RATE)
        size = max(len(left_pcm), len(right_pcm), 2)
        left_pcm = left_pcm.ljust(size, b"\0")
        right_pcm = right_pcm.ljust(size, b"\0")
        stereo = audioop.add(
            audioop.tostereo(left_pcm, 2, 1, 0),
            audioop.tostereo(right_pcm, 2, 0, 1),
            2,
        )
        write_pcm16_wav(dest, stereo, SAMPLE_RATE, 2)

    def _clear_gain_mark(self, call_id: str) -> Path:
        return call_dir(call_id) / f".clear_gain_v{_CLEAR_GAIN_VERSION}"

    def _mark_clear_gain(self, call_id: str) -> None:
        mark = self._clear_gain_mark(call_id)
        mark.write_text(str(_CLEAR_GAIN_VERSION), encoding="utf-8")
        for legacy in call_dir(call_id).glob(".clear_gain_v*"):
            if legacy != mark:
                legacy.unlink(missing_ok=True)

    def _read_agent_track(self, call_id: str) -> tuple[bytes, int]:
        if self._nonempty(self.agent_wav_path(call_id)):
            return _strip_wav_pcm(self.agent_wav_path(call_id).read_bytes(), SAMPLE_RATE)
        if self._nonempty(self.agent_pcm_path(call_id)):
            return self.agent_pcm_path(call_id).read_bytes(), SAMPLE_RATE
        mp3 = self.agent_mp3_path(call_id)
        if self._nonempty(mp3):
            data = mp3.read_bytes()
            if not _is_mpeg(data):
                # Older calls stored raw PSTN-rate PCM here when it opened on a -1 sample.
                return data, SAMPLE_RATE
        return b"", SAMPLE_RATE

    def refresh_clear_tracks(self, call_id: str) -> None:
        """Rebuild levelled review WAVs from archived caller/agent audio (existing calls)."""
        if not call_id or self._clear_gain_mark(call_id).exists():
            return
        user_pcm, user_rate = b"", SAMPLE_RATE
        if self._nonempty(self.user_wav_path(call_id)):
            user_pcm, user_rate = _strip_wav_pcm(self.user_wav_path(call_id).read_bytes(), SAMPLE_RATE)
        elif self._nonempty(self.user_pcm_path(call_id)):
            user_pcm = self.user_pcm_path(call_id).read_bytes()
        agent_pcm, agent_rate = self._read_agent_track(call_id)
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
        self._mark_clear_gain(call_id)

    def _balance_source(self, call_id: str) -> Path | None:
        for name in _CARRIER_RECORDINGS:
            path = call_dir(call_id) / name
            if self._nonempty(path):
                return path
        return None

    def ensure_balanced_mix(self, call_id: str) -> Path | None:
        """The recording tenants hear: each speaker levelled to the same loudness.

        Built from the carrier recording when there is one (it is time-aligned and
        split L=caller, R=agent), else the levelled local mix. Rebuilt lazily when
        the version, the source or the source file changes; originals stay as they
        are. Returns None when nothing can be levelled (no audio, or no decoder for
        the carrier's format), so callers fall back to the original file.
        """
        if not call_id:
            return None
        src = self._balance_source(call_id)
        if src is None:
            self.refresh_clear_tracks(call_id)
            mix = self.mix_clear_path(call_id)
            return mix if self._nonempty(mix) and self._clear_gain_mark(call_id).exists() else None
        dest = self.balanced_path(call_id)
        mark = self._balance_mark(call_id)
        try:
            if (
                self._nonempty(dest)
                and mark.exists()
                and mark.read_text(encoding="utf-8").strip() == src.name
                and dest.stat().st_mtime >= src.stat().st_mtime
            ):
                return dest
            decoded = read_pcm16(src)
            if decoded is None or decoded[2] not in (1, 2) or not decoded[0]:
                return None
            pcm, rate, channels = decoded
            levelled = level_interleaved_pcm16(pcm, rate, channels)
            if src.name.startswith("telnyx") and channels == 2:
                # Telnyx history plays folded to both ears; keep that, levelled.
                mono = level_speech_pcm16(audioop.tomono(levelled, 2, 1, 1), rate)
                levelled = audioop.tostereo(mono, 2, 1, 1)
            write_pcm16_wav(dest, levelled, rate, channels)
            mark.write_text(src.name, encoding="utf-8")
            for stale in call_dir(call_id).glob(".balanced_v*"):
                if stale != mark:
                    stale.unlink(missing_ok=True)
            return dest
        except Exception as exc:
            logger.warning("[AUDIO] balanced mix failed call=%s: %s", call_id, str(exc)[:200])
            return None

    def levels_for(self, call_id: str, path: Path) -> tuple[str, str]:
        """(recording source, "balanced" | "original") for a file the API serves."""
        name = path.name
        if name == self.balanced_path(call_id).name:
            mark = self._balance_mark(call_id)
            origin = mark.read_text(encoding="utf-8").strip() if mark.exists() else ""
            return ("telnyx" if origin.startswith("telnyx") else "vobiz"), "balanced"
        if name == self.mix_clear_path(call_id).name and self._clear_gain_mark(call_id).exists():
            return "local", "balanced"
        if name.startswith("vobiz_recording"):
            return "vobiz", "original"
        return ("telnyx" if name.startswith("telnyx") else "local"), "original"

    @staticmethod
    def _nonempty(path: Path) -> bool:
        return path.exists() and path.stat().st_size > 0

    def ensure_mp3_for_wav(self, wav_path: Path, mp3_path: Path) -> Path | None:
        """Cache MP3 next to WAV; return mp3 path when encoding succeeds."""
        if not self._nonempty(wav_path):
            return None
        if wav_path.suffix.lower() == ".mp3":
            return wav_path
        if self._nonempty(mp3_path) and mp3_path.stat().st_mtime >= wav_path.stat().st_mtime:
            return mp3_path
        from server.call.audio_mp3 import convert_wav_to_mp3

        if convert_wav_to_mp3(wav_path, mp3_path):
            return mp3_path if self._nonempty(mp3_path) else None
        return None

    def ensure_conversation_mp3(self, call_id: str, wav_path: Path | None) -> Path | None:
        if wav_path is None or not self._nonempty(wav_path):
            return None
        if wav_path.suffix.lower() == ".mp3":
            return wav_path
        dest = self._encoded_path(call_id, wav_path, ".mp3")
        return self.ensure_mp3_for_wav(wav_path, dest)

    def _encoded_path(self, call_id: str, wav_path: Path, suffix: str) -> Path:
        # The levelled mix keeps its own encode cache, so a request for the original
        # recording can never overwrite (or be served as) the balanced one.
        if wav_path.name in (self.balanced_path(call_id).name, self.mix_clear_path(call_id).name):
            return call_dir(call_id) / f"conversation_balanced{suffix}"
        if wav_path.stem.startswith(("user", "agent")):
            # Single-speaker tracks get their own cache too (agent.mp3 is a raw track).
            return call_dir(call_id) / f"{wav_path.stem}.encoded{suffix}"
        return call_dir(call_id) / f"conversation{suffix}"

    def ensure_mp4_for_wav(self, wav_path: Path, mp4_path: Path) -> Path | None:
        """Cache MP4 next to WAV; return mp4 path when encoding succeeds."""
        if not self._nonempty(wav_path):
            return None
        if wav_path.suffix.lower() == ".mp4":
            return wav_path
        if self._nonempty(mp4_path) and mp4_path.stat().st_mtime >= wav_path.stat().st_mtime:
            return mp4_path
        from server.call.audio_mp3 import convert_wav_to_mp4

        if convert_wav_to_mp4(wav_path, mp4_path):
            return mp4_path if self._nonempty(mp4_path) else None
        return None

    def ensure_conversation_mp4(self, call_id: str, wav_path: Path | None) -> Path | None:
        if wav_path is None or not self._nonempty(wav_path):
            return None
        if wav_path.suffix.lower() == ".mp4":
            return wav_path
        dest = self._encoded_path(call_id, wav_path, ".mp4")
        return self.ensure_mp4_for_wav(wav_path, dest)

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
                call_dir(call_id) / "conversation.mp4",
                call_dir(call_id) / "vobiz_recording.mp4",
                call_dir(call_id) / "vobiz_recording.mp3",
                call_dir(call_id) / "conversation.mp3",
                call_dir(call_id) / "vobiz_recording.wav",
                self.telnyx_review_path(call_id),
                self.telnyx_mp3_path(call_id),
                self.telnyx_wav_path(call_id),
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
