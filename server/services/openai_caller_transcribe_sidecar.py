"""Parallel gpt-4o-mini-transcribe on inbound caller PCM (Gemini Live PSTN)."""
from __future__ import annotations

import asyncio
import io
import time
import wave
from collections.abc import Awaitable, Callable
from typing import Any

from server.realtime.models import REALTIME_PCM_RATE
from server.utils.logger import logger

OnFinal = Callable[[str], Awaitable[None]]

_MIN_CHUNK_BYTES = REALTIME_PCM_RATE * 2  # ~1s PCM16 mono
_FLUSH_INTERVAL_SEC = 2.5


class OpenaiCallerTranscribeSidecar:
    def __init__(self, *, language: str, on_final: OnFinal) -> None:
        self._language = (language or "te-IN").strip() or "te-IN"
        self._on_final = on_final
        self._buf = bytearray()
        self._audio_sec = 0.0
        self._closed = False
        self._task: asyncio.Task | None = None
        self._last_flush = 0.0
        self._flush_lock = asyncio.Lock()

    @property
    def billed_audio_sec(self) -> float:
        return self._audio_sec

    def start(self) -> None:
        if self._task is not None:
            return
        self._last_flush = time.monotonic()
        self._task = asyncio.create_task(self._tick(), name="openai-caller-stt")

    async def close(self) -> None:
        self._closed = True
        if self._buf:
            await self._flush()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def feed_pcm16(self, pcm16: bytes) -> None:
        if self._closed or not pcm16:
            return
        self._buf.extend(pcm16)
        self._audio_sec += len(pcm16) / (REALTIME_PCM_RATE * 2)

    async def _tick(self) -> None:
        try:
            while not self._closed:
                await asyncio.sleep(0.4)
                if len(self._buf) >= _MIN_CHUNK_BYTES * 2:
                    await self._flush()
                    continue
                if time.monotonic() - self._last_flush >= _FLUSH_INTERVAL_SEC and len(self._buf) >= _MIN_CHUNK_BYTES:
                    await self._flush()
        except asyncio.CancelledError:
            return

    async def _flush(self) -> None:
        async with self._flush_lock:
            if not self._buf:
                return
            chunk = bytes(self._buf)
            self._buf.clear()
            self._last_flush = time.monotonic()
        text = await _transcribe_wav_async(chunk, self._language)
        cleaned = (text or "").strip()
        if cleaned:
            asyncio.create_task(self._deliver_final(cleaned), name="openai-caller-stt-deliver")

    async def _deliver_final(self, cleaned: str) -> None:
        try:
            await self._on_final(cleaned)
        except Exception as exc:
            logger.warning("[CALLER_STT] on_final failed: %s", str(exc)[:160])


async def _transcribe_wav_async(pcm16: bytes, language: str) -> str:
    from server.utils.http_clients import get_openai_client

    wav = _pcm16_to_wav(pcm16)
    client = get_openai_client()
    lang_hint = language.split("-")[0] if language else None
    kwargs: dict[str, Any] = {"model": "gpt-4o-mini-transcribe", "file": ("chunk.wav", wav)}
    if lang_hint:
        kwargs["language"] = lang_hint
    resp = await client.audio.transcriptions.create(**kwargs)
    if isinstance(resp, str):
        return resp
    return str(getattr(resp, "text", "") or "")


def _pcm16_to_wav(pcm16: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(REALTIME_PCM_RATE)
        wf.writeframes(pcm16)
    return buf.getvalue()
