"""Record what the caller wants about future contact, apart from the hangup reason.

"End this call" and "never call me again" are different outcomes. The close
reason stays a lifecycle value; the contact preference is its own field, and a
real opt-out is written to the tenant DNC list before the line closes so the
next outbound attempt sees it.
"""
from __future__ import annotations

import asyncio
from typing import Any

from server.call.close_decision import CONTACT_PREFERENCES
from server.utils.logger import log_pstn

_OPT_OUT_PERSIST_TIMEOUT_S = 2.0


def current_contact_preference(call_id: str | None) -> str:
    from server.call.call_context import get as get_ctx

    ctx = get_ctx(call_id) if call_id else None
    return str(getattr(ctx, "contact_preference", "") or "none")


def _stamp_meta(call_id: str | None, preference: str) -> str:
    if not call_id:
        return preference
    try:
        from server.call.call_ledger import call_ledger

        # Write even when meta.json does not exist yet: the lifecycle-end DNC
        # check reads this field after the live context is gone.
        meta = call_ledger.read_meta(call_id) or {}
        if meta.get("contact_preference") == "do_not_call":
            preference = "do_not_call"
        meta["contact_preference"] = preference
        call_ledger.write_meta(call_id, meta)
    except Exception as exc:
        log_pstn("contact_preference.meta_failed", call_id=call_id, error_type=type(exc).__name__)
    return preference


async def record_contact_preference(call_id: str | None, preference: Any) -> str:
    """Store the preference on the live call and enroll explicit opt-outs in DNC."""
    value = str(preference or "").strip().lower()
    if value not in CONTACT_PREFERENCES:
        value = "none"
    from server.call.call_context import get as get_ctx

    ctx = get_ctx(call_id) if call_id else None
    # A neutral later turn cannot undo an explicit opt-out. Renewed permission
    # belongs to the tenant's audited DND management flow, never a model label.
    previous = str(getattr(ctx, "contact_preference", "") or "")
    if call_id and previous != "do_not_call":
        from server.call.call_ledger import call_ledger
        meta = await asyncio.to_thread(call_ledger.read_meta, call_id)
        previous = str((meta or {}).get("contact_preference") or previous)
    if previous == "do_not_call" or getattr(ctx, "contact_preference", "") == "do_not_call":
        value = "do_not_call"
    value = _stamp_meta(call_id, value)
    if ctx is not None:
        ctx.contact_preference = value
    if value != "do_not_call" or not call_id:
        return value
    try:
        from server.services.saas.dnc_service import handle_call_opt_out

        enrolled = await asyncio.wait_for(
            handle_call_opt_out(call_id, disposition="do_not_call"),
            timeout=_OPT_OUT_PERSIST_TIMEOUT_S,
        )
        log_pstn("contact_preference.dnc", call_id=call_id, enrolled=bool(enrolled))
    except Exception as exc:
        # The lifecycle end repeats the check from the recorded preference.
        log_pstn("contact_preference.dnc_failed", call_id=call_id, error_type=type(exc).__name__)
    return value
