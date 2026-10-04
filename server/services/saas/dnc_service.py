"""Authoritative DND and live call opt-out auto-enrollment service."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

logger = logging.getLogger(__name__)

_OPT_OUT_DISPOSITIONS = frozenset({"opt_out", "optout", "do_not_call", "dnc", "opt_out_live_call"})


async def auto_enroll_dnc_opt_out(tenant_id: uuid.UUID | str, phone: str) -> bool:
    """Atomic upsert of opt-out into tenant's dnc_list.
    
    If the phone already exists (even if previously deactivated), reactivate it.
    """
    from server.db.connection import get_session_factory
    from server.db.models.phase5_models import DncEntry
    from server.services.saas.contact_import_service import normalize_e164_phone

    clean_phone = str(phone or "").strip()
    if not clean_phone:
        return False
    norm, _ = normalize_e164_phone(clean_phone, "US")
    normalized_phone = norm or clean_phone
    if not normalized_phone:
        return False

    tid = uuid.UUID(str(tenant_id)) if isinstance(tenant_id, (str, uuid.UUID)) else None
    if not tid:
        return False

    factory = get_session_factory()
    if not factory:
        return False

    now = datetime.now(timezone.utc)
    async with factory() as session:
        bind = session.bind
        dialect_name = bind.dialect.name if bind else ""
        if dialect_name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            stmt = (
                pg_insert(DncEntry)
                .values(
                    id=uuid.uuid4(),
                    tenant_id=tid,
                    phone_e164=normalized_phone,
                    reason="verbal_opt_out_live_call",
                    source="live_call_opt_out",
                    active=True,
                    added_at=now,
                    removed_at=None,
                    removed_by_user_id=None,
                    removal_reason=None,
                    reconsent_confirmed=False,
                )
                .on_conflict_do_update(
                    index_elements=["tenant_id", "phone_e164"],
                    set_={
                        "active": True,
                        "reason": "verbal_opt_out_live_call",
                        "source": "live_call_opt_out",
                        "added_at": now,
                        "removed_at": None,
                        "removed_by_user_id": None,
                        "removal_reason": None,
                        "reconsent_confirmed": False,
                    },
                )
            )
            await session.execute(stmt)
        else:
            existing = await session.execute(
                select(DncEntry).where(DncEntry.tenant_id == tid, DncEntry.phone_e164 == normalized_phone)
            )
            row = existing.scalar_one_or_none()
            if row:
                row.active = True
                row.reason = "verbal_opt_out_live_call"
                row.source = "live_call_opt_out"
                row.added_at = now
                row.removed_at = None
                row.removed_by_user_id = None
                row.removal_reason = None
                row.reconsent_confirmed = False
            else:
                session.add(
                    DncEntry(
                        id=uuid.uuid4(),
                        tenant_id=tid,
                        phone_e164=normalized_phone,
                        reason="verbal_opt_out_live_call",
                        source="live_call_opt_out",
                        active=True,
                        added_at=now,
                    )
                )
        await session.commit()
        logger.info("[DNC] Tenant-wide auto-enrollment for %s (tenant %s) on verbal opt-out", normalized_phone, tid)
        return True


async def handle_call_opt_out(
    call_id: str,
    *,
    reason: str | None = None,
    disposition: str | None = None,
) -> bool:
    """Inspects call termination reason/disposition and auto-enrolls into DND if opt-out occurred."""
    is_opt_out = (
        (reason and str(reason).strip().lower() == "opt_out")
        or (disposition and str(disposition).strip().lower() in _OPT_OUT_DISPOSITIONS)
    )
    if not is_opt_out:
        return False

    from server.call.call_context import get as get_call_ctx
    from server.call.call_ledger import call_ledger
    from server.call.call_store import call_store

    ctx = get_call_ctx(call_id)
    stored = await call_store.get(call_id)
    meta = call_ledger.read_meta(call_id) or {}

    tenant_id = (ctx.tenant_id if ctx else None) or (stored or {}).get("tenant_id")
    if not tenant_id:
        return False

    direction = (
        (ctx.direction if ctx else None)
        or (stored or {}).get("direction")
        or meta.get("direction")
        or "inbound"
    )
    direction_norm = str(direction).strip().lower()

    target_phone: str | None = None
    if direction_norm in ("outbound", "outgoing", "outbound-api"):
        target_phone = (
            meta.get("callee_e164")
            or meta.get("to_e164")
            or meta.get("to")
            or (stored or {}).get("destination_phone")
            or (stored or {}).get("to_e164")
        )
    else:
        target_phone = (
            meta.get("caller_id")
            or meta.get("from_e164")
            or meta.get("from")
            or (stored or {}).get("caller_id")
        )

    # Fallback to any phone recorded
    if not target_phone:
        target_phone = meta.get("callee_e164") or meta.get("caller_id") or meta.get("to_e164")

    if not target_phone:
        logger.warning("[DNC] Could not resolve phone number for opt-out on call %s", call_id)
        return False

    return await auto_enroll_dnc_opt_out(tenant_id, target_phone)
