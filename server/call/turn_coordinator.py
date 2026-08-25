"""Per-call turn serialization — prevents overlapping turns and dropped ledger writes."""
from __future__ import annotations

import asyncio
from typing import Awaitable, TypeVar

T = TypeVar("T")

_locks: dict[str, asyncio.Lock] = {}
_pending: dict[str, set[asyncio.Task]] = {}


def lock_for(call_id: str) -> asyncio.Lock:
    if call_id not in _locks:
        _locks[call_id] = asyncio.Lock()
    return _locks[call_id]


def track(call_id: str, coro: Awaitable[T]) -> asyncio.Task[T]:
    task = asyncio.create_task(coro)
    bucket = _pending.setdefault(call_id, set())
    bucket.add(task)

    def _done(t: asyncio.Task[T]) -> None:
        bucket.discard(t)
        if not bucket:
            _pending.pop(call_id, None)

    task.add_done_callback(_done)
    return task


async def drain(call_id: str) -> None:
    pending = list(_pending.get(call_id, []))
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


def reset_for_tests() -> None:
    _locks.clear()
    _pending.clear()
