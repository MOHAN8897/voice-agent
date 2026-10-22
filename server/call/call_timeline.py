"""Unified call timeline: connected calls plus never-answered ringing attempts.

A ``calls`` row only exists once media streams, so a missed inbound call used to be
invisible. The console needs one ordered list with one status vocabulary, so this
module merges both sources and normalises them into a single item shape.
"""
from __future__ import annotations

from typing import Any

from server.call.call_status import (
    CALL_STATUSES,
    is_in_progress_record,
    normalize_call_statuses,
    status_for_record,
)
from server.call.call_store import call_attempt_store, call_store

#: How many rows each source contributes to a page. Over-fetching by `offset`
#: lets the merged list be sliced correctly without a full table scan.
_MAX_FETCH = 500


def _attempt_to_item(row: dict[str, Any]) -> dict[str, Any]:
    """A ringing event, shaped like a call so the console needs one renderer."""
    status = status_for_record(row)
    return {
        "call_id": row.get("attempt_id"),
        "attempt_id": row.get("attempt_id"),
        "is_attempt": True,
        "connected": row.get("linked_call_id") is not None,
        "linked_call_id": row.get("linked_call_id"),
        "tenant_id": row.get("tenant_id"),
        "agent_id": row.get("agent_id"),
        "channel": "pstn",
        "direction": row.get("direction") or "inbound",
        "status": status,
        "in_progress": status == "in_progress",
        "started_at": row.get("started_at"),
        "ended_at": row.get("ended_at"),
        "answered_at": row.get("answered_at"),
        "duration_sec": row.get("duration_sec"),
        "end_reason": row.get("end_reason"),
        "policy_reason": row.get("policy_reason"),
        "disposition": None,
        "caller_phone": row.get("from_number"),
        "called_phone": row.get("to_number"),
        "summary": None,
        "has_recording": False,
        "has_transcript": False,
    }


def _call_to_item(row: dict[str, Any]) -> dict[str, Any]:
    status = status_for_record(row)
    return {
        "call_id": row.get("call_id"),
        "attempt_id": None,
        "is_attempt": False,
        "connected": True,
        "linked_call_id": None,
        "tenant_id": row.get("tenant_id"),
        "agent_id": row.get("agent_id"),
        "channel": row.get("channel"),
        "direction": row.get("direction"),
        "status": status,
        "in_progress": is_in_progress_record(row),
        "is_test": bool(row.get("is_test")),
        "started_at": row.get("started_at"),
        "ended_at": row.get("ended_at"),
        "answered_at": None,
        "duration_sec": row.get("duration_sec"),
        "end_reason": row.get("end_reason"),
        "policy_reason": None,
        "disposition": row.get("disposition"),
        "caller_phone": None,
        "called_phone": None,
        "summary": row.get("summary"),
        "has_recording": bool(row.get("has_recording")),
        "has_transcript": bool(row.get("summary")) or bool(row.get("has_transcript")),
    }


def _sort_key(item: dict[str, Any]) -> str:
    return str(item.get("started_at") or "")


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """An attempt linked to a real call must not appear twice."""
    connected_ids = {i.get("linked_call_id") for i in items if i.get("is_attempt") and i.get("linked_call_id")}
    out: list[dict[str, Any]] = []
    for item in items:
        if item.get("is_attempt") and item.get("linked_call_id") in connected_ids:
            # Keep only the richer connected row.
            if not any(o.get("call_id") == item.get("linked_call_id") and not o.get("is_attempt") for o in items):
                out.append(item)
            continue
        out.append(item)
    return out


async def list_timeline(
    *,
    tenant_id: str,
    agent_id: str | None = None,
    statuses: list[str] | None = None,
    direction: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 20,
    offset: int = 0,
    include_attempts: bool = True,
    include_tests: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    """One chronological list of everything that rang, with canonical status.

    Browser practice sessions (``is_test``) are excluded unless ``include_tests``
    is set — they are not real conversations and must not inflate the rollups.
    """
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    wanted = set(normalize_call_statuses(statuses))

    calls, _call_total = await call_store.list_calls(
        tenant_id=tenant_id,
        agent_id=agent_id,
        since=since,
        until=until,
        limit=_MAX_FETCH,
        offset=0,
        include_tests=include_tests,
    )
    items = [_call_to_item(c) for c in calls]

    if include_attempts:
        attempts, _attempt_total = await call_attempt_store.list_attempts(
            tenant_id=tenant_id,
            agent_id=agent_id,
            since=since,
            until=until,
            limit=_MAX_FETCH,
            offset=0,
        )
        items.extend(_attempt_to_item(a) for a in attempts)

    items = _dedupe(items)
    if direction:
        items = [i for i in items if i.get("direction") == direction]
    if wanted:
        items = [i for i in items if i.get("status") in wanted]
    items.sort(key=_sort_key, reverse=True)

    total = len(items)
    return items[offset : offset + limit], total


def counts_from_items(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = {status: 0 for status in CALL_STATUSES}
    for item in items:
        status = item.get("status")
        if status in counts:
            counts[status] += 1
    return counts


async def timeline_stats(
    *,
    tenant_id: str,
    agent_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> dict[str, Any]:
    """Counts and totals for the whole window, for the console's summary row."""
    items, _total = await list_timeline(
        tenant_id=tenant_id,
        agent_id=agent_id,
        since=since,
        until=until,
        limit=_MAX_FETCH,
        offset=0,
    )
    counts = counts_from_items(items)
    connected = [i for i in items if i.get("connected")]
    total_duration = sum(int(i.get("duration_sec") or 0) for i in connected)
    return {
        "counts": counts,
        "total": len(items),
        "connected": len(connected),
        "missed": counts.get("missed", 0),
        "totalDurationSec": total_duration,
        "avgDurationSec": round(total_duration / len(connected)) if connected else 0,
    }
