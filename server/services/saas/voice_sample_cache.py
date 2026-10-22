"""Persist public catalog samples; never cache tenant greetings or custom text."""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import os
import tempfile
import wave
from collections.abc import Awaitable, Callable
from pathlib import Path

_inflight: dict[tuple[asyncio.AbstractEventLoop, str], asyncio.Task] = {}
logger = logging.getLogger(__name__)


def valid_wav(audio: bytes) -> bool:
    try:
        with wave.open(io.BytesIO(audio), "rb") as reader:
            frames = reader.getnframes()
            return (
                frames > 0 and reader.getsampwidth() == 2 and reader.getnchannels() == 1
                and len(reader.readframes(frames)) == frames * 2
            )
    except (EOFError, wave.Error):
        return False


def sample_path(parts: list) -> Path:
    from server.config.env import get_settings

    digest = hashlib.sha256(json.dumps(parts, ensure_ascii=True).encode()).hexdigest()
    return Path(get_settings().data_dir) / "voice-samples" / "v1" / f"{digest}.wav"


def _read(path: Path) -> bytes | None:
    try:
        if path.stat().st_size > 5_000_000:
            return None
        audio = path.read_bytes()
        return audio if valid_wav(audio) else None
    except OSError:
        return None


def _write(path: Path, audio: bytes) -> None:
    if not valid_wav(audio):
        raise RuntimeError("Voice sample returned invalid WAV audio")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            output.write(audio)
            output.flush()
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


async def get_or_create(parts: list, generate: Callable[[], Awaitable[bytes]]) -> tuple[bytes, bool]:
    path = sample_path(parts)
    cached = await asyncio.to_thread(_read, path)
    if cached is not None:
        return cached, True
    key = (asyncio.get_running_loop(), str(path))
    task = _inflight.get(key)
    shared = task is not None
    if task is None:
        async def create():
            audio = await generate()
            try:
                await asyncio.to_thread(_write, path, audio)
            except OSError as exc:
                logger.warning("Voice sample cache write failed (%s)", type(exc).__name__)
            return audio

        task = asyncio.create_task(create())
        _inflight[key] = task

        def completed(done):
            _inflight.pop(key, None)
            if not done.cancelled():
                done.exception()  # Retrieve errors even if every HTTP waiter disconnected.

        task.add_done_callback(completed)
    return await asyncio.shield(task), shared
