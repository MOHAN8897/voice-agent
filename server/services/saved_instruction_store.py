"""Postgres mirror of compiled session instructions (brief, script, brain)."""
from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from server.db.connection import get_session_factory
from server.db.models.brain_models import SavedInstruction

_log = logging.getLogger(__name__)


def agent_id_from_session(session_id: str) -> uuid.UUID | None:
    raw = (session_id or "").strip()
    prefix = "test-studio:"
    if raw.startswith(prefix):
        raw = raw[len(prefix) :]
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


def _jsonable(entry: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in (entry or {}).items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[key] = value
        elif isinstance(value, (list, dict)):
            out[key] = value
        else:
            out[key] = str(value)
    return out


async def upsert(session_id: str, entry: dict[str, Any]) -> None:
    factory = get_session_factory()
    if factory is None or not session_id:
        return
    payload = _jsonable(entry)
    agent_uuid = agent_id_from_session(session_id)
    try:
        async with factory() as session:
            row = await session.get(SavedInstruction, session_id)
            now = datetime.now(timezone.utc)
            if row is None:
                session.add(
                    SavedInstruction(
                        session_id=session_id,
                        agent_id=agent_uuid,
                        payload=payload,
                        updated_at=now,
                    )
                )
            else:
                row.payload = payload
                row.agent_id = agent_uuid
                row.updated_at = now
            await session.commit()
    except Exception as exc:
        _log.debug("saved_instruction upsert skipped: %s", exc)


async def delete(session_id: str) -> None:
    factory = get_session_factory()
    if factory is None or not session_id:
        return
    try:
        async with factory() as session:
            row = await session.get(SavedInstruction, session_id)
            if row is not None:
                await session.delete(row)
                await session.commit()
    except Exception as exc:
        _log.debug("saved_instruction delete skipped: %s", exc)


async def load_all() -> dict[str, dict[str, Any]]:
    factory = get_session_factory()
    if factory is None:
        return {}
    async with factory() as session:
        result = await session.execute(select(SavedInstruction))
        out: dict[str, dict[str, Any]] = {}
        for row in result.scalars():
            payload = dict(row.payload or {})
            if payload:
                out[row.session_id] = payload
        return out


def _spawn(coro) -> None:
    if get_session_factory() is None:
        coro.close()
        return

    async def _run() -> None:
        try:
            await coro
        except Exception as exc:
            _log.debug("saved_instruction task skipped: %s", exc)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        threading.Thread(target=lambda: asyncio.run(_run()), daemon=True).start()
        return
    loop.create_task(_run())


def queue_upsert(session_id: str, entry: dict[str, Any]) -> None:
    _spawn(upsert(session_id, entry))


def queue_delete(session_id: str) -> None:
    _spawn(delete(session_id))
