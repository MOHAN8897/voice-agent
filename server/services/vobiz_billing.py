"""Use per-call Vobiz CDRs for cost reconciliation; never infer cost from balances."""
from __future__ import annotations

import asyncio
import logging
import math
from typing import Any

logger = logging.getLogger(__name__)


def nonnegative(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else None
    except (ValueError, TypeError, OverflowError):
        return None


def cdr_billing_fields(payload: dict, call_uuid: str) -> dict:
    data = payload.get("data", payload)
    if isinstance(data, list):
        data = next((row for row in data if isinstance(row, dict) and row.get("uuid") == call_uuid), {})
    if not isinstance(data, dict) or str(data.get("uuid") or "") != call_uuid:
        return {}
    seconds = nonnegative(data.get("billsec"))
    if seconds is None:
        return {}
    fields: dict[str, Any] = {
        "carrier_billable_duration_sec": int(seconds),
        "carrier_duration_source": "vobiz_cdr",
    }
    from server.call.billing_timing import utc_timestamp
    if data.get("answer_time"):
        fields["connected_at"] = utc_timestamp(data["answer_time"])
    if data.get("end_time"):
        fields["disconnected_at"] = utc_timestamp(data["end_time"])
    cost = nonnegative(data.get("total_cost"))
    currency = str(data.get("currency") or "").upper()
    if cost is not None and currency in {"USD", "INR"}:
        fields["carrier_billing"] = {
            "amount": cost, "currency": currency, "billable_seconds": int(seconds),
            "source": "vobiz_cdr", "includes_streaming": True,
        }
    return fields


async def reconcile_vobiz_call(call_id: str) -> bool:
    from server.call.call_ledger import call_ledger
    from server.services.vobiz_client import VobizClient

    meta = call_ledger.read_meta(call_id)
    call_uuid = str(meta.get("vobiz_call_uuid") or "")
    if meta.get("channel") != "pstn" or not call_uuid:
        return False
    client = VobizClient()
    if not client.configured:
        return False
    for attempt in range(2):
        try:
            payload = await asyncio.wait_for(client.get_call_cdr(call_uuid), timeout=6)
            fields = cdr_billing_fields(payload, call_uuid)
            if fields:
                # Re-read after the await so a late provider usage trailer is preserved.
                meta = call_ledger.read_meta(call_id)
                meta.update(fields)
                call_ledger.write_meta(call_id, meta)
                return True
        except Exception as exc:
            logger.info("[BILLING] carrier CDR unavailable call=%s kind=%s", call_id, type(exc).__name__)
            if getattr(exc, "status", None) not in {404, None}:
                break
        if attempt == 0:
            await asyncio.sleep(.4)
    return False
