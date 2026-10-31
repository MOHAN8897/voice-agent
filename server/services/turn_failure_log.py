"""Persist failed agent turns — reconstructable, admin-visible, alertable."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from server.utils.logger import logger

_BACKGROUND: set[asyncio.Task] = set()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


async def record_turn_failure(
    *,
    call_id: str | None,
    tenant_id: str | None,
    agent_id: str | None,
    transcript: str,
    partial_text: str,
    finish_reason: str | None,
    error_type: str,
    error: str,
    delivered: bool,
    turn_completed: bool,
    retry_used: bool,
    watchdog_retry: bool,
    tool_wait: bool,
) -> dict[str, Any]:
    """Keep the failed turn instead of deleting it, then raise the alert."""
    from server.call.call_ledger import call_ledger

    record = {
        "at": _utcnow(),
        "call_id": call_id,
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "transcript": (transcript or "").strip()[:2000],
        "partial_text": (partial_text or "").strip()[:2000],
        "finish_reason": finish_reason or "unknown",
        "error_type": error_type,
        "error": (error or "")[:300],
        "delivered": bool(delivered),
        "turn_completed": bool(turn_completed),
        "retry_used": bool(retry_used),
        "watchdog_retry": bool(watchdog_retry),
        "tool_wait": bool(tool_wait),
    }
    if call_id:
        try:
            await call_ledger.append_failed_turn(call_id, record)
            meta = call_ledger.read_meta(call_id) or {}
            meta["agent_failure_count"] = int(meta.get("agent_failure_count") or 0) + 1
            meta["agent_failure_last"] = {
                key: record[key]
                for key in (
                    "at",
                    "finish_reason",
                    "error_type",
                    "retry_used",
                    "watchdog_retry",
                    "delivered",
                )
            }
            call_ledger.write_meta(call_id, meta)
        except Exception as exc:
            logger.warning(
                "[TURN] failed-turn record skipped call=%s: %s",
                call_id,
                type(exc).__name__,
            )
    _schedule_alert(record)
    return record


def _schedule_alert(record: dict[str, Any]) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(_alert(record))
    _BACKGROUND.add(task)
    task.add_done_callback(_BACKGROUND.discard)


async def _alert(record: dict[str, Any]) -> None:
    from server.services.saas.activity_log import record_event

    tenant = None
    raw = record.get("tenant_id")
    if raw:
        try:
            tenant = uuid.UUID(str(raw))
        except (TypeError, ValueError):
            tenant = None
    await record_event(
        action="call.agent_failure",
        resource_type="call",
        resource_id=str(record.get("call_id") or ""),
        actor="voice-agent",
        tenant_id=tenant,
        source="system",
        outcome="error",
        severity="error",
        payload={
            "finish_reason": record.get("finish_reason"),
            "error_type": record.get("error_type"),
            "retry_used": record.get("retry_used"),
            "watchdog_retry": record.get("watchdog_retry"),
            "tool_wait": record.get("tool_wait"),
            "partial_chars": len(record.get("partial_text") or ""),
            "delivered": record.get("delivered"),
        },
    )
