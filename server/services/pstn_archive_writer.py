"""Single-writer audio archive queue — avoids per-frame create_task storms."""
from __future__ import annotations

import asyncio
from typing import Literal

_Kind = Literal["user", "agent"]


class PstnArchiveWriter:
    def __init__(self) -> None:
        self._q: asyncio.Queue[tuple[str, _Kind, bytes] | None] = asyncio.Queue(maxsize=500)
        self._task: asyncio.Task | None = None
        self._closed = False

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    def enqueue(self, call_id: str, kind: _Kind, pcm_or_wire: bytes) -> None:
        if self._closed or not call_id or not pcm_or_wire:
            return
        self.start()
        try:
            self._q.put_nowait((call_id, kind, pcm_or_wire))
        except asyncio.QueueFull:
            try:
                _ = self._q.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                self._q.put_nowait((call_id, kind, pcm_or_wire))
            except asyncio.QueueFull:
                pass

    async def close(self) -> None:
        if self._closed:
            if self._task:
                try:
                    await asyncio.wait_for(self._task, timeout=2.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    self._task.cancel()
                self._task = None
            return
        self._closed = True
        try:
            self._q.put_nowait(None)
        except asyncio.QueueFull:
            pass
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
            self._task = None

    async def _run(self) -> None:
        from server.call.audio_archive import audio_archive

        while True:
            item = await self._q.get()
            if item is None:
                return
            call_id, kind, data = item
            try:
                if kind == "user":
                    await audio_archive.append_user_pcm(call_id, data)
                else:
                    await audio_archive.append_agent_audio(call_id, data)
            except Exception:
                pass
