"""Concurrent call channels: pricing, tenant caps, charging, renewal and analytics.

Model
-----
* A channel is one simultaneous PSTN call (inbound or outbound).
* Every active phone number a tenant owns brings ``channelsPerNumber`` (default
  1) **held** channels: Vobiz sells no capacity with a DID, so the platform sets
  one aside from its own pool for each number it sells.
* Paid channels are held too. Held channels are always available to their
  tenant; nobody else's calls can use them.
* Every tenant also gets ``includedChannels`` free (per-tenant override:
  ``tenant.limits["included_channels"]``). These are best effort: they use only
  capacity nobody holds.
* Paid channels are a **30-day** recurring subscription, matching how Vobiz
  bills the platform's own concurrency capacity (it renews every 30 days).
* Price per channel per 30 days is set by the platform admin and versioned in
  ``config_versions`` (``concurrency_pricing`` / ``platform``). A price of 0
  means nothing is charged or debited.

Charging rules
--------------
* First purchase (or after a lapse): starts a new 30-day period now and charges
  ``price x channels`` in full.
* Increase mid-period: charges the added channels prorated to the end of the
  current period (``price x added x remaining / 30 days``, rounded half-up to
  the minor unit). The renewal date does not move.
* Decrease: never refunded; takes effect at the next renewal. Cancelling the
  pending decrease before then is free.
* Renewal at period end charges ``current price x channels``. Price changes made
  by the admin therefore apply from each tenant's next renewal or purchase, never
  to a period already paid.
* Insufficient balance at renewal: channels stay usable for a grace period
  (``graceDays``, default 3) with a notice; renewal is retried. When grace ends
  unpaid, paid channels drop to 0 (the tenant keeps its included channels).
* Every charge is one wallet transaction with a deterministic ``reference_id``
  (purchase: the client's request id; renewal: the period end), so retries never
  debit twice. Charges are debited from prepaid wallet credit, on which GST was
  already invoiced at top-up, so no second GST line is raised here.

Enforcement
-----------
``call_admission.reserve`` (outbound and inbound Vobiz) and
``telephony_orchestrator.assert_concurrent_limit`` call :func:`channel_cap`.
When pricing has never been configured, the legacy caps apply unchanged
(``tenant.limits.max_concurrent_pstn`` within ``SAAS_MAX_CONCURRENT_PSTN``).
Once configured, a tenant may use ``included + number channels + paid``
channels, the sum of live calls across all tenants never exceeds
``platformCapacity`` (the capacity bought from Vobiz), and a call beyond a
tenant's held channels is admitted only if it leaves every other tenant's
unused held channels free (:func:`admission_decision`). Held channels are never
sold past ``platformCapacity``: a number or paid-channel purchase that would is
refused before any charge. Campaign dials refused for capacity are re-queued by
the campaign runner, not dropped.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import desc, func, select

from server.db.connection import get_session_factory

logger = logging.getLogger(__name__)

PERIOD_DAYS = 30
PERIOD = timedelta(days=PERIOD_DAYS)
RESOURCE_TYPE = "concurrency_pricing"
RESOURCE_ID = "platform"
CACHE_TTL_S = 15.0
RENEWAL_RETRY_INTERVAL = timedelta(hours=6)
DEFAULT_GRACE_DAYS = 3
DEFAULT_CHANNELS_PER_NUMBER = 1
#: Vobiz sells concurrent calls in blocks (10 on the standard tier).
DEFAULT_CONCURRENCY_BLOCK = 10
#: Phone number statuses that hold channels (suspended / released numbers do not).
NUMBER_HOLDING_STATUSES = ("active", "pending")
#: Approved number purchases not yet active (a retry can still activate needs_attention).
IN_FLIGHT_HOLDING_STATUSES = ("paid", "provisioning", "needs_attention")
#: Advisory lock key that serializes platform-wide admission (PostgreSQL only).
_PLATFORM_LOCK_KEY = 4_904_903_001

_cache: dict[str, Any] | None = None
_cache_loaded_at: float = 0.0
_cache_set_explicitly = False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _half_up(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _http(status: int, code: str, message: str, **extra: Any) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": {"code": code, "message": message, **extra}})


# ---------------------------------------------------------------------------
# Pricing configuration
# ---------------------------------------------------------------------------

def _config_from_payload(version: int, payload: dict[str, Any], created_at: datetime | None) -> dict[str, Any]:
    return {
        "configured": True,
        "version": int(version),
        "priceInrPaisePerChannel": int(payload.get("priceInrPaisePerChannel") or 0),
        "priceUsdMicrosPerChannel": int(payload.get("priceUsdMicrosPerChannel") or 0),
        "fxRateInr": float(payload.get("fxRateInr") or 0) or None,
        "platformCapacity": max(0, int(payload.get("platformCapacity") or 0)),
        "includedChannels": max(0, int(payload.get("includedChannels") or 0)),
        "graceDays": max(0, int(payload.get("graceDays") if payload.get("graceDays") is not None else DEFAULT_GRACE_DAYS)),
        "maxChannelsPerTenant": max(0, int(payload.get("maxChannelsPerTenant") or 0)),
        "channelsPerNumber": max(0, int(payload.get("channelsPerNumber") if payload.get("channelsPerNumber") is not None else DEFAULT_CHANNELS_PER_NUMBER)),
        "platformCps": max(0, int(payload.get("platformCps") or 0)),
        "concurrencyBlockSize": max(1, int(payload.get("concurrencyBlockSize") or DEFAULT_CONCURRENCY_BLOCK)),
        "periodDays": PERIOD_DAYS,
        "updatedAt": _aware(created_at).isoformat() if created_at else None,
        "actor": payload.get("actor"),
        "reason": payload.get("reason"),
    }


def set_cached_pricing(config: dict[str, Any] | None) -> None:
    """Pin the pricing config in this process (tests, and right after a save)."""
    global _cache, _cache_loaded_at, _cache_set_explicitly
    _cache = dict(config) if config else None
    _cache_loaded_at = time.monotonic()
    _cache_set_explicitly = config is not None


def clear_pricing_cache() -> None:
    global _cache, _cache_loaded_at, _cache_set_explicitly
    _cache, _cache_loaded_at, _cache_set_explicitly = None, 0.0, False


async def load_pricing(*, force: bool = False) -> dict[str, Any] | None:
    """Latest channel pricing, or None when the admin has never configured it."""
    global _cache, _cache_loaded_at
    if _cache_set_explicitly:
        return dict(_cache) if _cache else None
    if not force and _cache_loaded_at and time.monotonic() - _cache_loaded_at < CACHE_TTL_S:
        return dict(_cache) if _cache else None
    factory = get_session_factory()
    if factory is None:
        return dict(_cache) if _cache else None
    try:
        from server.db.models.entities import ConfigVersion

        async with factory() as db:
            row = (await db.execute(
                select(ConfigVersion).where(
                    ConfigVersion.resource_type == RESOURCE_TYPE, ConfigVersion.resource_id == RESOURCE_ID,
                ).order_by(desc(ConfigVersion.version)).limit(1)
            )).scalar_one_or_none()
    except Exception as exc:  # noqa: BLE001 -- keep the last known value
        logger.warning("[CHANNELS] pricing read failed: %s", type(exc).__name__)
        return dict(_cache) if _cache else None
    _cache = _config_from_payload(row.version, row.payload or {}, row.created_at) if row else None
    _cache_loaded_at = time.monotonic()
    return dict(_cache) if _cache else None


async def save_pricing(
    *,
    actor: str,
    reason: str,
    price_inr_per_channel: Decimal | float | str,
    platform_capacity: int,
    included_channels: int,
    grace_days: int = DEFAULT_GRACE_DAYS,
    max_channels_per_tenant: int = 0,
    channels_per_number: int | None = None,
    platform_cps: int | None = None,
    concurrency_block_size: int | None = None,
) -> dict[str, Any]:
    """Publish a new pricing version. Applies to purchases and renewals from now on.

    Fields left as None keep their previous value (or the default)."""
    clean_reason = (reason or "").strip()
    if len(clean_reason) < 8:
        raise ValueError("A reason of at least 8 characters is required to change channel pricing.")
    try:
        price = Decimal(str(price_inr_per_channel))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Channel price must be a number.") from exc
    if not price.is_finite() or price < 0:
        raise ValueError("Channel price must be zero or more.")
    paise = price * 100
    if paise != paise.to_integral_value():
        raise ValueError("Channel price supports at most 2 decimal places.")
    platform_capacity = int(platform_capacity)
    included_channels = int(included_channels)
    grace_days = int(grace_days)
    max_channels_per_tenant = int(max_channels_per_tenant or 0)
    if platform_capacity < 1 or platform_capacity > 100_000:
        raise ValueError("Platform capacity must be between 1 and 100000 channels.")
    if included_channels < 0 or included_channels > platform_capacity:
        raise ValueError("Included channels must be between 0 and the platform capacity.")
    if grace_days < 0 or grace_days > 30:
        raise ValueError("Grace period must be between 0 and 30 days.")
    if max_channels_per_tenant < 0:
        raise ValueError("Per-tenant maximum must be zero (no limit) or more.")
    previous = await load_pricing(force=True) or {}
    channels_per_number = int(channels_per_number if channels_per_number is not None
                              else previous.get("channelsPerNumber", DEFAULT_CHANNELS_PER_NUMBER))
    platform_cps = int(platform_cps if platform_cps is not None else previous.get("platformCps", 0))
    concurrency_block_size = int(concurrency_block_size if concurrency_block_size is not None
                                 else previous.get("concurrencyBlockSize", DEFAULT_CONCURRENCY_BLOCK))
    if channels_per_number < 0 or channels_per_number > 100:
        raise ValueError("Channels per number must be between 0 and 100.")
    if platform_cps < 0 or platform_cps > 1000:
        raise ValueError("Platform CPS must be between 0 (use the server default) and 1000.")
    if concurrency_block_size < 1 or concurrency_block_size > 10000:
        raise ValueError("Vobiz block size must be between 1 and 10000.")

    from server.services.saas.billing_rates import load_current_rates

    fx = Decimal(str((await load_current_rates()).get("fx_rate_inr") or 0))
    if fx <= 0:
        raise ValueError("A positive INR per USD rate is required to price channels.")
    paise_int = int(paise)
    usd_micros = _half_up(Decimal(paise_int) / 100 / fx * 1_000_000) if paise_int else 0

    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    from server.db.models.concurrency_models import TenantChannelSubscription
    from server.db.models.entities import ConfigVersion

    async with factory() as db:
        if db.bind.dialect.name == "postgresql":
            from sqlalchemy import text

            await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _PLATFORM_LOCK_KEY})
        sold = int((await db.execute(
            select(func.coalesce(func.sum(TenantChannelSubscription.paid_channels), 0)).where(
                TenantChannelSubscription.status.in_(("active", "grace")))
        )).scalar_one() or 0)
        if sold > platform_capacity:
            raise ValueError(
                f"{sold} paid channels are already sold; platform capacity cannot be set below that. "
                "Buy more Vobiz capacity or wait for tenants to downgrade."
            )
        last = (await db.execute(
            select(func.max(ConfigVersion.version)).where(
                ConfigVersion.resource_type == RESOURCE_TYPE, ConfigVersion.resource_id == RESOURCE_ID)
        )).scalar_one_or_none()
        version = int(last or 0) + 1
        payload = {
            "priceInrPaisePerChannel": paise_int,
            "priceUsdMicrosPerChannel": usd_micros,
            "fxRateInr": float(fx),
            "platformCapacity": platform_capacity,
            "includedChannels": included_channels,
            "graceDays": grace_days,
            "maxChannelsPerTenant": max_channels_per_tenant,
            "channelsPerNumber": channels_per_number,
            "platformCps": platform_cps,
            "concurrencyBlockSize": concurrency_block_size,
            "actor": actor,
            "reason": clean_reason,
        }
        now = _utcnow()
        db.add(ConfigVersion(id=uuid.uuid4(), resource_type=RESOURCE_TYPE, resource_id=RESOURCE_ID,
                             version=version, payload=payload, created_at=now))
        await db.commit()
    config = _config_from_payload(version, payload, now)
    set_cached_pricing(config)
    global _cache_set_explicitly
    _cache_set_explicitly = False  # other processes' saves are picked up after the TTL
    return config


def public_pricing(config: dict[str, Any] | None) -> dict[str, Any]:
    if not config:
        return {"configured": False, "periodDays": PERIOD_DAYS, "priceInrPerChannel": 0.0, "priceUsdPerChannel": 0.0,
                "free": True}
    return {
        "configured": True,
        "version": config["version"],
        "priceInrPerChannel": round(config["priceInrPaisePerChannel"] / 100.0, 2),
        "priceUsdPerChannel": round(config["priceUsdMicrosPerChannel"] / 1_000_000.0, 6),
        "free": config["priceInrPaisePerChannel"] <= 0,
        "platformCapacity": config["platformCapacity"],
        "includedChannels": config["includedChannels"],
        "graceDays": config["graceDays"],
        "maxChannelsPerTenant": config["maxChannelsPerTenant"],
        "channelsPerNumber": config.get("channelsPerNumber", DEFAULT_CHANNELS_PER_NUMBER),
        "platformCps": config.get("platformCps", 0),
        "concurrencyBlockSize": config.get("concurrencyBlockSize", DEFAULT_CONCURRENCY_BLOCK),
        "periodDays": PERIOD_DAYS,
        "updatedAt": config.get("updatedAt"),
        "reason": config.get("reason"),
    }


# ---------------------------------------------------------------------------
# Caps (admission)
# ---------------------------------------------------------------------------

def legacy_caps(settings: Any, limits: dict | None) -> tuple[int, int]:
    """Caps used before the admin configures channel pricing (unchanged behaviour)."""
    platform_cap = max(1, min(20, int(getattr(settings, "saas_max_concurrent_pstn", 20) or 20)))
    tenant_cap = max(1, min(platform_cap, int((limits or {}).get("max_concurrent_pstn") or platform_cap)))
    return tenant_cap, platform_cap


def _paid_in_force(sub: Any, now: datetime | None = None) -> int:
    if sub is None or sub.status not in ("active", "grace"):
        return 0
    now = now or _utcnow()
    if sub.status == "grace" and sub.grace_until is not None and _aware(sub.grace_until) <= now:
        return 0  # Grace has ended; the renewal worker will record the lapse.
    return max(0, int(sub.paid_channels or 0))


async def channel_cap(db, tenant: Any, *, settings: Any) -> dict[str, Any]:
    """The tenant's simultaneous-call cap and the platform capacity it sits within."""
    config = await load_pricing()
    limits = getattr(tenant, "limits", None) or {}
    if not config:
        tenant_cap, platform_cap = legacy_caps(settings, limits)
        return {"legacy": True, "cap": tenant_cap, "included": tenant_cap, "paid": 0,
                "platformCapacity": platform_cap, "pricingVersion": None}
    included = limits.get("included_channels")
    included = max(0, int(included if included is not None else config["includedChannels"]))
    from server.db.models.concurrency_models import TenantChannelSubscription

    sub = await db.get(TenantChannelSubscription, tenant.tenant_id)
    paid = _paid_in_force(sub)
    numbers = await number_count(db, tenant.tenant_id)
    number_channels = numbers * int(config.get("channelsPerNumber", DEFAULT_CHANNELS_PER_NUMBER))
    return {"legacy": False, "cap": min(config["platformCapacity"], included + number_channels + paid),
            "included": included, "paid": paid, "numbers": numbers, "numberChannels": number_channels,
            "held": number_channels + paid,
            "platformCapacity": config["platformCapacity"], "pricingVersion": config["version"]}


async def number_count(db, tenant_id: uuid.UUID) -> int:
    """Phone numbers the tenant holds channels for (active or still provisioning)."""
    from server.db.models.phase5_models import PhoneNumber

    return int((await db.execute(select(func.count()).select_from(PhoneNumber).where(
        PhoneNumber.tenant_id == tenant_id, PhoneNumber.released_at.is_(None),
        PhoneNumber.status.in_(NUMBER_HOLDING_STATUSES)))).scalar_one() or 0)


async def held_by_tenant(db, config: dict[str, Any]) -> dict[uuid.UUID, dict[str, int]]:
    """Held channels per tenant: ``{tenant: {numbers, numberChannels, paid, held}}``."""
    from server.db.models.concurrency_models import TenantChannelSubscription
    from server.db.models.phase5_models import PhoneNumber

    per_number = int(config.get("channelsPerNumber", DEFAULT_CHANNELS_PER_NUMBER))
    out: dict[uuid.UUID, dict[str, int]] = {}
    rows = (await db.execute(select(PhoneNumber.tenant_id, func.count()).where(
        PhoneNumber.released_at.is_(None), PhoneNumber.status.in_(NUMBER_HOLDING_STATUSES),
    ).group_by(PhoneNumber.tenant_id))).all()
    for tenant_id, n in rows:
        out[tenant_id] = {"numbers": int(n), "numberChannels": int(n) * per_number, "paid": 0}
    # Approved purchases still being activated hold their channel already, so two
    # tenants cannot both be approved into the last free channel.
    from server.db.models.saas_models import NumberPurchase

    activating = (await db.execute(select(NumberPurchase.tenant_id, func.count()).where(
        NumberPurchase.status.in_(IN_FLIGHT_HOLDING_STATUSES), NumberPurchase.phone_number_id.is_(None),
    ).group_by(NumberPurchase.tenant_id))).all()
    for tenant_id, n in activating:
        row = out.setdefault(tenant_id, {"numbers": 0, "numberChannels": 0, "paid": 0})
        row["numbers"] += int(n)
        row["numberChannels"] += int(n) * per_number
    now = _utcnow()
    subs = (await db.execute(select(TenantChannelSubscription).where(
        TenantChannelSubscription.status.in_(("active", "grace"))))).scalars().all()
    for sub in subs:
        paid = _paid_in_force(sub, now)
        if paid:
            out.setdefault(sub.tenant_id, {"numbers": 0, "numberChannels": 0, "paid": 0})["paid"] = paid
    for row in out.values():
        row["held"] = row["numberChannels"] + row["paid"]
    return out


async def active_by_tenant(db) -> dict[uuid.UUID, int]:
    """Live PSTN calls per tenant (reservations plus untracked live calls)."""
    from server.db.models.entities import Call
    from server.db.models.phase5_models import PstnDialRequest
    from server.services.saas.call_admission import ACTIVE

    out: dict[uuid.UUID, int] = {}
    for tenant_id, n in (await db.execute(select(PstnDialRequest.tenant_id, func.count()).where(
            PstnDialRequest.status.in_(ACTIVE)).group_by(PstnDialRequest.tenant_id))).all():
        out[tenant_id] = out.get(tenant_id, 0) + int(n)
    reservations = select(PstnDialRequest.call_id).where(
        PstnDialRequest.status.in_(ACTIVE), PstnDialRequest.call_id.is_not(None))
    for tenant_id, n in (await db.execute(select(Call.tenant_id, func.count()).where(
            Call.channel == "pstn", Call.ended_at.is_(None), Call.call_id.not_in(reservations),
            Call.tenant_id.is_not(None)).group_by(Call.tenant_id))).all():
        out[tenant_id] = out.get(tenant_id, 0) + int(n)
    return out


def admission_decision(
    tenant_id: uuid.UUID,
    *,
    capacity: int,
    active: dict[uuid.UUID, int],
    held: dict[uuid.UUID, dict[str, int]],
) -> str | None:
    """None when one more call for `tenant_id` fits the shared pool; else the incident kind.

    * The pool is full: ``platform_full``.
    * The call is within the tenant's held channels: admitted (that capacity is
      theirs; it was never sold to anyone else).
    * Otherwise it is best effort, and admitted only if every other tenant's
      unused held channels stay free: else ``reserved_full``.
    """
    live = sum(active.values())
    if live >= capacity:
        return "platform_full"
    own_active = active.get(tenant_id, 0)
    if own_active < held.get(tenant_id, {}).get("held", 0):
        return None
    unused_others = sum(max(0, row["held"] - active.get(other, 0)) for other, row in held.items() if other != tenant_id)
    if live + unused_others >= capacity:
        return "reserved_full"
    return None


async def platform_admission(db, tenant_id: uuid.UUID, config: dict[str, Any]) -> str | None:
    """Platform half of admission; the caller holds :func:`lock_platform`."""
    return admission_decision(tenant_id, capacity=int(config["platformCapacity"]),
                              active=await active_by_tenant(db), held=await held_by_tenant(db, config))


def platform_cps(config: dict[str, Any] | None, settings: Any) -> int:
    """New outbound calls per second the platform Vobiz account allows."""
    configured = int((config or {}).get("platformCps") or 0)
    if configured > 0:
        return max(1, min(1000, configured))
    return max(1, min(100, int(getattr(settings, "saas_max_outbound_cps", 1) or 1)))


async def held_total(db, config: dict[str, Any], *, exclude: uuid.UUID | None = None) -> int:
    return sum(row["held"] for tid, row in (await held_by_tenant(db, config)).items() if tid != exclude)


async def platform_active_calls(db) -> int:
    """Live PSTN calls across every tenant (reservations plus untracked live calls)."""
    from server.db.models.entities import Call
    from server.db.models.phase5_models import PstnDialRequest
    from server.services.saas.call_admission import ACTIVE

    reservations = select(PstnDialRequest.call_id).where(
        PstnDialRequest.status.in_(ACTIVE), PstnDialRequest.call_id.is_not(None))
    tracked = (await db.execute(select(func.count()).select_from(PstnDialRequest).where(
        PstnDialRequest.status.in_(ACTIVE)))).scalar_one()
    untracked = (await db.execute(select(func.count()).select_from(Call).where(
        Call.channel == "pstn", Call.ended_at.is_(None), Call.call_id.not_in(reservations)))).scalar_one()
    return int(tracked or 0) + int(untracked or 0)


async def lock_platform(db) -> None:
    """Serialize cross-tenant admission so two tenants cannot both take the last channel."""
    if db.bind.dialect.name == "postgresql":
        from sqlalchemy import text

        await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _PLATFORM_LOCK_KEY})


def capacity_exception(scope: str) -> HTTPException:
    if scope in ("platform", "platform_full", "reserved_full"):
        return HTTPException(429, detail={"error": {
            "code": "platform_capacity", "retry_after": 5,
            "message": "All call lines are busy right now, so this call was not placed and you were not charged. "
                       "Please try again in a moment. Campaign calls wait and retry on their own."}},
            headers={"Retry-After": "5"})
    return HTTPException(429, detail={"error": {
        "code": "concurrency_limit", "retry_after": 5,
        "message": "All your call channels are in use, so this call was not placed. Wait for a call to end, "
                   "or add extra channels in Billing. Campaign calls wait and retry on their own."}},
        headers={"Retry-After": "5"})


async def record_daily(
    factory,
    tenant_id: uuid.UUID,
    *,
    active: int | None = None,
    cap: int | None = None,
    admitted: int = 0,
    rejected: int = 0,
    queued: int = 0,
) -> None:
    """Best-effort daily analytics upsert. Never raises into the call path."""
    if factory is None:
        return
    try:
        from server.db.models.concurrency_models import TenantConcurrencyDaily

        today = _utcnow().date()
        async with factory() as db:
            row = await db.get(TenantConcurrencyDaily, (tenant_id, today), with_for_update=True)
            if row is None:
                row = TenantConcurrencyDaily(tenant_id=tenant_id, day=today, peak_active=0, channel_cap=0,
                                             admitted=0, rejected=0, queued=0, updated_at=_utcnow())
                db.add(row)
            if active is not None:
                row.peak_active = max(int(row.peak_active or 0), int(active))
            if cap is not None:
                row.channel_cap = int(cap)
            row.admitted = int(row.admitted or 0) + admitted
            row.rejected = int(row.rejected or 0) + rejected
            row.queued = int(row.queued or 0) + queued
            row.updated_at = _utcnow()
            await db.commit()
    except Exception as exc:  # noqa: BLE001 -- analytics must never block a call
        logger.debug("[CHANNELS] daily usage not recorded: %s", type(exc).__name__)


# ---------------------------------------------------------------------------
# Quotes and changes (tenant)
# ---------------------------------------------------------------------------

def _prorated(price_minor: int, channels: int, remaining: timedelta) -> int:
    if price_minor <= 0 or channels <= 0:
        return 0
    seconds = max(0.0, min(remaining.total_seconds(), PERIOD.total_seconds()))
    return _half_up(Decimal(price_minor) * channels * Decimal(str(seconds)) / Decimal(str(PERIOD.total_seconds())))


def _quote(config: dict[str, Any], sub: Any, target: int, included: int, now: datetime,
           number_channels: int = 0) -> dict[str, Any]:
    price_paise = int(config["priceInrPaisePerChannel"])
    price_micros = int(config["priceUsdMicrosPerChannel"])
    current = _paid_in_force(sub, now)
    in_period = (
        sub is not None and sub.status in ("active", "grace") and sub.current_period_end is not None
        and _aware(sub.current_period_end) > now
    )
    pending = getattr(sub, "pending_paid_channels", None) if sub is not None else None
    if target > current:
        if in_period:
            remaining = _aware(sub.current_period_end) - now
            added = target - current
            paise = _prorated(price_paise, added, remaining)
            micros = _prorated(price_micros, added, remaining)
            effect, period_end, rule = "now", _aware(sub.current_period_end), "prorated"
        else:
            paise, micros = price_paise * target, price_micros * target
            effect, period_end, rule = "now", now + PERIOD, "new_period"
    else:
        paise = micros = 0
        effect = "period_end" if target < current else "none"
        period_end = _aware(sub.current_period_end) if in_period else None
        rule = "downgrade_at_period_end" if target < current else ("cancel_pending_downgrade" if pending is not None else "no_change")
    cents = _half_up(Decimal(micros) / 10_000) if micros else 0
    if micros and cents == 0:
        cents = 1
    return {
        "currentPaidChannels": current,
        "targetPaidChannels": target,
        "includedChannels": included,
        "numberChannels": number_channels,
        "totalChannelsAfter": included + number_channels + target,
        "pendingPaidChannels": pending,
        "priceInrPerChannel": round(price_paise / 100.0, 2),
        "priceUsdPerChannel": round(price_micros / 1_000_000.0, 6),
        "periodDays": PERIOD_DAYS,
        "rule": rule,
        "effective": effect,
        "periodEnd": period_end.isoformat() if period_end else None,
        "chargeNowInrPaise": paise,
        "chargeNowCents": cents,
        "chargeNowInr": round(paise / 100.0, 2),
        "chargeNowUsd": round(cents / 100.0, 2),
        "recurringInr": round(price_paise * target / 100.0, 2),
        "recurringUsd": round(price_micros * target / 1_000_000.0, 2),
        "pricingVersion": config["version"],
        "free": price_paise <= 0,
    }


async def _included_for(db, tenant_id: uuid.UUID, config: dict[str, Any]) -> int:
    from server.db.models.entities import Tenant

    tenant = await db.get(Tenant, tenant_id)
    limits = (tenant.limits if tenant else None) or {}
    value = limits.get("included_channels")
    return max(0, int(value if value is not None else config["includedChannels"]))


def _validate_target(config: dict[str, Any], target: int, included: int) -> None:
    if target < 0:
        raise _http(422, "invalid_channels", "Channels cannot be negative.")
    limit = config["maxChannelsPerTenant"]
    if limit and included + target > limit:
        raise _http(422, "channel_limit", f"A workspace can hold at most {limit} channels. Contact support for more.")
    if included + target > config["platformCapacity"]:
        raise _http(409, "platform_capacity", "That many channels is more than the platform can provide right now.")


async def quote_change(tenant_id: uuid.UUID, target_paid: int) -> dict[str, Any]:
    config = await load_pricing(force=True)
    if not config:
        raise _http(409, "channels_unavailable", "Additional call channels are not offered yet.")
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    from server.db.models.concurrency_models import TenantChannelSubscription

    async with factory() as db:
        included = await _included_for(db, tenant_id, config)
        _validate_target(config, int(target_paid), included)
        sub = await db.get(TenantChannelSubscription, tenant_id)
        number_channels = await number_count(db, tenant_id) * int(config.get("channelsPerNumber", DEFAULT_CHANNELS_PER_NUMBER))
        return _quote(config, sub, int(target_paid), included, _utcnow(), number_channels)


async def apply_change(
    tenant_id: uuid.UUID,
    target_paid: int,
    *,
    request_id: str,
    expected_charge_inr_paise: int | None,
    user_id: uuid.UUID | None,
    actor: str,
) -> dict[str, Any]:
    """Buy, add, schedule a decrease of, or restore paid channels; idempotent per request id."""
    request_id = (request_id or "").strip()
    if not request_id or len(request_id) > 64:
        raise _http(422, "request_id_required", "A request id is required.")
    config = await load_pricing(force=True)
    if not config:
        raise _http(409, "channels_unavailable", "Additional call channels are not offered yet.")
    target = int(target_paid)
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    from server.db.models.concurrency_models import TenantChannelEvent, TenantChannelSubscription
    from server.services.saas.billing_wallet_service import debit_exact_in_session
    from server.services.saas.call_admission import lock_tenant

    ref = f"channels:{tenant_id}:{request_id}"
    async with factory() as db:
        await lock_tenant(db, tenant_id)
        await lock_platform(db)
        previous = (await db.execute(select(TenantChannelEvent).where(
            TenantChannelEvent.tenant_id == tenant_id, TenantChannelEvent.reference_id == ref))).scalar_one_or_none()
        if previous is not None:
            sub = await db.get(TenantChannelSubscription, tenant_id)
            return {"ok": True, "duplicate": True, "subscription": _sub_payload(sub, config, previous.channels_after)}
        included = await _included_for(db, tenant_id, config)
        _validate_target(config, target, included)
        sub = await db.get(TenantChannelSubscription, tenant_id, with_for_update=True)
        now = _utcnow()
        if sub is None:
            sub = TenantChannelSubscription(tenant_id=tenant_id, paid_channels=0, status="none",
                                            price_inr_paise_per_channel=0, price_usd_micros_per_channel=0,
                                            created_at=now, updated_at=now)
            db.add(sub)
            await db.flush()
        if sub.status == "grace" and target > _paid_in_force(sub, now):
            raise _http(402, "renewal_overdue",
                        "Your channel renewal is overdue. Add funds; renewal is retried automatically, then you can add channels.")
        quote = _quote(config, sub, target, included, now)
        if expected_charge_inr_paise is not None and int(expected_charge_inr_paise) != quote["chargeNowInrPaise"]:
            raise _http(409, "quote_changed", "The price changed. Review the new total and confirm again.", quote=quote)
        before = _paid_in_force(sub, now)
        if target > before:
            # Platform-wide oversell guard: held channels (every tenant's number
            # channels and paid channels) can never exceed what Vobiz sold us.
            held_now = await held_by_tenant(db, config)
            held_others = sum(row["held"] for tid, row in held_now.items() if tid != tenant_id)
            # Includes this tenant's numbers still being activated.
            own_numbers = held_now.get(tenant_id, {}).get("numberChannels", 0)
            if held_others + own_numbers + target > config["platformCapacity"]:
                from server.services.saas import capacity_incidents

                await capacity_incidents.record(
                    "channel_blocked", tenant_id,
                    detail=f"held {held_others + own_numbers} + {target} paid > capacity {config['platformCapacity']}")
                raise _http(409, "platform_capacity",
                            "We're adding call capacity right now, so we can't add that many channels yet. "
                            "Try fewer, or try again later. You were not charged.")
            charge = await debit_exact_in_session(
                db, tenant_id, kind="channel_purchase", reference_id=ref, user_id=user_id,
                want_cents=quote["chargeNowCents"], want_paise=quote["chargeNowInrPaise"],
                insufficient_message=(f"Add funds to buy channels. This change costs ₹{quote['chargeNowInr']:.2f} now."),
            )
            if quote["rule"] == "new_period":
                sub.current_period_start, sub.current_period_end = now, now + PERIOD
            sub.paid_channels = target
            sub.pending_paid_channels = None
            sub.status = "active"
            sub.grace_until = None
            sub.notice = None
            sub.price_inr_paise_per_channel = config["priceInrPaisePerChannel"]
            sub.price_usd_micros_per_channel = config["priceUsdMicrosPerChannel"]
            sub.pricing_version = config["version"]
            kind = "purchase"
            amount_paise, amount_cents = int(charge.get("amountInrPaise") or 0), int(charge.get("amountCents") or 0)
            after = target
        elif target < before:
            sub.pending_paid_channels = target
            kind, amount_paise, amount_cents, after = "downgrade_scheduled", 0, 0, before
        else:
            if sub.pending_paid_channels is None:
                return {"ok": True, "unchanged": True, "subscription": _sub_payload(sub, config, before)}
            sub.pending_paid_channels = None
            kind, amount_paise, amount_cents, after = "downgrade_cancelled", 0, 0, before
        sub.updated_at = now
        db.add(TenantChannelEvent(tenant_id=tenant_id, kind=kind, channels_before=before, channels_after=after,
                                  amount_inr_paise=amount_paise, amount_cents=amount_cents, reference_id=ref,
                                  pricing_version=config["version"], actor=actor[:255], created_at=now))
        pending_after = sub.pending_paid_channels
        await db.commit()
        payload = _sub_payload(sub, config, after, included=included)
    await _activity(tenant_id, f"billing.channels.{kind}", actor, {"before": before, "after": after,
                    "pending": pending_after, "chargeInrPaise": amount_paise, "pricingVersion": config["version"]})
    return {"ok": True, "kind": kind, "chargedInrPaise": amount_paise, "chargedCents": amount_cents, "subscription": payload}


def _sub_payload(sub: Any, config: dict[str, Any] | None, paid: int | None = None, *, included: int | None = None) -> dict[str, Any]:
    if sub is None:
        return {"status": "none", "paidChannels": 0, "pendingPaidChannels": None, "periodStart": None,
                "periodEnd": None, "graceUntil": None, "notice": None, "includedChannels": included}
    return {
        "status": sub.status,
        "paidChannels": int(paid if paid is not None else _paid_in_force(sub)),
        "pendingPaidChannels": sub.pending_paid_channels,
        "periodStart": _aware(sub.current_period_start).isoformat() if sub.current_period_start else None,
        "periodEnd": _aware(sub.current_period_end).isoformat() if sub.current_period_end else None,
        "graceUntil": _aware(sub.grace_until).isoformat() if sub.grace_until else None,
        "notice": sub.notice,
        "lockedPriceInrPerChannel": round(int(sub.price_inr_paise_per_channel or 0) / 100.0, 2),
        "pricingVersion": sub.pricing_version,
        "includedChannels": included,
    }


async def _activity(tenant_id: uuid.UUID, action: str, actor: str, payload: dict[str, Any], outcome: str = "ok") -> None:
    try:
        from server.services.saas.activity_log import record_event

        await record_event(action=action, resource_type="channels", resource_id=str(tenant_id), actor=actor,
                           tenant_id=tenant_id, payload=payload, source="billing", outcome=outcome)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Renewal
# ---------------------------------------------------------------------------

async def renew_tenant(tenant_id: uuid.UUID, *, now: datetime | None = None) -> str:
    """Renew one due subscription. Returns renewed | grace | lapsed | ended | skipped."""
    config = await load_pricing()
    factory = get_session_factory()
    if factory is None:
        return "skipped"
    from server.db.models.concurrency_models import TenantChannelEvent, TenantChannelSubscription
    from server.services.saas.billing_wallet_service import debit_exact_in_session

    now = now or _utcnow()
    notice_event: tuple[str, dict[str, Any]] | None = None
    async with factory() as db:
        sub = await db.get(TenantChannelSubscription, tenant_id, with_for_update=True)
        if sub is None or sub.status not in ("active", "grace") or sub.current_period_end is None:
            return "skipped"
        period_end = _aware(sub.current_period_end)
        if period_end > now:
            return "skipped"
        if sub.status == "grace" and sub.last_renewal_attempt_at is not None and \
                now - _aware(sub.last_renewal_attempt_at) < RENEWAL_RETRY_INTERVAL and \
                not (sub.grace_until is not None and _aware(sub.grace_until) <= now):
            return "skipped"
        before = int(sub.paid_channels or 0)
        channels = int(sub.pending_paid_channels if sub.pending_paid_channels is not None else before)
        included = await _included_for(db, tenant_id, config) if config else 0
        if channels <= 0:
            sub.paid_channels, sub.pending_paid_channels, sub.status = 0, None, "none"
            sub.current_period_start = sub.current_period_end = sub.grace_until = None
            sub.notice = None
            sub.updated_at = now
            db.add(TenantChannelEvent(tenant_id=tenant_id, kind="downgrade_applied", channels_before=before,
                                      channels_after=0, created_at=now, actor="system"))
            await db.commit()
            return "ended"
        price_paise = int(config["priceInrPaisePerChannel"]) if config else int(sub.price_inr_paise_per_channel or 0)
        price_micros = int(config["priceUsdMicrosPerChannel"]) if config else int(sub.price_usd_micros_per_channel or 0)
        want_paise = price_paise * channels
        want_micros = price_micros * channels
        want_cents = _half_up(Decimal(want_micros) / 10_000) if want_micros else 0
        ref = f"channel_renewal:{tenant_id}:{period_end.strftime('%Y%m%dT%H%M%S')}"
        sub.last_renewal_attempt_at = now
        try:
            charge = await debit_exact_in_session(
                db, tenant_id, kind="channel_renewal", reference_id=ref, want_cents=want_cents, want_paise=want_paise,
                insufficient_message="Add funds to renew your call channels.")
        except HTTPException:
            grace_days = int(config["graceDays"]) if config else DEFAULT_GRACE_DAYS
            grace_until = period_end + timedelta(days=grace_days)
            if sub.status == "active":
                sub.status = "grace"
                sub.grace_until = grace_until
                sub.notice = (
                    f"Renewal of {channels} call channel{'s' if channels != 1 else ''} "
                    f"(₹{want_paise / 100:.2f}) failed: not enough wallet balance. Add funds by "
                    f"{grace_until.strftime('%d %b %Y')} or the workspace drops to {included} included "
                    f"channel{'s' if included != 1 else ''}."
                )
                db.add(TenantChannelEvent(tenant_id=tenant_id, kind="renewal_failed", channels_before=before,
                                          channels_after=before, amount_inr_paise=0, reference_id=None,
                                          pricing_version=config["version"] if config else None, actor="system",
                                          created_at=now))
                notice_event = ("billing.channels.renewal_failed", {"channels": channels, "graceUntil": grace_until.isoformat()})
                result = "grace"
            elif sub.grace_until is not None and _aware(sub.grace_until) <= now:
                sub.status = "lapsed"
                sub.paid_channels = 0
                sub.pending_paid_channels = None
                sub.current_period_start = sub.current_period_end = None
                sub.grace_until = None
                sub.notice = (
                    f"Paid call channels ended after the renewal stayed unpaid. The workspace now has "
                    f"{included} included channel{'s' if included != 1 else ''}; buy channels again in Billing."
                )
                db.add(TenantChannelEvent(tenant_id=tenant_id, kind="lapsed", channels_before=before,
                                          channels_after=0, actor="system", created_at=now))
                notice_event = ("billing.channels.lapsed", {"channelsBefore": before})
                result = "lapsed"
            else:
                result = "grace"
            sub.updated_at = now
            await db.commit()
            if notice_event:
                await _activity(tenant_id, notice_event[0], "system", notice_event[1], outcome="error")
            return result
        sub.current_period_start = period_end
        sub.current_period_end = period_end + PERIOD
        sub.paid_channels = channels
        sub.pending_paid_channels = None
        sub.status = "active"
        sub.grace_until = None
        sub.notice = None
        if config:
            sub.price_inr_paise_per_channel = price_paise
            sub.price_usd_micros_per_channel = price_micros
            sub.pricing_version = config["version"]
        sub.updated_at = now
        if not charge.get("duplicate"):
            db.add(TenantChannelEvent(tenant_id=tenant_id, kind="renewal", channels_before=before,
                                      channels_after=channels, amount_inr_paise=int(charge.get("amountInrPaise") or 0),
                                      amount_cents=int(charge.get("amountCents") or 0), reference_id=ref,
                                      pricing_version=config["version"] if config else None, actor="system",
                                      created_at=now))
        await db.commit()
    return "renewed"


async def renew_due(*, now: datetime | None = None, limit: int = 50) -> dict[str, int]:
    factory = get_session_factory()
    if factory is None:
        return {}
    from server.db.models.concurrency_models import TenantChannelSubscription

    now = now or _utcnow()
    async with factory() as db:
        ids = (await db.execute(select(TenantChannelSubscription.tenant_id).where(
            TenantChannelSubscription.status.in_(("active", "grace")),
            TenantChannelSubscription.current_period_end <= now,
        ).order_by(TenantChannelSubscription.current_period_end).limit(limit))).scalars().all()
    counts: dict[str, int] = {}
    for tenant_id in ids:
        try:
            outcome = await renew_tenant(tenant_id, now=now)
        except Exception as exc:  # noqa: BLE001 -- one tenant never blocks the rest
            logger.warning("[CHANNELS] renewal failed tenant=%s err=%s", tenant_id, type(exc).__name__)
            outcome = "error"
        counts[outcome] = counts.get(outcome, 0) + 1
    return counts


async def renewal_loop(interval_s: float = 600.0) -> None:
    import asyncio

    while True:
        try:
            result = await renew_due()
            if result:
                logger.info("[CHANNELS] renewal pass: %s", result)
        except asyncio.CancelledError:
            break
        except Exception as exc:  # noqa: BLE001
            logger.warning("[CHANNELS] renewal pass error: %s", type(exc).__name__)
        await asyncio.sleep(interval_s)


# ---------------------------------------------------------------------------
# Tenant status and analytics
# ---------------------------------------------------------------------------

async def tenant_overview(tenant_id: uuid.UUID, *, days: int = 30) -> dict[str, Any]:
    from server.config.env import get_settings
    from server.db.models.concurrency_models import (
        TenantChannelEvent,
        TenantChannelSubscription,
        TenantConcurrencyDaily,
    )
    from server.db.models.entities import Tenant
    from server.services.saas.call_admission import active_capacity

    config = await load_pricing()
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    days = max(1, min(int(days), 180))
    since_day = _utcnow().date() - timedelta(days=days - 1)
    async with factory() as db:
        tenant = await db.get(Tenant, tenant_id)
        if tenant is None:
            raise _http(404, "tenant_not_found", "Workspace not found.")
        cap = await channel_cap(db, tenant, settings=get_settings())
        active_now = await active_capacity(db, tenant_id)
        sub = await db.get(TenantChannelSubscription, tenant_id) if config else None
        try:
            daily_rows = (await db.execute(select(TenantConcurrencyDaily).where(
                TenantConcurrencyDaily.tenant_id == tenant_id, TenantConcurrencyDaily.day >= since_day,
            ).order_by(TenantConcurrencyDaily.day))).scalars().all()
            events = (await db.execute(select(TenantChannelEvent).where(
                TenantChannelEvent.tenant_id == tenant_id,
            ).order_by(TenantChannelEvent.created_at.desc()).limit(50))).scalars().all()
        except Exception as exc:  # noqa: BLE001 -- tables absent before migration
            logger.info("[CHANNELS] analytics unavailable: %s", type(exc).__name__)
            daily_rows, events = [], []
    by_day = {row.day: row for row in daily_rows}
    daily = []
    for offset in range(days):
        day: date = since_day + timedelta(days=offset)
        row = by_day.get(day)
        daily.append({
            "day": day.isoformat(),
            "peakActive": int(row.peak_active) if row else 0,
            "channelCap": int(row.channel_cap) if row and row.channel_cap else cap["cap"],
            "admitted": int(row.admitted) if row else 0,
            "rejected": int(row.rejected) if row else 0,
            "queued": int(row.queued) if row else 0,
        })
    charges = [{
        "id": str(ev.id), "kind": ev.kind, "channelsBefore": ev.channels_before, "channelsAfter": ev.channels_after,
        "amountInr": round(int(ev.amount_inr_paise or 0) / 100.0, 2), "amountUsd": round(int(ev.amount_cents or 0) / 100.0, 2),
        "referenceId": ev.reference_id, "pricingVersion": ev.pricing_version,
        "createdAt": _aware(ev.created_at).isoformat() if ev.created_at else None,
    } for ev in events]
    return {
        "pricing": public_pricing(config),
        "channels": {
            "cap": cap["cap"], "included": cap["included"], "paid": cap["paid"], "legacy": cap["legacy"],
            "numbers": cap.get("numbers", 0), "numberChannels": cap.get("numberChannels", 0),
            "held": cap.get("held", cap["paid"]),
            "channelsPerNumber": (config or {}).get("channelsPerNumber", DEFAULT_CHANNELS_PER_NUMBER) if config else 0,
            "activeNow": active_now,
        },
        "subscription": _sub_payload(sub, config, included=cap["included"]) if config else None,
        "daily": daily,
        "totals": {
            "peakActive": max((d["peakActive"] for d in daily), default=0),
            "admitted": sum(d["admitted"] for d in daily),
            "rejected": sum(d["rejected"] for d in daily),
            "queued": sum(d["queued"] for d in daily),
            "chargedInr": round(sum(c["amountInr"] for c in charges) , 2),
        },
        "events": charges,
    }


async def platform_overview() -> dict[str, Any]:
    """Admin view: capacity, sold channels, live calls, and the Vobiz account's own counters."""
    from server.db.models.concurrency_models import TenantChannelSubscription
    from server.services.saas.vobiz_concurrency import fetch_platform_concurrency

    config = await load_pricing(force=True)
    sold = tenants = live = 0
    factory = get_session_factory()
    if factory is not None:
        async with factory() as db:
            try:
                sold, tenants = (await db.execute(select(
                    func.coalesce(func.sum(TenantChannelSubscription.paid_channels), 0), func.count()).where(
                    TenantChannelSubscription.status.in_(("active", "grace"))))).one()
            except Exception:  # noqa: BLE001 -- before migration
                sold, tenants = 0, 0
            live = await platform_active_calls(db)
    return {
        "pricing": public_pricing(config),
        "soldPaidChannels": int(sold or 0),
        "tenantsWithPaidChannels": int(tenants or 0),
        "liveCalls": int(live or 0),
        "vobiz": await fetch_platform_concurrency(),
    }
