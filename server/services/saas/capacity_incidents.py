"""Record calls and purchases refused for lack of capacity, for the admin capacity page.

Best-effort and never raises into a call path. One row per kind, workspace and
minute with a running count, so a campaign retrying every few seconds leaves a
readable trail rather than thousands of rows.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from server.db.connection import get_session_factory

logger = logging.getLogger(__name__)

#: kind -> (scope, operator wording). Scope "tenant" is the workspace's own
#: limit; "platform" means the shared Vobiz capacity: that is what to buy.
KINDS: dict[str, tuple[str, str]] = {
    "tenant_limit": ("tenant", "Workspace used all its channels"),
    "platform_full": ("platform", "Every channel on the Vobiz account was busy"),
    "reserved_full": ("platform", "Free capacity used up: what is left is held for workspaces' numbers and paid channels"),
    "cps_paced": ("platform", "Dialling speed (CPS) limit reached; call waited its turn"),
    "tenant_cps_paced": ("tenant", "Workspace dialling speed limit reached; call waited its turn"),
    "carrier_capacity": ("platform", "Vobiz refused the call: account concurrency or CPS limit"),
    "number_blocked": ("platform", "Number purchase refused: no free channel to give the new number"),
    "channel_blocked": ("platform", "Paid channel purchase refused: not enough Vobiz capacity"),
}
PLATFORM_KINDS = frozenset(k for k, (scope, _) in KINDS.items() if scope == "platform")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def record(kind: str, tenant_id: uuid.UUID | str | None = None, *, detail: str | None = None) -> None:
    factory = get_session_factory()
    if factory is None or kind not in KINDS:
        return
    try:
        tid = uuid.UUID(str(tenant_id)) if tenant_id else None
    except (TypeError, ValueError):
        tid = None  # e.g. a dev-portal session without a workspace
    from sqlalchemy.exc import IntegrityError

    for attempt in range(2):
        try:
            await _upsert(factory, kind, tid, detail)
            break
        except IntegrityError:
            # Another process created this minute's row first: add to it instead.
            if attempt:
                logger.debug("[CAPACITY] incident not recorded kind=%s (conflict)", kind)
        except Exception as exc:  # noqa: BLE001 -- observability must never block a call
            logger.debug("[CAPACITY] incident not recorded kind=%s err=%s", kind, type(exc).__name__)
            break
    if kind in PLATFORM_KINDS:
        logger.warning("[CAPACITY] %s tenant=%s", kind, tid or "-")


async def _upsert(factory, kind: str, tid: uuid.UUID | None, detail: str | None) -> None:
    from server.db.models.concurrency_models import CapacityIncident

    now = _now()
    tenant_key = str(tid) if tid else "platform"
    row_id = f"{now.strftime('%Y%m%d%H%M')}:{kind}:{tenant_key}"
    async with factory() as db:
        row = await db.get(CapacityIncident, row_id, with_for_update=True)
        if row is None:
            db.add(CapacityIncident(id=row_id, kind=kind, tenant_key=tenant_key, tenant_id=tid, count=1,
                                    detail=(detail or "")[:300] or None, created_at=now, last_seen_at=now))
        else:
            row.count = int(row.count or 0) + 1
            row.last_seen_at = now
            if detail:
                row.detail = detail[:300]
        await db.commit()


async def recent(*, hours: int = 72, limit: int = 200) -> list[dict[str, Any]]:
    """Newest first, with tenant names, for the admin page."""
    factory = get_session_factory()
    if factory is None:
        return []
    from server.db.models.concurrency_models import CapacityIncident
    from server.db.models.entities import Tenant

    since = _now() - timedelta(hours=max(1, min(hours, 24 * 30)))
    try:
        async with factory() as db:
            rows = (await db.execute(
                select(CapacityIncident, Tenant.name)
                .outerjoin(Tenant, Tenant.tenant_id == CapacityIncident.tenant_id)
                .where(CapacityIncident.last_seen_at >= since)
                .order_by(CapacityIncident.last_seen_at.desc()).limit(limit)
            )).all()
    except Exception as exc:  # noqa: BLE001 -- table absent before migration
        logger.info("[CAPACITY] incidents unavailable: %s", type(exc).__name__)
        return []
    out = []
    for inc, name in rows:
        scope, label = KINDS.get(inc.kind, ("platform", inc.kind))
        out.append({
            "kind": inc.kind, "scope": scope, "label": label, "count": int(inc.count or 0),
            "tenantId": str(inc.tenant_id) if inc.tenant_id else None, "tenantName": name,
            "detail": inc.detail,
            "firstAt": _aware(inc.created_at).isoformat(), "lastAt": _aware(inc.last_seen_at).isoformat(),
        })
    return out


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def summarize(items: list[dict[str, Any]], *, hours: int = 24) -> dict[str, int]:
    """Counts per kind within the last `hours` (items come from :func:`recent`)."""
    since = _now() - timedelta(hours=hours)
    out: dict[str, int] = {}
    for item in items:
        if datetime.fromisoformat(item["lastAt"]) >= since:
            out[item["kind"]] = out.get(item["kind"], 0) + int(item["count"])
    return out
