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
from server.call.hangup_causes import outcome_for_item

#: Upper bound on rows each source contributes to a page. A page needs only the
#: first ``offset + limit`` rows of each source to be merged and sliced correctly.
_MAX_FETCH = 2000


def _attempt_to_item(row: dict[str, Any]) -> dict[str, Any]:
    """A ringing event, shaped like a call so the console needs one renderer."""
    status = status_for_record(row)
    outbound = str(row.get("direction") or "").lower() == "outbound"
    # ``caller_phone`` is the other party the console shows: for an outbound
    # attempt that is the number we dialled, not our own caller ID.
    remote, local = (row.get("to_number"), row.get("from_number")) if outbound else (row.get("from_number"), row.get("to_number"))
    item = {
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
        "caller_phone": remote,
        "called_phone": local,
        "summary": None,
        "status_tags": [],
        "has_recording": False,
        "has_transcript": False,
        # Dropped before the row leaves the server; used to find the callback it belongs to.
        "_control": row.get("provider_call_control_id"),
    }
    item.update(outcome_for_item(item))
    return item


def _call_to_item(row: dict[str, Any]) -> dict[str, Any]:
    status = status_for_record(row)
    item = {
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
        "status_tags": list(row.get("status_tags") or []),
        "has_recording": bool(row.get("has_recording")),
        "has_transcript": bool(row.get("summary")) or bool(row.get("has_transcript")),
    }
    item.update(outcome_for_item(item))
    return item


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
    tags: list[str] | None = None,
    tag_match: str = "any",
) -> tuple[list[dict[str, Any]], int]:
    """One chronological list of everything that rang, with canonical status.

    Browser practice sessions (``is_test``) are excluded unless ``include_tests``
    is set — they are not real conversations and must not inflate the rollups.
    A tag filter only ever matches connected calls: a ringing attempt has no
    transcript, so it has nothing to tag.
    """
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    wanted = set(normalize_call_statuses(statuses))
    wanted_tags = [str(tag).strip() for tag in (tags or []) if str(tag).strip()]

    # Each source is already ordered newest first, so the first ``offset + limit``
    # rows of the merged page can only come from the first ``offset + limit`` rows
    # of each source. Status/direction filters and totals are evaluated in SQL.
    fetch = min(offset + limit, _MAX_FETCH)
    calls, call_total = await call_store.list_calls(
        tenant_id=tenant_id,
        agent_id=agent_id,
        since=since,
        until=until,
        limit=fetch,
        offset=0,
        statuses=sorted(wanted) or None,
        direction=direction,
        include_tests=include_tests,
        tags=wanted_tags or None,
        tag_match=tag_match,
        max_limit=_MAX_FETCH,
    )
    items = [_call_to_item(c) for c in calls]
    total = call_total

    if wanted_tags:
        include_attempts = False
    if include_attempts:
        # An attempt linked to a connected call is represented by that call's row.
        attempts, attempt_total = await call_attempt_store.list_attempts(
            tenant_id=tenant_id,
            agent_id=agent_id,
            since=since,
            until=until,
            limit=fetch,
            offset=0,
            statuses=sorted(wanted) or None,
            direction=direction,
            exclude_linked=True,
            max_limit=_MAX_FETCH,
        )
        items.extend(_attempt_to_item(a) for a in attempts)
        total += attempt_total

    items = _dedupe(items)
    if direction:
        items = [i for i in items if i.get("direction") == direction]
    if wanted:
        items = [i for i in items if i.get("status") in wanted]
    items.sort(key=_sort_key, reverse=True)

    page = items[offset : offset + limit]
    await annotate_callbacks(page, tenant_id=tenant_id)
    return page, total


#: Callback modes a person or the follow-up worker dialled. "requested" rows are a
#: caller asking to be called, not a dial, and never mark a history row.
_DIALLED_CALLBACK_MODES = ("manual", "ai_redial", "scheduled")


async def annotate_callbacks(items: list[dict[str, Any]], *, tenant_id: str) -> None:
    """Mark callback dials and the calls they returned, in place.

    A callback is its own call or ringing attempt; without this it looks like an
    unrelated outgoing call, and the missed call never shows it was returned.
    Each row gets ``callback_of`` (this dial returned that call) and
    ``callbacks`` (how often this call was returned, and the latest result).
    Failure-tolerant: history without the links still renders.
    """
    for item in items:
        item.setdefault("callback_of", None)
        item.setdefault("callbacks", None)
    try:
        await _annotate_callbacks(items, tenant_id=tenant_id)
    except Exception:  # noqa: BLE001 -- annotation must never fail the history list.
        pass
    for item in items:
        item.pop("_control", None)


async def _annotate_callbacks(items: list[dict[str, Any]], *, tenant_id: str) -> None:
    import uuid as _uuid

    from sqlalchemy import or_, select

    from server.db.connection import get_session_factory
    from server.db.models.entities import CallAttempt, CallCallback
    from server.db.models.saas_models import User

    factory = get_session_factory()
    if factory is None or not items:
        return
    try:
        tid = _uuid.UUID(str(tenant_id))
    except (TypeError, ValueError):
        return

    def _uuid_or_none(value: Any) -> _uuid.UUID | None:
        try:
            return _uuid.UUID(str(value))
        except (TypeError, ValueError):
            return None

    row_ids = [u for u in (_uuid_or_none(i.get("call_id")) for i in items) if u]
    call_ids = [u for u in (_uuid_or_none(i.get("call_id")) for i in items if not i.get("is_attempt")) if u]
    async with factory() as session:
        # A connected call's carrier id lives on the attempt that rang it.
        control_by_call: dict[str, str] = {}
        if call_ids:
            linked = await session.execute(
                select(CallAttempt.linked_call_id, CallAttempt.provider_call_control_id).where(
                    CallAttempt.tenant_id == tid, CallAttempt.linked_call_id.in_(call_ids)
                )
            )
            control_by_call = {str(cid): ctl for cid, ctl in linked if ctl}
        controls = {str(i["_control"]) for i in items if i.get("_control")} | set(control_by_call.values())
        # A dial the carrier refused is recorded under "dialfail:<dial_request_id>".
        request_ids = {c.split(":", 1)[1] for c in controls if c.startswith("dialfail:")}
        filters = []
        if controls:
            filters.append(CallCallback.provider_call_control_id.in_(controls))
        if request_ids:
            filters.append(CallCallback.dial_request_id.in_(request_ids))
        if row_ids:
            filters += [CallCallback.original_call_id.in_(row_ids), CallCallback.original_attempt_id.in_(row_ids)]
        rows = (
            await session.execute(
                select(CallCallback)
                .where(CallCallback.tenant_id == tid, CallCallback.mode.in_(_DIALLED_CALLBACK_MODES), or_(*filters))
                .order_by(CallCallback.created_at.desc())
            )
        ).scalars().all()
        # What each callback dial actually did, from the attempt the carrier reported.
        result_by_control: dict[str, str] = {}
        dial_controls = {r.provider_call_control_id for r in rows if r.provider_call_control_id}
        if dial_controls:
            for control, linked_call, status, end_reason, direction in await session.execute(
                select(CallAttempt.provider_call_control_id, CallAttempt.linked_call_id, CallAttempt.status,
                       CallAttempt.end_reason, CallAttempt.direction)
                .where(CallAttempt.tenant_id == tid, CallAttempt.provider_call_control_id.in_(dial_controls))
            ):
                if linked_call is not None:
                    result_by_control[control] = "Answered"
                elif status == "in_progress":
                    result_by_control[control] = "Ringing"
                else:
                    words = outcome_for_item({"status": status, "direction": direction, "end_reason": end_reason})
                    result_by_control[control] = words.get("outcome_label") or "Ended"
        user_ids = {r.user_id for r in rows if r.user_id}
        names: dict[Any, str] = {}
        if user_ids:
            for uid, full_name, email in await session.execute(
                select(User.user_id, User.full_name, User.email).where(User.user_id.in_(user_ids))
            ):
                names[uid] = (full_name or "").strip() or email
    if not rows:
        return

    by_control = {r.provider_call_control_id: r for r in rows if r.provider_call_control_id}
    by_request = {r.dial_request_id: r for r in rows}
    for item in items:
        control = item.get("_control") or control_by_call.get(str(item.get("call_id")))
        cb = by_control.get(control) if control else None
        if cb is None and control and str(control).startswith("dialfail:"):
            cb = by_request.get(str(control).split(":", 1)[1])
        if cb is not None:
            original = cb.original_call_id or cb.original_attempt_id
            item["callback_of"] = {
                "id": str(original) if original else None,
                "mode": cb.mode,
                "by": names.get(cb.user_id) if cb.user_id else None,
                "at": cb.created_at.isoformat() if cb.created_at else None,
            }
        own = str(item.get("call_id"))
        returned = [
            r for r in rows
            if str(r.original_call_id or "") == own or str(r.original_attempt_id or "") == own
        ]
        if returned:
            latest = returned[0]
            item["callbacks"] = {
                "count": len(returned),
                "last_at": latest.created_at.isoformat() if latest.created_at else None,
                "last_status": latest.status,
                # "Answered", "Busy", "No answer"… or why the dial never rang.
                "last_result": result_by_control.get(latest.provider_call_control_id or "")
                or ("Not placed" if latest.status == "failed" else None),
                "last_mode": latest.mode,
            }


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
    include_attempts: bool = True,
) -> dict[str, Any]:
    """Counts and totals for the whole window, for the console's summary row."""
    from server.db.connection import get_session_factory
    if get_session_factory() is not None:
        from server.services.saas.agent_performance import performance
        return await performance(tenant_id, agent_id, since, until, include_attempts)
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
