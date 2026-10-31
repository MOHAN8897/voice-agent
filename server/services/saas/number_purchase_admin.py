"""Platform-admin view of number purchases: what happened, why, and what to do.

Read side: every purchase with its money trail (debit, refund), the provisioning
job's error explained in operator language, refusals that stopped before any
charge (from the activity log), and platform-level alerts (carrier balance,
rent below carrier price, credentials, stuck jobs).

Write side: a guarded retry and a guarded refund. Neither can turn a refunded
purchase back into a number, refund a number the tenant now owns, or refund a
job the worker is running.

All carrier calls here are read-only (balance, inventory listing).
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, desc, select

from server.db.connection import get_session_factory
from server.db.models.entities import Tenant
from server.db.models.phase5_models import AuditLog
from server.db.models.saas_models import (
    BillingWalletTransaction,
    NumberPurchase,
    NumberReservation,
    ProvisionJob,
)
from server.services.saas.number_purchase_errors import (
    PLATFORM_CODES,
    admin_explanation,
)

logger = logging.getLogger(__name__)

BUCKETS = ("succeeded", "provisioning", "needs_attention", "failed", "refunded")
#: A purchase still provisioning after this long is shown as needing attention.
STUCK_AFTER = timedelta(minutes=15)
REFUSAL_WINDOW = timedelta(days=7)
_INVENTORY_CACHE_SECONDS = 120
_inventory_cache: dict[str, Any] = {"at": 0.0, "value": None}


class PurchaseAdminError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.message = message
        self.status_code = status_code


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _iso(value: datetime | None) -> str | None:
    value = _aware(value)
    return value.isoformat() if value else None


def _money(tx: BillingWalletTransaction | None) -> dict | None:
    if tx is None:
        return None
    return {
        "usd": round(abs(int(tx.amount_cents or 0)) / 100.0, 2),
        "inr": round(abs(int(tx.amount_inr_paise or 0)) / 100.0, 2),
        "at": _iso(tx.created_at),
    }


def _bucket(purchase: NumberPurchase, job: ProvisionJob | None, debit, refund) -> tuple[str, bool]:
    """(bucket, stuck). Buckets are exclusive so filter counts add up."""
    status = str(purchase.status or "")
    if status in {"active", "provisioned"}:
        return "succeeded", False
    if refund is not None:
        return "refunded", False
    if status == "needs_attention":
        return "needs_attention", False
    if status in {"paid", "provisioning"}:
        updated = _aware(purchase.updated_at) or _aware(purchase.created_at)
        stuck = bool(updated and _utcnow() - updated > STUCK_AFTER)
        return ("needs_attention" if stuck else "provisioning"), stuck
    if status in {"failed", "refunded"}:
        # Money taken and not returned is an operator problem, not a closed case.
        return ("needs_attention" if debit is not None and _debited(debit) else "failed"), False
    return "needs_attention", False


def _debited(tx: BillingWalletTransaction | None) -> bool:
    return tx is not None and (int(tx.amount_cents or 0) != 0 or int(tx.amount_inr_paise or 0) != 0)


def _job_error(job: ProvisionJob | None) -> dict:
    return job.last_error if job is not None and isinstance(job.last_error, dict) else {}


def _issue_code(purchase, job, bucket: str, stuck: bool, debit, refund) -> str | None:
    err = _job_error(job)
    if bucket == "succeeded":
        return None
    if stuck:
        return "provisioning_stuck"
    if purchase.status in {"failed", "refunded"} and _debited(debit) and refund is None:
        return "refund_failed"
    return str(err.get("code") or "") or ("provider_provision_failed" if purchase.status == "failed" else None)


def _actions(purchase, job, bucket: str, stuck: bool, refund) -> dict:
    running = job is not None and job.status == "running" and not stuck
    owned = purchase.phone_number_id is not None
    can_refund = (
        refund is None
        and not owned
        and not running
        and purchase.status in {"failed", "needs_attention", "paid", "provisioning", "refunded"}
        and (purchase.status in {"failed", "needs_attention", "refunded"} or stuck)
    )
    can_retry = (
        refund is None
        and not running
        and (purchase.status == "needs_attention" or stuck)
    )
    return {"canRetry": can_retry, "canRefund": can_refund}


def _serialize(purchase, tenant_name, job, debit, refund) -> dict:
    bucket, stuck = _bucket(purchase, job, debit, refund)
    code = _issue_code(purchase, job, bucket, stuck, debit, refund)
    err = _job_error(job)
    if refund is not None:
        refund_state = "refunded"
    elif not _debited(debit):
        refund_state = "not_charged"
    elif purchase.status in {"failed", "refunded"}:
        refund_state = "failed"  # money taken, purchase closed, nothing returned
    elif bucket in {"succeeded", "provisioning"}:
        refund_state = "not_needed"
    else:
        refund_state = "pending"  # needs a decision: retry or refund
    return {
        "purchaseId": str(purchase.id),
        "tenantId": str(purchase.tenant_id),
        "tenantName": tenant_name,
        "e164": purchase.e164,
        "country": purchase.country_code,
        "provider": purchase.provider,
        "status": bucket,
        "rawStatus": purchase.status,
        "stuck": stuck,
        "createdAt": _iso(purchase.created_at),
        "updatedAt": _iso(purchase.updated_at),
        "charged": _money(debit) if _debited(debit) else None,
        "refund": {"state": refund_state, **({"amount": _money(refund)} if refund is not None else {})},
        "job": (
            {
                "status": job.status,
                "attempts": int(job.attempts or 0),
                "updatedAt": _iso(job.updated_at),
            }
            if job is not None
            else None
        ),
        "issue": admin_explanation(code),
        "carrier": {
            "errorType": err.get("error_type"),
            "providerStatus": err.get("providerStatus"),
            "context": err.get("context") if isinstance(err.get("context"), dict) else None,
        }
        if err
        else None,
        "phoneNumberId": str(purchase.phone_number_id) if purchase.phone_number_id else None,
        **_actions(purchase, job, bucket, stuck, refund),
    }


async def _load_rows(session, *, purchase_id: uuid.UUID | None = None, limit: int = 500):
    stmt = (
        select(NumberPurchase, Tenant.name, ProvisionJob)
        .join(Tenant, Tenant.tenant_id == NumberPurchase.tenant_id, isouter=True)
        .join(ProvisionJob, ProvisionJob.purchase_id == NumberPurchase.id, isouter=True)
        .order_by(desc(NumberPurchase.created_at))
    )
    if purchase_id is not None:
        stmt = stmt.where(NumberPurchase.id == purchase_id)
    else:
        stmt = stmt.limit(limit)
    rows = (await session.execute(stmt)).all()
    refs = []
    for purchase, _name, _job in rows:
        refs += [f"did:{purchase.id}", f"did_refund:{purchase.id}"]
    txs: dict[str, BillingWalletTransaction] = {}
    for i in range(0, len(refs), 400):
        chunk = refs[i : i + 400]
        for tx in (
            await session.execute(
                select(BillingWalletTransaction).where(BillingWalletTransaction.reference_id.in_(chunk))
            )
        ).scalars():
            txs[str(tx.reference_id)] = tx
    return [
        (purchase, name, job, txs.get(f"did:{purchase.id}"), txs.get(f"did_refund:{purchase.id}"))
        for purchase, name, job in rows
    ]


async def list_admin_purchases(
    *, status: str | None = None, q: str | None = None, limit: int = 50, offset: int = 0
) -> dict:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    async with factory() as session:
        rows = await _load_rows(session)
    items = [_serialize(*row) for row in rows]
    counts = {b: 0 for b in BUCKETS}
    for item in items:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    needle = str(q or "").strip().lower()
    if needle:
        items = [
            i for i in items
            if needle in " ".join(
                str(i.get(k) or "") for k in ("e164", "tenantName", "tenantId", "purchaseId")
            ).lower()
        ]
    if status and status in BUCKETS:
        items = [i for i in items if i["status"] == status]
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    return {
        "items": items[offset : offset + limit],
        "total": len(items),
        "limit": limit,
        "offset": offset,
        "counts": counts,
    }


def _refusal(row: AuditLog, tenant_names: dict) -> dict:
    payload = row.payload if isinstance(row.payload, dict) else {}
    code = str(payload.get("error") or payload.get("code") or "unknown")
    explanation = admin_explanation(code)
    return {
        "id": str(row.id),
        "at": _iso(row.created_at),
        "tenantId": str(row.tenant_id) if row.tenant_id else None,
        "tenantName": tenant_names.get(row.tenant_id),
        "e164": payload.get("e164") or row.resource_id,
        "code": code,
        "httpStatus": payload.get("httpStatus"),
        "platform": code in PLATFORM_CODES,
        "context": payload.get("context") if isinstance(payload.get("context"), dict) else None,
        "issue": explanation,
        "actor": row.actor,
    }


async def list_refusals(*, platform_only: bool = False, limit: int = 100) -> dict:
    """Buy requests refused before any charge, newest first (activity log)."""
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    since = _utcnow() - REFUSAL_WINDOW
    async with factory() as session:
        rows = (
            await session.execute(
                select(AuditLog)
                .where(AuditLog.action == "number.purchase.refused", AuditLog.created_at >= since)
                .order_by(desc(AuditLog.created_at))
                .limit(500)
            )
        ).scalars().all()
        tenant_ids = {r.tenant_id for r in rows if r.tenant_id}
        names = {}
        if tenant_ids:
            names = dict(
                (await session.execute(select(Tenant.tenant_id, Tenant.name).where(Tenant.tenant_id.in_(tenant_ids)))).all()
            )
    items = [_refusal(r, names) for r in rows]
    if platform_only:
        items = [i for i in items if i["platform"]]
    return {"items": items[: max(1, min(limit, 500))], "total": len(items), "windowDays": REFUSAL_WINDOW.days}


async def purchase_detail(purchase_id: uuid.UUID) -> dict | None:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    async with factory() as session:
        rows = await _load_rows(session, purchase_id=purchase_id)
        if not rows:
            return None
        purchase, name, job, debit, refund = rows[0]
        created = _aware(purchase.created_at) or _utcnow()
        events = (
            await session.execute(
                select(AuditLog)
                .where(
                    (AuditLog.resource_id == str(purchase.id))
                    | (
                        (AuditLog.resource_id == purchase.e164)
                        & (AuditLog.tenant_id == purchase.tenant_id)
                        & (AuditLog.created_at >= created - timedelta(hours=1))
                        & (AuditLog.created_at <= created + timedelta(days=2))
                    )
                )
                .order_by(AuditLog.created_at)
                .limit(100)
            )
        ).scalars().all()
    item = _serialize(purchase, name, job, debit, refund)
    timeline: list[dict] = [
        {"at": _iso(purchase.created_at), "kind": "created", "label": "Purchase created", "tone": "info"}
    ]
    if debit is not None:
        money = _money(debit)
        timeline.append({
            "at": money["at"], "kind": "debit", "tone": "info",
            "label": f"Wallet debited ₹{money['inr']:.2f} / ${money['usd']:.2f}" if _debited(debit) else "No charge (free number)",
        })
    for ev in events:
        payload = ev.payload if isinstance(ev.payload, dict) else {}
        code = payload.get("code") or payload.get("error")
        explanation = admin_explanation(code) if code else None
        timeline.append({
            "at": _iso(ev.created_at),
            "kind": ev.action,
            "label": _EVENT_LABELS.get(ev.action, ev.action),
            "detail": explanation["title"] if explanation else None,
            "actor": ev.actor,
            "tone": "error" if ev.outcome == "error" else ("warning" if ev.severity == "warning" else "info"),
        })
    if refund is not None:
        money = _money(refund)
        timeline.append({"at": money["at"], "kind": "refund", "tone": "success",
                         "label": f"Refunded ₹{money['inr']:.2f} / ${money['usd']:.2f} to the wallet"})
    timeline.sort(key=lambda e: e.get("at") or "")
    item["timeline"] = timeline
    return item


_EVENT_LABELS = {
    "number.purchase.accepted": "Tenant confirmed purchase; job queued",
    "number.purchase.refused": "Purchase refused before charge",
    "number.provision.done": "Number activated",
    "number.provision.awaiting_provider_id": "Created, waiting for carrier number ID",
    "number.provision.failed": "Provisioning failed",
    "number.provision.needs_attention": "Provisioning needs attention",
    "purchase.retry_provision": "Admin retried provisioning",
    "purchase.refund": "Admin refunded",
}


async def retry_purchase(purchase_id: uuid.UUID) -> dict:
    """Requeue a purchase the worker gave up on. Never a refunded or owned one."""
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    async with factory() as session:
        rows = await _load_rows(session, purchase_id=purchase_id)
        if not rows:
            raise PurchaseAdminError("not_found", "Purchase not found.", 404)
        purchase, _name, job, _debit, refund = rows[0]
        _bucket_name, stuck = _bucket(purchase, job, _debit, refund)
        if refund is not None or purchase.status in {"failed", "refunded"}:
            raise PurchaseAdminError(
                "purchase_closed",
                "This purchase was failed and refunded. Retrying would hand out a number nobody paid for; ask the tenant to buy again.",
            )
        if purchase.status in {"active", "provisioned"} or purchase.phone_number_id:
            raise PurchaseAdminError("purchase_complete", "This number is already active.")
        if purchase.status != "needs_attention" and not stuck:
            raise PurchaseAdminError("purchase_in_progress", "Provisioning is still running; wait for it to finish.")
        locked = await session.get(NumberPurchase, purchase_id, with_for_update=True)
        locked.status = "paid"
        locked.updated_at = _utcnow()
        job_row = (
            await session.execute(select(ProvisionJob).where(ProvisionJob.purchase_id == purchase_id).with_for_update())
        ).scalar_one_or_none()
        if job_row is None:
            session.add(ProvisionJob(purchase_id=purchase_id, status="queued", attempts=0,
                                     created_at=_utcnow(), updated_at=_utcnow()))
        else:
            job_row.status = "queued"
            job_row.attempts = 0
            job_row.updated_at = _utcnow()
        tenant_id = locked.tenant_id
        await session.commit()
    return {"ok": True, "tenantId": tenant_id}


async def refund_purchase(purchase_id: uuid.UUID) -> dict:
    """Close a purchase that will not complete and return the tenant's money.

    Refuses an active number (the tenant has it), a job currently running (it may
    still succeed), and a purchase that is merely in progress. The wallet refund
    itself is idempotent (one ``did_refund:<id>`` row at most).
    """
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    async with factory() as session:
        rows = await _load_rows(session, purchase_id=purchase_id)
        if not rows:
            raise PurchaseAdminError("not_found", "Purchase not found.", 404)
        purchase, _name, job, debit, refund = rows[0]
        _b, stuck = _bucket(purchase, job, debit, refund)
        if refund is not None:
            return {"ok": True, "duplicate": True, "tenantId": purchase.tenant_id}
        if purchase.phone_number_id or purchase.status in {"active", "provisioned"}:
            raise PurchaseAdminError(
                "number_owned",
                "The tenant owns this number. Release it from the Accounts page instead of refunding the purchase.",
            )
        if job is not None and job.status == "running" and not stuck:
            raise PurchaseAdminError("purchase_in_progress", "Provisioning is running right now; wait for it to finish.")
        if purchase.status in {"paid", "provisioning"} and not stuck:
            raise PurchaseAdminError("purchase_in_progress", "Provisioning is still in progress; wait for it to finish.")
        locked = await session.get(NumberPurchase, purchase_id, with_for_update=True)
        locked.status = "refunded"
        locked.updated_at = _utcnow()
        job_row = (
            await session.execute(select(ProvisionJob).where(ProvisionJob.purchase_id == purchase_id).with_for_update())
        ).scalar_one_or_none()
        if job_row is not None:
            # The worker only claims "queued"; this stops a later run buying it.
            job_row.status = "cancelled"
            job_row.updated_at = _utcnow()
        await session.execute(delete(NumberReservation).where(NumberReservation.purchase_id == purchase_id))
        tenant_id, user_id = locked.tenant_id, locked.user_id
        await session.commit()
    if not _debited(debit):
        return {"ok": True, "refunded": False, "reason": "nothing_charged", "tenantId": tenant_id}
    from server.services.saas.billing_wallet_service import refund_did_purchase

    result = await refund_did_purchase(tenant_id, user_id=user_id, purchase_id=purchase_id)
    return {"ok": bool(result.get("ok", True)), "refunded": True, "tenantId": tenant_id}


# ------------------------------------------------------------------ health / alerts


async def _inventory_pricing() -> dict | None:
    """Read-only Vobiz inventory price summary, cached briefly."""
    now = time.monotonic()
    if _inventory_cache["value"] is not None and now - _inventory_cache["at"] < _INVENTORY_CACHE_SECONDS:
        return _inventory_cache["value"]
    from server.services.saas.number_purchase_service import carrier_charge_minor
    from server.services.vobiz_client import VobizClient

    try:
        rows = await VobizClient().search_available_numbers(country="IN", limit=300)
    except Exception as exc:
        logger.warning("admin inventory pricing failed error_type=%s", type(exc).__name__)
        return {"ok": False}
    charges = []
    for row in rows:
        charge = carrier_charge_minor(row)
        if charge is not None:
            charges.append(charge)
    value = {"ok": True, "count": len(rows), "charges": charges}
    _inventory_cache.update(at=now, value=value)
    return value


async def purchases_health() -> dict:
    """Platform-level state that decides whether any tenant can buy a number."""
    from server.services.saas.billing_rates import load_current_rates
    from server.services.saas.number_purchase_service import retail_minor_for
    from server.services.telephony import active_telephony_provider, provider_configured

    provider = active_telephony_provider()
    rates = await load_current_rates()
    rent = {
        "inr": round(int(rates.get("did_monthly_inr_paise") or 0) / 100.0, 2),
        "usd": round(int(rates.get("did_monthly_usd_cents") or 0) / 100.0, 2),
    }
    alerts: list[dict] = []
    balance_info: dict | None = None
    pricing_info: dict | None = None
    configured = provider != "vobiz" or provider_configured("vobiz")

    if provider == "vobiz" and not configured:
        alerts.append(_alert("carrier_not_configured"))
    elif provider == "vobiz":
        from server.services.vobiz_client import VobizClient

        try:
            bal = await VobizClient().get_balance()
        except Exception as exc:
            bal = {"ok": False, "error": type(exc).__name__}
        if isinstance(bal, dict) and bal.get("ok") is not False and not bal.get("fallback"):
            balance_info = {"ok": True, "balance": bal.get("balance"), "currency": bal.get("currency") or "INR"}
        else:
            balance_info = {"ok": False}
        pricing = await _inventory_pricing()
        if pricing and pricing.get("ok"):
            inr = [c for c, cur in pricing["charges"] if cur == "INR"]
            retail = retail_minor_for("INR", rates) or 0
            above = [c for c in inr if c > retail]
            cheapest = min(inr) / 100.0 if inr else None
            pricing_info = {
                "ok": True,
                "inventoryCount": pricing["count"],
                "pricedCount": len(inr),
                "aboveRentCount": len(above),
                "cheapestInr": cheapest,
                "highestInr": max(inr) / 100.0 if inr else None,
                "currency": "INR",
            }
            if inr and len(above) == len(inr):
                alerts.append(_alert(
                    "carrier_price_above_retail",
                    severity="error",
                    title="Tenants cannot buy any number: rent is below every Vobiz price",
                    detail=(
                        f"Phone number rent is ₹{rent['inr']:.2f}/month but the cheapest Vobiz number costs "
                        f"₹{cheapest:.2f} (setup + first month). All {len(inr)} inventory numbers are hidden from tenants."
                    ),
                    action=f"Raise “Phone number monthly rent” to at least ₹{cheapest:.2f} in Wallet & rates.",
                ))
            elif above:
                alerts.append(_alert(
                    "carrier_price_above_retail",
                    detail=(
                        f"{len(above)} of {len(inr)} inventory numbers cost more than the ₹{rent['inr']:.2f} rent "
                        "and are hidden from tenants."
                    ),
                ))
        elif pricing is not None:
            pricing_info = {"ok": False}
            alerts.append(_alert("carrier_inventory_unavailable"))
        if balance_info.get("ok"):
            amount = float(balance_info.get("balance") or 0)
            cheapest = (pricing_info or {}).get("cheapestInr")
            needed = cheapest if cheapest is not None else None
            if needed is not None and str(balance_info.get("currency")).upper() == "INR" and amount < needed:
                alerts.append(_alert(
                    "carrier_balance_exhausted",
                    detail=(
                        f"The Vobiz balance is ₹{amount:.2f}, below the cheapest number (₹{needed:.2f} setup + first month). "
                        "Purchases are refused before tenants are charged."
                    ),
                    action=f"Top up the Vobiz account by at least ₹{needed - amount:.2f} (more to buy several numbers).",
                ))

    # Refusals and failures in the window, grouped by platform code.
    refusals = (await list_refusals(platform_only=True, limit=500))["items"]
    purchases = (await list_admin_purchases(limit=200))
    by_code: dict[str, dict] = {}
    for r in refusals:
        group = by_code.setdefault(r["code"], {"tenants": set(), "numbers": set(), "count": 0, "lastAt": None})
        group["count"] += 1
        if r.get("tenantName") or r.get("tenantId"):
            group["tenants"].add(r.get("tenantName") or r.get("tenantId"))
        if r.get("e164"):
            group["numbers"].add(r["e164"])
        group["lastAt"] = max(filter(None, [group["lastAt"], r["at"]]), default=None)
    factory = get_session_factory()
    all_rows = []
    if factory is not None:
        async with factory() as session:
            all_rows = [_serialize(*row) for row in await _load_rows(session)]
    for p in all_rows:
        issue = p.get("issue") or {}
        if issue.get("scope") == "platform" and p["status"] in {"needs_attention", "refunded", "failed"}:
            group = by_code.setdefault(issue["code"], {"tenants": set(), "numbers": set(), "count": 0, "lastAt": None})
            group["count"] += 1
            group["tenants"].add(p.get("tenantName") or p["tenantId"])
            group["numbers"].add(p["e164"])
            group["lastAt"] = max(filter(None, [group["lastAt"], p["updatedAt"]]), default=None)
    existing = {a["code"] for a in alerts}
    for code, group in by_code.items():
        affected = {
            "count": group["count"],
            "tenants": sorted(group["tenants"])[:10],
            "numbers": sorted(group["numbers"])[:10],
            "lastAt": group["lastAt"],
        }
        if code in existing:
            for a in alerts:
                if a["code"] == code:
                    a["affected"] = affected
            continue
        alert = _alert(code)
        alert["affected"] = affected
        alerts.append(alert)

    needs_attention = sum(1 for p in all_rows if p["status"] == "needs_attention")
    if needs_attention:
        refund_failed = sum(1 for p in all_rows if (p.get("issue") or {}).get("code") == "refund_failed")
        alerts.append({
            "code": "purchases_need_attention",
            "severity": "error" if refund_failed else "warning",
            "scope": "number",
            "title": f"{needs_attention} purchase{'s' if needs_attention != 1 else ''} need{'s' if needs_attention == 1 else ''} attention",
            "detail": (
                f"Tenants were charged and the number is not active yet{f'; {refund_failed} refund(s) failed' if refund_failed else ''}."
            ),
            "action": "Open each one below: retry provisioning or refund.",
            "href": None,
            "filter": "needs_attention",
        })

    order = {"error": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: order.get(a.get("severity", "info"), 3))
    return {
        "provider": provider,
        "configured": configured,
        "rent": rent,
        "carrierBalance": balance_info,
        "inventoryPricing": pricing_info,
        "alerts": alerts,
        "counts": purchases["counts"],
        "refusalsLast7Days": len(refusals),
        "checkedAt": _iso(_utcnow()),
    }


def _alert(code: str, **overrides: Any) -> dict:
    base = admin_explanation(code) or {"code": code}
    return {**base, **{k: v for k, v in overrides.items() if v is not None}}
