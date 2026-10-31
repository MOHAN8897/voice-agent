"""The customer clock starts when a call is connected, independently of API usage."""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def utc_timestamp(value=None) -> str:
    if value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except (ValueError, TypeError):
            pass
    return datetime.now(timezone.utc).isoformat()


def mark_call_connected(call_id: str | None, at=None) -> None:
    if not call_id:
        return
    from server.call.call_ledger import call_ledger

    try:
        meta = call_ledger.read_meta(call_id)
        if meta and not meta.get("connected_at"):
            meta["connected_at"] = utc_timestamp(at)
            meta["billing_timing_version"] = 2
            call_ledger.write_meta(call_id, meta)
    except (OSError, ValueError):
        logger.error("[BILLING] could not persist connected clock call=%s", call_id)


def mark_call_disconnected(call_id: str | None, at=None) -> None:
    if not call_id:
        return
    from server.call.call_ledger import call_ledger

    try:
        meta = call_ledger.read_meta(call_id)
        if meta and not meta.get("disconnected_at"):
            meta["disconnected_at"] = utc_timestamp(at)
            call_ledger.write_meta(call_id, meta)
    except (OSError, ValueError):
        logger.error("[BILLING] could not persist disconnected clock call=%s", call_id)
