"""Admin call-capacity page: what the platform owns, what tenants need, when to buy.

Vobiz sells concurrency (simultaneous calls) and CPS (new calls per second) on
the parent account only; every tenant shares them. The platform holds one
channel per number sold plus every paid channel (``concurrency_service``), so
"what we must own" is at least the held total, and real peaks on top.

Buying a bundle (:func:`purchase`) debits the Vobiz balance. It runs only on an
explicit admin confirmation of the live Vobiz price, one request id buys once,
and an unanswered purchase blocks further buys until the admin has checked
Vobiz, because Vobiz itself says never to retry a timed-out purchase.
"""
from __future__ import annotations

import logging
import math
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select

from server.db.connection import get_session_factory

logger = logging.getLogger(__name__)

#: Utilisation (held channels or real peak, whichever is higher) that turns the signal amber / red.
WARN_PCT = 70
CRITICAL_PCT = 90
#: Headroom the estimate keeps above the highest of held channels and real peak.
HEADROOM = Decimal("1.2")
RESOURCE_LABEL = {"concurrent_calls": "concurrent calls", "cps": "CPS"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _http(status: int, code: str, message: str, **extra: Any) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": {"code": code, "message": message, **extra}})


def round_up_to_block(n: int, block: int) -> int:
    if n <= 0:
        return 0
    block = max(1, int(block))
    return int(math.ceil(n / block) * block)


def estimate(*, owned: int, held: int, peak: int, block: int, platform_incidents_24h: int) -> dict[str, Any]:
    """How many concurrent calls to own, and how many to buy now (rounded to Vobiz blocks)."""
    need = max(held, peak)
    recommended = int(math.ceil(Decimal(need) * HEADROOM)) if need else 0
    # Calls were refused for platform capacity today: one block more, whatever the arithmetic says.
    if platform_incidents_24h and recommended <= owned:
        recommended = owned + 1
    shortfall = max(0, recommended - owned)
    return {
        "required": need,
        "recommended": recommended,
        "shortfall": shortfall,
        "buy": round_up_to_block(shortfall, block),
        "blockSize": block,
        "utilizationPct": int(round(need * 100 / owned)) if owned else (100 if need else 0),
    }


def signals(*, configured: bool, owned: int, held: int, peak: int, vobiz_max: int | None,
            vobiz_cps: int | None, owned_cps: int, incidents: dict[str, int], est: dict[str, Any]) -> list[dict[str, Any]]:
    """Plain-language alerts, worst first. level: critical | warning | info | ok."""
    out: list[dict[str, Any]] = []
    if not configured:
        out.append({"level": "warning", "code": "not_configured",
                    "title": "Channel rules are not switched on",
                    "detail": "Numbers do not hold channels and the platform pool is not enforced yet. Save the capacity settings below to start.",
                    "action": "Save capacity settings"})
    if vobiz_max is not None and owned > vobiz_max:
        out.append({"level": "critical", "code": "above_vobiz",
                    "title": f"Capacity is set to {owned} but Vobiz allows {vobiz_max}",
                    "detail": "Calls above the Vobiz limit are refused by Vobiz (SIP 429) and fail.",
                    "action": "Use the Vobiz limit, or buy more concurrency"})
    if vobiz_max is not None and vobiz_max > owned:
        out.append({"level": "info", "code": "below_vobiz",
                    "title": f"Vobiz allows {vobiz_max} calls but only {owned} are in use here",
                    "detail": "You are paying Vobiz for capacity tenants cannot use.",
                    "action": "Use the Vobiz limit"})
    if held > owned:
        out.append({"level": "critical", "code": "overcommitted",
                    "title": f"{held} channels are promised to tenants but only {owned} exist",
                    "detail": "Numbers and paid channels hold more channels than the platform owns, so some held calls can be refused.",
                    "action": f"Buy {est['buy'] or est['shortfall']} concurrent calls"})
    platform_refusals = sum(incidents.get(k, 0) for k in ("platform_full", "reserved_full", "carrier_capacity"))
    if platform_refusals:
        out.append({"level": "critical", "code": "calls_refused",
                    "title": f"{platform_refusals} call attempts were refused for capacity in the last 24 hours",
                    "detail": "Tenants saw \"all lines busy\" (campaign calls waited and retried).",
                    "action": f"Buy {est['buy']} concurrent calls" if est["buy"] else "Review the incidents below"})
    if incidents.get("number_blocked") or incidents.get("channel_blocked"):
        n = incidents.get("number_blocked", 0) + incidents.get("channel_blocked", 0)
        out.append({"level": "critical", "code": "sales_blocked",
                    "title": f"{n} number or channel purchases were refused: no capacity left to hold",
                    "detail": "Tenants could not buy. They were not charged.",
                    "action": f"Buy {est['buy'] or est['blockSize']} concurrent calls"})
    util = est["utilizationPct"]
    if owned and util >= CRITICAL_PCT and not any(s["code"] in ("overcommitted", "calls_refused") for s in out):
        out.append({"level": "critical", "code": "near_full",
                    "title": f"Capacity is {util}% used",
                    "detail": "New numbers will soon be refused and busy hours will see \"all lines busy\".",
                    "action": f"Buy {est['buy'] or est['blockSize']} concurrent calls"})
    elif owned and util >= WARN_PCT:
        out.append({"level": "warning", "code": "filling_up",
                    "title": f"Capacity is {util}% used",
                    "detail": "Time to plan the next Vobiz bundle before tenants are refused.",
                    "action": f"Buy {est['buy'] or est['blockSize']} concurrent calls"})
    paced = incidents.get("cps_paced", 0)
    if paced:
        out.append({"level": "warning" if paced < 100 else "critical", "code": "cps_paced",
                    "title": f"Calls waited for dialling speed {paced} times in the last 24 hours",
                    "detail": f"The platform starts at most {owned_cps} new call(s) per second across all tenants. Campaigns slow down; nothing is lost.",
                    "action": "Buy more CPS if campaigns are too slow"})
    if vobiz_cps is not None and owned_cps > vobiz_cps:
        out.append({"level": "critical", "code": "cps_above_vobiz",
                    "title": f"Dialling speed is set to {owned_cps} CPS but Vobiz allows {vobiz_cps}",
                    "detail": "Vobiz refuses calls started faster than its CPS limit.",
                    "action": "Use the Vobiz limit, or buy more CPS"})
    if not out:
        out.append({"level": "ok", "code": "healthy", "title": "Capacity is healthy",
                    "detail": f"{max(0, owned - held)} channels are free to hold for new numbers or paid channels.",
                    "action": None})
    order = {"critical": 0, "warning": 1, "info": 2, "ok": 3}
    return sorted(out, key=lambda s: order[s["level"]])


async def _daily_peaks(db, days: int) -> tuple[dict[uuid.UUID, dict[str, int]], int]:
    """Per tenant {peak, rejected, queued} over `days`, and the platform's peak day (sum of tenant peaks)."""
    from server.db.models.concurrency_models import TenantConcurrencyDaily

    since = _now().date() - timedelta(days=days - 1)
    rows = (await db.execute(select(TenantConcurrencyDaily).where(TenantConcurrencyDaily.day >= since))).scalars().all()
    per: dict[uuid.UUID, dict[str, int]] = {}
    by_day: Counter = Counter()
    for row in rows:
        item = per.setdefault(row.tenant_id, {"peak": 0, "rejected": 0, "queued": 0})
        item["peak"] = max(item["peak"], int(row.peak_active or 0))
        item["rejected"] += int(row.rejected or 0)
        item["queued"] += int(row.queued or 0)
        by_day[row.day] += int(row.peak_active or 0)
    return per, max(by_day.values(), default=0)


async def _peak_cps(db, hours: int = 24) -> int:
    """Most outbound dial requests started in one second over the last `hours`."""
    from server.db.models.phase5_models import PstnDialRequest

    since = _now() - timedelta(hours=hours)
    stamps = (await db.execute(select(PstnDialRequest.created_at).where(
        PstnDialRequest.created_at >= since, PstnDialRequest.destination_hash.is_not(None),
    ).limit(50000))).scalars().all()
    seconds = Counter(_aware(t).replace(microsecond=0) for t in stamps if t)
    return max(seconds.values(), default=0)


async def overview() -> dict[str, Any]:
    from server.config.env import get_settings
    from server.db.models.entities import Tenant
    from server.services.saas import capacity_incidents
    from server.services.saas import concurrency_service as channels
    from server.services.saas import capacity_policy
    from server.services.saas import vobiz_concurrency as vobiz

    settings = get_settings()
    policy = await capacity_policy.load_policy()
    config = await channels.load_pricing(force=True)
    effective = config or {"platformCapacity": channels.legacy_caps(settings, {})[1], "includedChannels": 0,
                           "channelsPerNumber": channels.DEFAULT_CHANNELS_PER_NUMBER,
                           "concurrencyBlockSize": channels.DEFAULT_CONCURRENCY_BLOCK, "platformCps": 0}
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    async with factory() as db:
        held = await channels.held_by_tenant(db, effective)
        active = await channels.active_by_tenant(db)
        try:
            peaks7, platform_peak7 = await _daily_peaks(db, 7)
            _, platform_peak30 = await _daily_peaks(db, 30)
        except Exception:  # noqa: BLE001 -- before migration 049
            peaks7, platform_peak7, platform_peak30 = {}, 0, 0
        peak_cps = await _peak_cps(db)
        ids = set(held) | set(active) | set(peaks7)
        names = dict((await db.execute(select(Tenant.tenant_id, Tenant.name).where(Tenant.tenant_id.in_(ids))))
                     .all()) if ids else {}
        limits = dict((await db.execute(select(Tenant.tenant_id, Tenant.limits).where(Tenant.tenant_id.in_(ids))))
                      .all()) if ids else {}
    incidents = await capacity_incidents.recent(hours=72)
    counts_24h = capacity_incidents.summarize(incidents, hours=24)
    tenant_incidents: Counter = Counter()
    for item in incidents:
        if item["tenantId"] and datetime.fromisoformat(item["lastAt"]) >= _now() - timedelta(hours=24):
            tenant_incidents[item["tenantId"]] += item["count"]

    owned = int(effective["platformCapacity"])
    owned_cps = channels.platform_cps(config, settings)
    held_total = sum(r["held"] for r in held.values())
    live = sum(active.values())
    block = int(effective.get("concurrencyBlockSize") or channels.DEFAULT_CONCURRENCY_BLOCK)
    vobiz_live = await vobiz.fetch_platform_concurrency()
    vobiz_limits = await vobiz.fetch_account_limits()
    vobiz_max = vobiz_live.get("maxConcurrent") if vobiz_live.get("available") else vobiz_limits.get("concurrentLimit")
    vobiz_cps = vobiz_limits.get("cpsLimit") if vobiz_limits.get("available") else None
    platform_incidents = sum(counts_24h.get(k, 0) for k in ("platform_full", "reserved_full", "carrier_capacity",
                                                              "number_blocked", "channel_blocked"))
    est = estimate(owned=owned, held=held_total, peak=platform_peak30, block=block,
                   platform_incidents_24h=platform_incidents)
    default_included = int(effective.get("includedChannels") or 0)
    tenants = []
    for tid in ids:
        h = held.get(tid, {"numbers": 0, "numberChannels": 0, "paid": 0, "held": 0})
        lim = limits.get(tid) or {}
        included = int(lim.get("included_channels") if lim.get("included_channels") is not None else default_included)
        p = peaks7.get(tid, {"peak": 0, "rejected": 0, "queued": 0})
        tenants.append({
            "tenantId": str(tid), "name": names.get(tid) or "Unknown workspace",
            "numbers": h["numbers"], "numberChannels": h["numberChannels"], "paidChannels": h["paid"],
            "held": h["held"], "included": included, "cap": min(owned, included + h["held"]),
            "activeNow": active.get(tid, 0), "peak7d": p["peak"], "rejected7d": p["rejected"],
            "queued7d": p["queued"], "incidents24h": tenant_incidents.get(str(tid), 0),
        })
    tenants.sort(key=lambda t: (-t["held"], -t["peak7d"], t["name"]))
    return {
        "configured": bool(config),
        "settings": channels.public_pricing(config),
        "concurrency": {
            "owned": owned, "vobizLimit": vobiz_max,
            "vobizLive": vobiz_live.get("concurrentCalls") if vobiz_live.get("available") else None,
            "held": held_total, "heldByNumbers": sum(r["numberChannels"] for r in held.values()),
            "heldByPaid": sum(r["paid"] for r in held.values()),
            "freeToHold": max(0, owned - held_total),
            "numbersSellable": (max(0, owned - held_total) // int(effective.get("channelsPerNumber") or 1))
                               if int(effective.get("channelsPerNumber") or 0) else None,
            "live": live, "available": max(0, owned - live),
            "peak7d": platform_peak7, "peak30d": platform_peak30,
        },
        "cps": {"owned": owned_cps, "vobizLimit": vobiz_cps, "peak24h": peak_cps,
                "paced24h": counts_24h.get("cps_paced", 0)},
        "vobiz": {"available": bool(vobiz_live.get("available") or vobiz_limits.get("available")),
                  "limits": vobiz_limits if vobiz_limits.get("available") else None},
        "estimate": est,
        "signals": signals(configured=bool(config), owned=owned, held=held_total, peak=platform_peak30,
                           vobiz_max=vobiz_max, vobiz_cps=vobiz_cps, owned_cps=owned_cps,
                           incidents=counts_24h, est=est),
        "incidentCounts24h": counts_24h,
        "incidents": incidents[:100],
        "tenants": tenants,
        "purchases": await list_purchases(limit=20),
        "policy": {**policy, "autoBuySpent30d": str(await capacity_policy.auto_buy_commitment())},
        "approvals": await capacity_policy.queue(),
    }


# ---------------------------------------------------------------------------
# Buying Vobiz bundles
# ---------------------------------------------------------------------------

def _purchase_payload(row: Any) -> dict[str, Any]:
    return {
        "id": str(row.id), "requestId": row.request_id, "resourceType": row.resource_type,
        "resourceLabel": RESOURCE_LABEL.get(row.resource_type, row.resource_type), "quantity": row.quantity,
        "quotedMonthlyCost": row.quoted_monthly_cost, "monthlyCost": row.monthly_cost, "currency": row.currency,
        "status": row.status, "vobizSubscriptionId": row.vobiz_subscription_id,
        "nextBillingDate": row.next_billing_date, "error": row.error, "actor": row.actor, "reason": row.reason,
        "createdAt": _aware(row.created_at).isoformat() if row.created_at else None,
        "updatedAt": _aware(row.updated_at).isoformat() if row.updated_at else None,
    }


async def list_purchases(limit: int = 20) -> list[dict[str, Any]]:
    factory = get_session_factory()
    if factory is None:
        return []
    from server.db.models.concurrency_models import VobizCapacityPurchase

    try:
        async with factory() as db:
            rows = (await db.execute(select(VobizCapacityPurchase).order_by(
                VobizCapacityPurchase.created_at.desc()).limit(limit))).scalars().all()
    except Exception as exc:  # noqa: BLE001 -- before migration 053
        logger.info("[CAPACITY] purchases unavailable: %s", type(exc).__name__)
        return []
    return [_purchase_payload(r) for r in rows]


async def preview(resource_type: str, quantity: int) -> dict[str, Any]:
    from server.services.saas import vobiz_concurrency as vobiz

    try:
        price = await vobiz.preview_channel_price(quantity, resource_type=resource_type)
    except ValueError as exc:
        raise _http(422, "invalid_quantity", str(exc)) from exc
    return {"price": price, "balance": await vobiz.fetch_balance(), "blocked": await _unresolved_purchase()}


#: Serializes Vobiz bundle purchases across API processes (PostgreSQL only).
_PURCHASE_LOCK_KEY = 4_904_903_002


async def _unresolved_in(db) -> Any:
    from server.db.models.concurrency_models import VobizCapacityPurchase

    # No time limit: Vobiz may have charged for it, so only an admin's check clears it.
    return (await db.execute(select(VobizCapacityPurchase).where(
        VobizCapacityPurchase.status.in_(("pending", "unknown")),
    ).order_by(VobizCapacityPurchase.created_at.desc()).limit(1))).scalar_one_or_none()


async def _unresolved_purchase() -> dict[str, Any] | None:
    """A recent purchase with no definite answer from Vobiz, which must be checked first."""
    factory = get_session_factory()
    if factory is None:
        return None
    try:
        async with factory() as db:
            row = await _unresolved_in(db)
    except Exception:  # noqa: BLE001
        return None
    return _purchase_payload(row) if row else None


def _same_money(a: str | None, b: str | None) -> bool:
    try:
        return Decimal(str(a)) == Decimal(str(b))
    except (InvalidOperation, TypeError, ValueError):
        return False


async def purchase(*, resource_type: str, quantity: int, request_id: str, expected_monthly_cost: str,
                   actor: str, reason: str, guard=None) -> dict[str, Any]:
    """Buy a Vobiz bundle once, then raise the platform's own limit to match."""
    from server.db.models.concurrency_models import VobizCapacityPurchase
    from server.services.saas import vobiz_concurrency as vobiz

    request_id = (request_id or "").strip()
    if not request_id or len(request_id) > 64:
        raise _http(422, "request_id_required", "A request id is required.")
    if resource_type not in vobiz.RESOURCE_TYPES:
        raise _http(422, "invalid_resource", "Choose concurrent calls or CPS.")
    quantity = int(quantity)
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    async with factory() as db:
        existing = (await db.execute(select(VobizCapacityPurchase).where(
            VobizCapacityPurchase.request_id == request_id))).scalar_one_or_none()
    if existing is not None:
        return {"ok": existing.status == "succeeded", "duplicate": True, "purchase": _purchase_payload(existing)}
    blocked = await _unresolved_purchase()
    if blocked:
        raise _http(409, "purchase_unconfirmed",
                    "An earlier purchase got no answer from Vobiz. Check the Vobiz limits on this page "
                    "(and the Vobiz console if needed), then mark it as checked before buying again.",
                    purchase=blocked)
    price = await vobiz.preview_channel_price(quantity, resource_type=resource_type)
    if not price.get("available"):
        raise _http(409 if price.get("reason") == "quantity_not_allowed" else 503, price.get("reason") or "vobiz_unavailable",
                    price.get("message") or "Vobiz could not price this bundle right now. Nothing was bought.")
    if not _same_money(price["monthlyCost"], expected_monthly_cost):
        raise _http(409, "quote_changed", "The Vobiz price changed. Review the new price and confirm again.", price=price)
    now = _now()
    row = VobizCapacityPurchase(id=uuid.uuid4(), request_id=request_id, resource_type=resource_type, quantity=quantity,
                                quoted_monthly_cost=price["monthlyCost"], currency=price.get("currency") or None,
                                status="pending", actor=actor[:255], reason=reason[:500], created_at=now, updated_at=now)
    # Claim the purchase under a lock: of two admins (or two auto-buys on
    # different servers) clicking at once, only one gets to call Vobiz; the
    # other sees its pending row and is refused, so nothing is bought twice.
    from sqlalchemy.exc import IntegrityError

    try:
        async with factory() as db:
            if db.bind.dialect.name == "postgresql":
                from sqlalchemy import text

                await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _PURCHASE_LOCK_KEY})
            same = (await db.execute(select(VobizCapacityPurchase).where(
                VobizCapacityPurchase.request_id == request_id))).scalar_one_or_none()
            if same is not None:
                return {"ok": same.status == "succeeded", "duplicate": True, "purchase": _purchase_payload(same)}
            other = await _unresolved_in(db)
            if other is not None:
                raise _http(409, "purchase_unconfirmed",
                            "Another purchase is in progress or got no answer from Vobiz. Wait for it, or mark it "
                            "as checked in the history below, before buying again.", purchase=_purchase_payload(other))
            if guard is not None:
                stop = await guard(db)
                if stop:
                    raise _http(409, stop, "Not bought: no longer needed or over the auto-buy budget.")
            db.add(row)
            await db.commit()
    except IntegrityError:
        async with factory() as db:
            same = (await db.execute(select(VobizCapacityPurchase).where(
                VobizCapacityPurchase.request_id == request_id))).scalar_one()
        return {"ok": same.status == "succeeded", "duplicate": True, "purchase": _purchase_payload(same)}
    try:
        result = await vobiz.purchase_capacity(resource_type, quantity)
    except Exception as exc:  # noqa: BLE001 -- a crash here must still leave the row "unknown", not "pending"
        logger.warning("[CAPACITY] purchase call crashed: %s", type(exc).__name__)
        result = {"status": "unknown", "message": "The purchase request was interrupted. Check the Vobiz limits before trying again."}
    applied: dict[str, Any] | None = None
    row_id = row.id
    try:
        async with factory() as db:
            row = await db.get(VobizCapacityPurchase, row_id, with_for_update=True)
            row.status = result["status"]
            row.monthly_cost = (result.get("monthlyCost") or "")[:32] or None
            row.currency = (result.get("currency") or row.currency or "")[:8] or None
            row.vobiz_subscription_id = (result.get("subscriptionId") or "")[:128] or None
            row.next_billing_date = (result.get("nextBillingDate") or "")[:40] or None
            row.error = (result.get("message") or "")[:400] or None
            row.updated_at = _now()
            await db.commit()
            payload = _purchase_payload(row)
    except Exception as exc:  # noqa: BLE001 -- the row stays "pending", which keeps blocking buys until checked
        logger.error("[CAPACITY] purchase result not saved (%s): status=%s", type(exc).__name__, result["status"])
        payload = {**_purchase_payload(row), "status": result["status"],
                   "error": "Vobiz answered but the result could not be saved. Check Vobiz before buying again."}
    if result["status"] == "succeeded":
        applied = await _apply_safely(actor=actor, reason=f"Bought {quantity} {RESOURCE_LABEL[resource_type]} on Vobiz",
                                      bought={resource_type: quantity})
    return {"ok": result["status"] == "succeeded", "purchase": payload, "applied": applied}


async def _apply_safely(**kwargs: Any) -> dict[str, Any]:
    """After money was spent, a settings error must not turn the purchase into a 500."""
    try:
        return await apply_vobiz_limits(**kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[CAPACITY] limits not applied after purchase: %s", type(exc).__name__)
        return {"applied": False, "message": "Bought, but the platform limit could not be updated automatically. "
                                             "Use \"Use the Vobiz limits\" on this page."}


async def resolve_unknown(purchase_id: uuid.UUID, *, outcome: str, actor: str) -> dict[str, Any]:
    """The admin checked Vobiz: an unanswered purchase was bought (succeeded) or not (failed)."""
    from server.db.models.concurrency_models import VobizCapacityPurchase

    if outcome not in ("succeeded", "failed"):
        raise _http(422, "invalid_outcome", "Outcome must be succeeded or failed.")
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    async with factory() as db:
        row = await db.get(VobizCapacityPurchase, purchase_id, with_for_update=True)
        if row is None:
            raise _http(404, "not_found", "Purchase not found.")
        if row.status not in ("pending", "unknown"):
            raise _http(409, "already_resolved", "This purchase already has a result.")
        row.status = outcome
        row.error = f"{row.error or ''} Checked by {actor}: {outcome}.".strip()[:400]
        row.updated_at = _now()
        await db.commit()
        payload = _purchase_payload(row)
    applied = None
    if outcome == "succeeded":
        applied = await _apply_safely(actor=actor, reason=f"Confirmed Vobiz purchase of {row.quantity} {RESOURCE_LABEL.get(row.resource_type, row.resource_type)}",
                                      bought={row.resource_type: row.quantity})
    return {"ok": True, "purchase": payload, "applied": applied}


async def apply_vobiz_limits(*, actor: str, reason: str, bought: dict[str, int] | None = None) -> dict[str, Any]:
    """Set the platform's capacity and CPS to what Vobiz now allows.

    Reads the Vobiz limits; when Vobiz cannot be read right after a purchase, adds
    what was bought to the current value instead. A no-op (with a note) before
    channel pricing is configured, since there is no version to update yet.
    """
    from server.services.saas import concurrency_service as channels
    from server.services.saas import vobiz_concurrency as vobiz
    from server.config.env import get_settings

    config = await channels.load_pricing(force=True)
    if not config:
        return {"applied": False, "message": "Save the capacity settings once to start using the Vobiz limits."}
    bought = bought or {}
    limits = await vobiz.fetch_account_limits()
    live = await vobiz.fetch_platform_concurrency()
    capacity = (live.get("maxConcurrent") if live.get("available") else None) or limits.get("concurrentLimit")
    cps = limits.get("cpsLimit") if limits.get("available") else None
    current_cps = channels.platform_cps(config, get_settings())
    current_capacity = int(config["platformCapacity"])
    # Right after a purchase Vobiz may still report the old limit; never let that
    # hide what was just bought.
    if bought.get("concurrent_calls") and (not capacity or int(capacity) <= current_capacity):
        capacity = current_capacity + int(bought["concurrent_calls"])
    if bought.get("cps") and (not cps or int(cps) <= current_cps):
        cps = current_cps + int(bought["cps"])
    if not capacity:
        capacity = current_capacity
    if not cps:
        cps = current_cps
    if int(capacity) == int(config["platformCapacity"]) and int(cps) == current_cps:
        return {"applied": False, "platformCapacity": capacity, "platformCps": cps,
                "message": "Already matches Vobiz."}
    saved = await channels.save_pricing(
        actor=actor, reason=reason if len(reason) >= 8 else f"{reason} (Vobiz sync)",
        price_inr_per_channel=Decimal(config["priceInrPaisePerChannel"]) / 100,
        platform_capacity=int(capacity), included_channels=min(int(config["includedChannels"]), int(capacity)),
        grace_days=int(config["graceDays"]), max_channels_per_tenant=int(config["maxChannelsPerTenant"]),
        channels_per_number=int(config.get("channelsPerNumber", channels.DEFAULT_CHANNELS_PER_NUMBER)),
        platform_cps=int(cps), concurrency_block_size=int(config.get("concurrencyBlockSize") or channels.DEFAULT_CONCURRENCY_BLOCK),
    )
    return {"applied": True, "platformCapacity": saved["platformCapacity"], "platformCps": saved["platformCps"],
            "version": saved["version"]}

