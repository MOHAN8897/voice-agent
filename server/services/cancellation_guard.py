"""Confirm with the caller before an in-call action cancels a booking.

Asked to move a site visit to another time, the model cancelled the booking
and then only offered to book the new time: the caller was left with no
appointment while believing it had been moved. A cancellation is destructive
and a reschedule action exists, so the first cancel attempt on a call asks the
caller to choose. It goes through only after the caller has answered since
(the model repeats it on a "yes, cancel it"); on "move it" the model reschedules.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Any

CANCEL_ACTIONS = frozenset({"GOOGLECALENDAR_CANCEL_EVENT", "GOOGLECALENDAR_DELETE_EVENT", "CALCOM_CANCEL_BOOKING"})
_MAX_PENDING = 4096
_pending: OrderedDict[tuple[str, str, str], int] = OrderedDict()


def check(call_id: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
    """None when the cancellation may run; otherwise a result asking the caller first."""
    name = str(tool_name or "").upper()
    if name not in CANCEL_ACTIONS or not call_id:
        return None
    from server.services.recipient_guard import caller_turns

    target = str(arguments.get("event_id") or arguments.get("booking_id") or arguments.get("uid") or "")
    key = (str(call_id), name, target)
    turns = len(caller_turns(call_id))
    asked = _pending.get(key)
    if asked is not None and turns > asked:
        _pending.pop(key, None)
        return None
    _pending[key] = turns
    _pending.move_to_end(key)
    while len(_pending) > _MAX_PENDING:
        _pending.popitem(last=False)
    return {
        "status": "needs_confirmation",
        "message": ("Nothing was cancelled. Ask the caller whether they want to cancel this appointment completely, "
                    "or move it to another time. To move it, use the reschedule action, which keeps the booking. "
                    "Only if they confirm a full cancellation, do this again with the same appointment."),
    }


def reset_for_tests() -> None:
    _pending.clear()
