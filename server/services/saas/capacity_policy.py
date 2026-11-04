"""How a tenant's number purchase gets its call channel: automatic or admin-approved.

Tenants only buy (and pay for) a number. Each number holds ``channelsPerNumber``
channels from the platform's Vobiz pool (``concurrency_service``). This module
decides, at purchase time, whether that channel is granted at once.

Modes (versioned in ``config_versions`` as ``capacity_policy`` / ``platform``):

* ``auto``: the number is approved at once when the pool has room. When it does
  not and **auto-buy** is on, the platform buys one Vobiz concurrency block,
  within the admin's monthly budget, and then approves. Otherwise the purchase
  waits in the approval queue (reason ``needs_capacity``) rather than being
  refused: the tenant has paid, the admin buys capacity and approves.
* ``manual``: every purchase waits for an admin. Approving holds the channel
  and starts activation; rejecting refunds the tenant in full.

A purchase waiting for approval has status ``awaiting_approval`` and a provision
job in ``held`` (the worker claims only ``queued``), and keeps its number
reservation, so nobody else can buy the number meanwhile.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException
from sqlalchemy import desc, func, select

from server.db.connection import get_session_factory

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "capacity_policy"
RESOURCE_ID = "platform"
AWAITING = "awaiting_approval"
HELD_JOB = "held"
#: The number reservation of a waiting purchase lasts this long; the queue shows the age.
APPROVAL_HOLD = timedelta(days=3)
DEFAULT_POLICY = {"approvalMode": "auto", "autoBuy": False, "autoBuyMonthlyBudgetInr": "0"}
_auto_buy_lock = asyncio.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _http(status: int, code: str, message: str, **extra: Any) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": {"code": code, "message": message, **extra}})


def _money(value: Any) -> Decimal:
    try:
        out = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(0)
    return out if out.is_finite() else Decimal(0)


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

async def load_policy() -> dict[str, Any]:
    factory = get_session_factory()
    if factory is None:
        return {**DEFAULT_POLICY, "version": None}
    from server.db.models.entities import ConfigVersion

    try:
        async with factory() as db:
            row = (await db.execute(select(ConfigVersion).where(
                ConfigVersion.resource_type == RESOURCE_TYPE, ConfigVersion.resource_id == RESOURCE_ID,
            ).order_by(desc(ConfigVersion.version)).limit(1))).scalar_one_or_none()
    except Exception as exc:  # noqa: BLE001
        logger.info("[CAPACITY] policy read failed: %s", type(exc).__name__)
        return {**DEFAULT_POLICY, "version": None}
    payload = (row.payload or {}) if row else {}
    return {
        "approvalMode": payload.get("approvalMode") if payload.get("approvalMode") in ("auto", "manual") else "auto",
        "autoBuy": bool(payload.get("autoBuy")),
        "autoBuyMonthlyBudgetInr": str(_money(payload.get("autoBuyMonthlyBudgetInr") or 0)),
        "version": row.version if row else None,
        "updatedAt": row.created_at.isoformat() if row and row.created_at else None,
        "actor": payload.get("actor"),
        "reason": payload.get("reason"),
    }


async def save_policy(*, approval_mode: str, auto_buy: bool, auto_buy_monthly_budget_inr: Any,
                      actor: str, reason: str) -> dict[str, Any]:
    if approval_mode not in ("auto", "manual"):
        raise ValueError("Approval mode must be auto or manual.")
    budget = _money(auto_buy_monthly_budget_inr)
    if budget < 0 or budget > Decimal("10000000"):
        raise ValueError("Auto-buy budget must be between 0 and 1,00,00,000.")
    if auto_buy and budget <= 0:
        raise ValueError("Set a monthly auto-buy budget above 0, or turn auto-buy off.")
    if len((reason or "").strip()) < 8:
        raise ValueError("A reason of at least 8 characters is required.")
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    from server.db.models.entities import ConfigVersion

    async with factory() as db:
        last = (await db.execute(select(func.max(ConfigVersion.version)).where(
            ConfigVersion.resource_type == RESOURCE_TYPE, ConfigVersion.resource_id == RESOURCE_ID))).scalar_one_or_none()
        db.add(ConfigVersion(id=uuid.uuid4(), resource_type=RESOURCE_TYPE, resource_id=RESOURCE_ID,
                             version=int(last or 0) + 1, created_at=_now(),
                             payload={"approvalMode": approval_mode, "autoBuy": bool(auto_buy),
                                      "autoBuyMonthlyBudgetInr": str(budget), "actor": actor,
                                      "reason": reason.strip()}))
        await db.commit()
    return await load_policy()


async def auto_buy_commitment(db=None) -> Decimal:
    """Monthly Vobiz cost of every bundle auto-buy has bought (they renew every 30 days).

    The budget caps this total, so auto-buy can never grow the recurring bill past
    it; counting only the last 30 days would let it add a budget's worth each month.
    """
    from server.db.models.concurrency_models import VobizCapacityPurchase

    query = select(VobizCapacityPurchase.monthly_cost, VobizCapacityPurchase.quoted_monthly_cost).where(
        VobizCapacityPurchase.actor == "auto-buy",
        VobizCapacityPurchase.status.in_(("succeeded", "pending", "unknown")))
    if db is not None:
        rows = (await db.execute(query)).all()
    else:
        factory = get_session_factory()
        if factory is None:
            return Decimal(0)
        async with factory() as session:
            rows = (await session.execute(query)).all()
    return sum((_money(a or b) for a, b in rows), Decimal(0))


# ---------------------------------------------------------------------------
# Decision at purchase time
# ---------------------------------------------------------------------------

async def _room_for(need: int) -> tuple[bool, int, int]:
    """(fits, held, capacity) for `need` more held channels."""
    from server.services.saas import concurrency_service as channels

    config = await channels.load_pricing(force=True)
    if not config:
        return True, 0, 0
    factory = get_session_factory()
    async with factory() as db:
        held = await channels.held_total(db, config)
    capacity = int(config["platformCapacity"])
    return held + need <= capacity, held, capacity


async def channels_needed(adding: int = 1) -> int:
    from server.services.saas import concurrency_service as channels

    config = await channels.load_pricing()
    if not config:
        return 0
    return int(adding) * int(config.get("channelsPerNumber", channels.DEFAULT_CHANNELS_PER_NUMBER))


async def _try_auto_buy(tenant_id: uuid.UUID, short_by: int, need: int, policy: dict[str, Any]) -> dict[str, Any]:
    """Buy enough Vobiz concurrency blocks for `short_by` channels, within budget. Never raises."""
    from server.services.saas import capacity_incidents, capacity_planner
    from server.services.saas import concurrency_service as channels
    from server.services.saas import vobiz_concurrency as vobiz

    config = await channels.load_pricing(force=True) or {}
    block = int(config.get("concurrencyBlockSize") or channels.DEFAULT_CONCURRENCY_BLOCK)
    quantity = capacity_planner.round_up_to_block(short_by, block)
    async with _auto_buy_lock:
        # Another purchase may have just bought enough while this one waited.
        if (await _room_for(need))[0]:
            return {"bought": True, "reason": "bought_by_another_purchase", "quantity": 0}
        if await capacity_planner._unresolved_purchase():
            return {"bought": False, "reason": "purchase_unconfirmed"}
        try:
            price = await vobiz.preview_channel_price(quantity, resource_type="concurrent_calls")
        except ValueError:  # quantity outside what Vobiz accepts in one purchase
            return {"bought": False, "reason": "quantity_not_allowed"}
        if not price.get("available"):
            return {"bought": False, "reason": price.get("reason") or "vobiz_unavailable"}
        cost = _money(price["monthlyCost"])
        budget = _money(policy.get("autoBuyMonthlyBudgetInr"))
        spent = await auto_buy_commitment()
        if spent + cost > budget:
            await capacity_incidents.record("number_blocked", tenant_id,
                                            detail=f"auto-buy over budget: {spent} + {cost} > {budget}")
            return {"bought": False, "reason": "over_budget", "cost": str(cost), "spent": str(spent)}
        balance = await vobiz.fetch_balance()
        if balance.get("available") and _money(balance.get("balance")) < cost:
            return {"bought": False, "reason": "vobiz_balance_low"}
        async def still_needed(db) -> str | None:
            """Re-checked under the cross-server purchase lock: another server may
            have just bought, or spent the budget, while this one was pricing."""
            config_now = await channels.load_pricing(force=True)
            if config_now and await channels.held_total(db, config_now) + need <= int(config_now["platformCapacity"]):
                return "bought_by_another_purchase"
            if await auto_buy_commitment(db) + cost > budget:
                return "over_budget"
            return None

        try:
            result = await capacity_planner.purchase(
                resource_type="concurrent_calls", quantity=quantity, request_id=f"auto-{uuid.uuid4().hex[:24]}",
                expected_monthly_cost=price["monthlyCost"], actor="auto-buy",
                reason=f"Automatic: a number purchase needed {short_by} more channel(s)", guard=still_needed)
        except HTTPException as exc:
            code = (exc.detail or {}).get("error", {}).get("code") if isinstance(exc.detail, dict) else None
            if code == "bought_by_another_purchase":
                return {"bought": True, "reason": code, "quantity": 0}
            logger.warning("[CAPACITY] auto-buy refused: %s", code)
            return {"bought": False, "reason": code or "purchase_refused"}
    if not result.get("ok"):
        return {"bought": False, "reason": result["purchase"]["status"]}
    return {"bought": True, "quantity": quantity, "monthlyCost": price["monthlyCost"]}


async def prepare_number_purchase(tenant_id: uuid.UUID) -> dict[str, Any]:
    """Step 1, outside any lock or transaction: buy capacity ahead when auto-buy applies.

    Never decides. Vobiz calls take seconds, so they must not run while the
    platform admission lock is held (every call admission waits on it).
    """
    policy = await load_policy()
    if policy["approvalMode"] == "manual":
        return {"policy": policy, "note": "manual"}
    need = await channels_needed(1)
    if need <= 0:
        return {"policy": policy, "note": "no_channel_needed"}
    fits, held, capacity = await _room_for(need)
    if fits:
        return {"policy": policy, "note": "capacity_available"}
    if not policy["autoBuy"]:
        return {"policy": policy, "note": "needs_capacity"}
    bought = await _try_auto_buy(tenant_id, held + need - capacity, need, policy)
    note = "auto_bought" if bought.get("bought") else f"needs_capacity:{bought.get('reason')}"
    return {"policy": policy, "note": note, "autoBuy": bought}


async def decide_in_session(session, tenant_id: uuid.UUID, prepared: dict[str, Any]) -> dict[str, Any]:
    """Step 2, inside the purchase's own transaction: approve only if a channel is free now.

    Takes the platform lock, so two purchases cannot both be approved into the
    last free channel: the second waits for the first to commit, then sees its
    paid purchase holding that channel. No network calls here. When it returns
    an ``incident``, the caller records it after its transaction ends.
    """
    from server.services.saas import concurrency_service as channels

    policy = prepared["policy"]
    if policy["approvalMode"] == "manual":
        return {"approved": False, "reason": "manual", "policy": "manual"}
    config = await channels.load_pricing()
    need = int(config.get("channelsPerNumber", channels.DEFAULT_CHANNELS_PER_NUMBER)) if config else 0
    if not config or need <= 0:
        return {"approved": True, "reason": "no_channel_needed", "policy": "auto"}
    await channels.lock_platform(session)
    held = await channels.held_total(session, config)
    capacity = int(config["platformCapacity"])
    if held + need <= capacity:
        reason = prepared["note"] if prepared["note"] in ("auto_bought", "capacity_available") else "capacity_available"
        return {"approved": True, "reason": reason, "policy": "auto"}
    reason = prepared["note"] if prepared["note"].startswith("needs_capacity") else "needs_capacity"
    return {"approved": False, "reason": reason, "policy": "auto",
            "incident": f"queued for approval: held {held} + {need} > capacity {capacity} ({reason})"}


async def record_decision(tenant_id: uuid.UUID, decision: dict[str, Any]) -> None:
    if decision.get("incident"):
        from server.services.saas import capacity_incidents

        await capacity_incidents.record("number_blocked", tenant_id, detail=decision["incident"])


async def decide_number_purchase(tenant_id: uuid.UUID) -> dict[str, Any]:
    """Both steps in their own transaction (used where no purchase transaction exists).

    ``approved`` False means the purchase goes ahead (tenant pays) but waits for
    an admin; it is never a refusal, so a tenant is never told to come back later.
    """
    prepared = await prepare_number_purchase(tenant_id)
    factory = get_session_factory()
    async with factory() as session:
        decision = await decide_in_session(session, tenant_id, prepared)
    await record_decision(tenant_id, decision)
    return {k: v for k, v in decision.items() if k != "incident"}


# ---------------------------------------------------------------------------
# Approval queue
# ---------------------------------------------------------------------------

async def queue() -> list[dict[str, Any]]:
    """Purchases waiting for an admin, oldest first."""
    factory = get_session_factory()
    if factory is None:
        return []
    from server.db.models.entities import Tenant
    from server.db.models.saas_models import NumberPurchase

    async with factory() as db:
        rows = (await db.execute(select(NumberPurchase, Tenant.name).outerjoin(
            Tenant, Tenant.tenant_id == NumberPurchase.tenant_id).where(NumberPurchase.status == AWAITING)
            .order_by(NumberPurchase.created_at).limit(200))).all()
    return [{
        "purchaseId": str(p.id), "tenantId": str(p.tenant_id), "tenantName": name or "Deleted workspace", "e164": p.e164,
        "country": p.country_code, "createdAt": p.created_at.isoformat() if p.created_at else None,
    } for p, name in rows]


async def approve(purchase_id: uuid.UUID, *, actor: str) -> dict[str, Any]:
    """Hold the number's channel and start activation. Refused while the pool has no room."""
    from server.db.models.saas_models import NumberPurchase, NumberReservation, ProvisionJob
    from server.services.saas import capacity_planner
    from server.services.saas import concurrency_service as channels

    need = await channels_needed(1)
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    async with factory() as db:
        await channels.lock_platform(db)
        purchase = await db.get(NumberPurchase, purchase_id, with_for_update=True)
        if purchase is None:
            raise _http(404, "not_found", "Purchase not found.")
        if purchase.status != AWAITING:
            raise _http(409, "not_awaiting", f"This purchase is {purchase.status}, not waiting for approval.")
        config = await channels.load_pricing(force=True)
        if config and need:
            held = await channels.held_total(db, config)
            capacity = int(config["platformCapacity"])
            if held + need > capacity:
                block = int(config.get("concurrencyBlockSize") or channels.DEFAULT_CONCURRENCY_BLOCK)
                buy = capacity_planner.round_up_to_block(held + need - capacity, block)
                raise _http(409, "needs_capacity",
                            f"No free channel for this number: {held} of {capacity} are already held. "
                            f"Buy {buy} concurrent calls first (Buy capacity, above), then approve.",
                            buy=buy)
        purchase.status = "paid"
        purchase.updated_at = _now()
        job = (await db.execute(select(ProvisionJob).where(ProvisionJob.purchase_id == purchase_id)
                                .with_for_update())).scalar_one_or_none()
        if job is None:
            db.add(ProvisionJob(purchase_id=purchase_id, status="queued", attempts=0, created_at=_now(), updated_at=_now()))
        else:
            job.status, job.attempts, job.updated_at = "queued", 0, _now()
        reservation = (await db.execute(select(NumberReservation).where(
            NumberReservation.purchase_id == purchase_id).with_for_update())).scalar_one_or_none()
        if reservation is not None:
            reservation.expires_at = _now() + timedelta(minutes=30)
        tenant_id, e164 = purchase.tenant_id, purchase.e164
        await db.commit()
    await _activity(tenant_id, "number.purchase.approved", actor, {"purchaseId": str(purchase_id), "e164": e164})
    return {"ok": True, "purchaseId": str(purchase_id), "status": "paid"}


async def reject(purchase_id: uuid.UUID, *, actor: str, reason: str) -> dict[str, Any]:
    """Refund the tenant in full and release the number."""
    from server.db.models.saas_models import NumberPurchase
    from server.services.saas.number_purchase_admin import PurchaseAdminError, refund_purchase

    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    async with factory() as db:
        purchase = await db.get(NumberPurchase, purchase_id)
        if purchase is None:
            raise _http(404, "not_found", "Purchase not found.")
        if purchase.status != AWAITING:
            raise _http(409, "not_awaiting", f"This purchase is {purchase.status}, not waiting for approval.")
        tenant_id, e164 = purchase.tenant_id, purchase.e164
    try:
        result = await refund_purchase(purchase_id)
    except PurchaseAdminError as exc:
        raise _http(exc.status_code, exc.code, exc.message) from exc
    await _activity(tenant_id, "number.purchase.rejected", actor,
                    {"purchaseId": str(purchase_id), "e164": e164, "reason": reason, "refunded": result.get("refunded")})
    return {"ok": True, "purchaseId": str(purchase_id), "status": "refunded", "refunded": result.get("refunded")}


async def _activity(tenant_id: uuid.UUID, action: str, actor: str, payload: dict[str, Any]) -> None:
    try:
        from server.services.saas.activity_log import record_event

        await record_event(action=action, resource_type="number_purchase", resource_id=payload.get("purchaseId", ""),
                           actor=actor, tenant_id=tenant_id, payload=payload, source="capacity")
    except Exception:  # noqa: BLE001
        pass


async def expire_stale_approvals(*, now: datetime | None = None, limit: int = 20) -> int:
    """Refund purchases nobody approved within APPROVAL_HOLD, as the tenant was promised."""
    factory = get_session_factory()
    if factory is None:
        return 0
    from server.db.models.saas_models import NumberPurchase

    cutoff = (now or _now()) - APPROVAL_HOLD
    async with factory() as db:
        ids = (await db.execute(select(NumberPurchase.id).where(
            NumberPurchase.status == AWAITING, NumberPurchase.created_at < cutoff,
        ).order_by(NumberPurchase.created_at).limit(limit))).scalars().all()
    done = 0
    for purchase_id in ids:
        try:
            await reject(purchase_id, actor="system",
                         reason=f"Not approved within {APPROVAL_HOLD.days} days; refunded automatically")
            done += 1
        except Exception as exc:  # noqa: BLE001 -- one purchase never blocks the rest
            logger.warning("[CAPACITY] stale approval not refunded %s: %s", purchase_id, type(exc).__name__)
    return done
