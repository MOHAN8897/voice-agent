"""Prevent duplicate PSTN outbound dials to the same destination."""
from __future__ import annotations

import asyncio
import time
from typing import Any

_ACTIVE_CALL_STATUSES = {
    "initiated",
    "ringing",
    "answered",
    "streaming",
    "bridged",
    "active",
    "queued",
    "in-progress",
    "in_progress",
}

# Terminal / zombie rows must never block a new Place Call.
_TERMINAL_CALL_STATUSES = {
    "hangup",
    "completed",
    "failed",
    "busy",
    "no-answer",
    "no_answer",
    "canceled",
    "cancelled",
    "ended",
    "stream-error",
    "stream-stopped",
    "stream-ended",
}

INFLIGHT_TTL_SEC = 45.0
# Ringing/queued rows older than this are zombies (provider never progressed).
# Answered/streaming calls are never replaced, regardless of age.
STALE_RING_SEC = 180.0
# Kept for tests/callers that still import the old reuse window name.
RECENT_DIAL_REUSE_SEC = STALE_RING_SEC

_LIVE_LEG_STATUSES = {
    "answered",
    "streaming",
    "bridged",
    "active",
    "in-progress",
    "in_progress",
}

_outbound_lock = asyncio.Lock()
_inflight: dict[str, float] = {}


def _normalize_dest_e164(value: str) -> str:
    from server.services.saas.inbound_routing import _normalize_e164

    normalized = _normalize_e164((value or "").strip())
    return normalized or (value or "").strip()


def dest_digits(value: str) -> str:
    """Legacy ten-digit helper — prefer _normalize_dest_e164 for matching."""
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


def _dest_matches(row_to: str, to_e164: str) -> bool:
    return _normalize_dest_e164(row_to) == _normalize_dest_e164(to_e164)


def _slot_key(provider: str, to_e164: str) -> str:
    return f"{provider}:{_normalize_dest_e164(to_e164)}"


def _is_active_status(status: str) -> bool:
    raw = (status or "").strip().lower().replace("call.", "")
    if raw in _TERMINAL_CALL_STATUSES:
        return False
    return raw in _ACTIVE_CALL_STATUSES


def _row_age_sec(row: dict[str, Any], now: float | None = None) -> float:
    started = float(row.get("first_seen_at") or row.get("dialed_at") or 0)
    if started <= 0:
        return 0.0
    return (now if now is not None else time.time()) - started


def _status_slug(status: str) -> str:
    return (status or "").strip().lower().replace("call.", "")


def _is_live_leg(row: dict[str, Any]) -> bool:
    if row.get("ended"):
        return False
    raw = _status_slug(str(row.get("status") or ""))
    if raw in _TERMINAL_CALL_STATUSES:
        return False
    return raw in _LIVE_LEG_STATUSES


def _is_replaceable_telnyx_row(row: dict[str, Any], now: float | None = None) -> bool:
    """Hang up only voice-check / skip-stream legs, or a ringing row stuck for minutes."""
    if row.get("voice_check") or row.get("skip_stream"):
        return True
    if not _is_active_status(str(row.get("status") or "")):
        return False
    if _is_live_leg(row):
        return False
    return _row_age_sec(row, now) >= STALE_RING_SEC


async def acquire_outbound_slot(provider: str, to_e164: str) -> bool:
    """Return False when another outbound to this destination is already in flight."""
    key = _slot_key(provider, to_e164)
    now = time.monotonic()
    async with _outbound_lock:
        ts = _inflight.get(key)
        if ts is not None and now - ts < INFLIGHT_TTL_SEC:
            return False
        _inflight[key] = now
        return True


def release_outbound_slot(provider: str, to_e164: str) -> None:
    _inflight.pop(_slot_key(provider, to_e164), None)


def peek_reusable_telnyx_call(to_e164: str) -> dict[str, Any] | None:
    """Return the live/ringing call to this dest so a duplicate Place Call no-ops."""
    from server.services.telnyx_client import telnyx_call_registry

    if not _normalize_dest_e164(to_e164):
        return None
    now = time.time()
    for row in telnyx_call_registry.list_recent(None):
        if not _dest_matches(str(row.get("to") or row.get("callee_e164") or ""), to_e164):
            continue
        if row.get("ended"):
            continue
        if not _is_active_status(str(row.get("status") or "")):
            continue
        if _is_replaceable_telnyx_row(row, now):
            continue
        return row
    return None


async def hangup_active_telnyx_to(client: Any, to_e164: str) -> None:
    from server.services.telnyx_client import TelnyxApiError, telnyx_call_registry

    if not _normalize_dest_e164(to_e164):
        return
    now = time.time()
    for row in telnyx_call_registry.list_recent(None):
        if not _dest_matches(str(row.get("to") or row.get("callee_e164") or ""), to_e164):
            continue
        if row.get("ended"):
            continue
        status = str(row.get("status") or "")
        if not _is_active_status(status):
            continue
        control = str(row.get("call_control_id") or "")
        if not control:
            continue
        if not _is_replaceable_telnyx_row(row, now):
            continue
        try:
            await client.hangup(control)
            telnyx_call_registry.upsert(control, {"status": "canceled", "last_event": "replaced-by-new-dial"})
        except TelnyxApiError:
            pass



async def hangup_active_plivo_to(to_e164: str) -> None:
    from server.services.plivo_client import PlivoApiError, PlivoClient, plivo_call_registry

    dest = (to_e164 or "").strip()
    if not dest:
        return
    client = PlivoClient()
    for row in plivo_call_registry.list_recent(20):
        if str(row.get("to") or "").strip() != dest:
            continue
        if not _is_active_status(str(row.get("status") or "")):
            continue
        call_uuid = str(row.get("call_uuid") or row.get("request_uuid") or "")
        if not call_uuid:
            continue
        try:
            await client.hangup(call_uuid)
            plivo_call_registry.upsert(call_uuid, {"status": "canceled", "last_event": "replaced-by-new-dial"})
        except PlivoApiError:
            pass


async def hangup_active_vobiz_to(to_e164: str) -> int:
    from server.services.vobiz_client import VobizApiError, VobizClient, vobiz_call_registry

    dest = (to_e164 or "").strip()
    if not dest:
        return 0
    client = VobizClient()
    cancelled_count = 0
    for row in vobiz_call_registry.list_recent(20):
        if not _dest_matches(str(row.get("to") or ""), to_e164):
            continue
        if row.get("ended"):
            continue
        if not _is_active_status(str(row.get("status") or "")):
            continue
        call_uuid = str(row.get("call_uuid") or row.get("request_uuid") or "")
        if not call_uuid:
            continue
        try:
            await client.hangup_call(call_uuid)
            vobiz_call_registry.upsert(
                call_uuid,
                {"status": "canceled", "last_event": "replaced-by-new-dial", "ended": True},
            )
            cancelled_count += 1
        except Exception:
            pass
    return cancelled_count

