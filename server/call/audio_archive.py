"""Audio archive — user PCM, agent stream, post-call stereo mix.wav."""
from __future__ import annotations

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
            user = bytes(_user_buffers.get(call_id, b""))
            agent = bytes(_agent_buffers.get(call_id, b""))
            agent_rate = _agent_rates.get(call_id, _AGENT_PCM_RATE)
            directory = call_dir(call_id)
            directory.mkdir(parents=True, exist_ok=True)
            self.user_pcm_path(call_id).write_bytes(user)
            agent_pcm = b""
            if agent and _is_mpeg(agent):
                self.agent_mp3_path(call_id).write_bytes(agent)
            else:
                self.agent_pcm_path(call_id).write_bytes(agent)
                agent_pcm = agent
            self._write_mix_wav(self.mix_path(call_id), user, agent_pcm, agent_rate)
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
    def _write_mix_wav(dest: Path, user_pcm: bytes, agent_pcm: bytes, agent_rate: int) -> None:
        """Stereo WAV at 16 kHz: L=user, R=agent (resampled) or silence."""
        right = _resample_int16_mono(agent_pcm, agent_rate, SAMPLE_RATE) if agent_pcm else b""
        user_frames = len(user_pcm) // 2
        agent_frames = len(right) // 2
        frame_count = max(user_frames, agent_frames)
        stereo = bytearray(frame_count * 4)
        for i in range(frame_count):
            if i < user_frames:
                stereo[i * 4] = user_pcm[i * 2]
                stereo[i * 4 + 1] = user_pcm[i * 2 + 1]
            if i < agent_frames:
                stereo[i * 4 + 2] = right[i * 2]
                stereo[i * 4 + 3] = right[i * 2 + 1]
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(bytes(stereo) if frame_count else b"")
        dest.write_bytes(buf.getvalue())

    def file_for(self, call_id: str, kind: str) -> Path | None:
        mapping = {
            "user": self.user_pcm_path(call_id),
            "agent": self.agent_path(call_id),
            "mix": self.mix_path(call_id),
        }
        path = mapping.get(kind)
        if path is None or not path.exists() or path.stat().st_size == 0:
            return None
        return path

    def reset_for_tests(self) -> None:
        _locks.clear()
        _user_buffers.clear()
        _agent_buffers.clear()
        _agent_rates.clear()


audio_archive = AudioArchive()
