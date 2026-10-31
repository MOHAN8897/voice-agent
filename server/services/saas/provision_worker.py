"""Durable carrier provisioning after a committed purchase."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from server.db.connection import get_session_factory
from server.db.models.phase5_models import PhoneNumber
from server.db.models.saas_models import (
    NumberPurchase,
    NumberReservation,
    ProvisionJob,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _queued_job_statement():
    return (
        select(ProvisionJob)
        .where(ProvisionJob.status == "queued", ProvisionJob.updated_at <= _utcnow())
        .order_by(ProvisionJob.created_at, ProvisionJob.job_id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )


def _provider_number_id(result: object) -> str | None:
    """Return only an identifier supplied by the carrier response."""
    if not isinstance(result, dict):
        return None
    value = result.get("phone_number_id")
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _phone_number_status(provider_number_id: str | None) -> str:
    """Do not expose a carrier order without a real resource ID as active."""
    return "active" if provider_number_id else "pending"


#: Number upkeep (carrier release reconciliation, monthly rental renewal) runs
#: from the provision worker's idle path at most this often per process.
_MAINTENANCE_INTERVAL_SECONDS = 600
_last_maintenance_at: float | None = None


async def run_number_maintenance_if_due() -> bool:
    """Finalise carrier releases and charge due rentals; throttled, never raises."""
    import time

    global _last_maintenance_at
    now = time.monotonic()
    if _last_maintenance_at is not None and now - _last_maintenance_at < _MAINTENANCE_INTERVAL_SECONDS:
        return False
    _last_maintenance_at = now
    try:
        from server.services.saas.number_inventory import reconcile_release_pending_numbers

        await reconcile_release_pending_numbers()
    except Exception as exc:
        logger.warning("number release reconcile failed error_type=%s", type(exc).__name__)
    try:
        from server.services.saas.number_rental import renew_due_numbers

        await renew_due_numbers()
    except Exception as exc:
        logger.warning("number rental renewal failed error_type=%s", type(exc).__name__)
    return True


#: Vobiz's documented body for a purchase whose balance debit failed (HTTP 500).
#: The number stays in inventory, so once ``place_number_order`` has reconciled
#: and found it not owned, the order definitely did not happen.
_VOBIZ_PURCHASE_FAILED_MARKER = "failed to purchase number"
#: Attempts before a documented purchase refusal is treated as final and refunded.
_PURCHASE_REFUSED_MAX_ATTEMPTS = 3


async def _diagnose_vobiz_purchase_refusal(purchase) -> tuple[str, dict]:
    """Read-only: is the parent balance below this number's carrier price?"""
    from server.services.saas.number_purchase_service import (
        CARRIER_MIN_BALANCE_USD,
        _carrier_remaining,
        carrier_charge_minor,
    )
    from server.services.vobiz_client import VobizClient

    context: dict = {}
    try:
        client = VobizClient()
        balance = await client.get_balance()
        if not isinstance(balance, dict) or balance.get("ok") is False or balance.get("fallback"):
            return "carrier_purchase_refused", context
        remaining = _carrier_remaining(balance)
        currency = str(balance.get("currency") or "INR").upper()
        if remaining is None:
            return "carrier_purchase_refused", context
        context = {"carrierBalance": round(remaining, 2), "currency": currency}
        required = None
        try:
            rows = await client.search_available_numbers(
                country=str(purchase.country_code or "IN"), limit=25, search=purchase.e164
            )
            row = next((r for r in rows if str(r.get("e164") or "") == purchase.e164), None)
            charge = carrier_charge_minor(row) if row else None
            if charge is not None and charge[1] == currency:
                required = charge[0] / 100.0
        except Exception:
            required = None
        if required is None:
            required = CARRIER_MIN_BALANCE_USD * (96.78 if currency == "INR" else 1.0)
        context["carrierRequired"] = round(required, 2)
        if remaining < required:
            return "carrier_balance_exhausted", context
    except Exception as exc:
        logger.warning("vobiz refusal diagnosis failed error_type=%s", type(exc).__name__)
    return "carrier_purchase_refused", context


async def _classify_provision_failure(
    provider: str,
    exc: Exception,
    provider_status: int | None,
    provider_number_id: str | None,
    purchase,
) -> tuple[str | None, dict, bool]:
    """(code, operator context, definitive) for a provisioning exception.

    ``definitive`` means the carrier certainly did not sell us the number, so the
    purchase can fail and refund now. Anything that might have created the number
    is left to the reconcile-and-retry path.
    """
    if provider != "vobiz" or provider_number_id is not None or purchase is None:
        return None, {}, False
    detail = getattr(exc, "detail", None)
    detail_code = None
    if isinstance(detail, dict):
        detail_code = str((detail.get("error") or {}).get("code") or "") or None
    elif isinstance(detail, str):
        detail_code = detail
    if detail_code == "voice_kyc_required" or getattr(exc, "code", None) == "voice_kyc_required":
        return "voice_kyc_not_approved", {}, True
    if type(exc).__name__ != "VobizApiError":
        return None, {}, False
    if provider_status == 404:
        # Documented: "number not found in inventory" — someone else bought it.
        return "number_taken", {}, True
    if provider_status in (401, 403):
        return "carrier_auth_failed", {"providerStatus": provider_status}, True
    body = str(getattr(exc, "body", "") or "").lower()
    if provider_status == 500 and _VOBIZ_PURCHASE_FAILED_MARKER in body:
        code, context = await _diagnose_vobiz_purchase_refusal(purchase)
        if code == "carrier_balance_exhausted":
            # Retrying cannot succeed until someone tops up the parent account.
            return code, context, True
        attempts = 0
        factory = get_session_factory()
        if factory is not None:
            async with factory() as session:
                job = (
                    await session.execute(
                        select(ProvisionJob).where(ProvisionJob.purchase_id == purchase.id)
                    )
                ).scalar_one_or_none()
                attempts = int(job.attempts or 0) if job is not None else 0
        return code, context, attempts >= _PURCHASE_REFUSED_MAX_ATTEMPTS
    return None, {}, False


async def enqueue_provision(purchase_id: uuid.UUID) -> None:
    factory = get_session_factory()
    if factory is None:
        return
    async with factory() as session:
        existing = await session.execute(
            select(ProvisionJob).where(ProvisionJob.purchase_id == purchase_id)
        )
        if existing.scalar_one_or_none():
            return
        session.add(
            ProvisionJob(
                purchase_id=purchase_id,
                status="queued",
                attempts=0,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
        )
        await session.commit()


async def process_one_job() -> bool:
    """Returns True if a job was processed."""
    factory = get_session_factory()
    if factory is None:
        return False
    async with factory() as session:
        stale = (await session.execute(select(ProvisionJob).where(
            ProvisionJob.status == "running", ProvisionJob.updated_at < _utcnow() - timedelta(minutes=10),
        ).with_for_update(skip_locked=True).limit(20))).scalars().all()
        for abandoned in stale:
            abandoned.status = "queued" if abandoned.attempts < 5 else "needs_attention"
            abandoned.updated_at = _utcnow()
            purchase = await session.get(NumberPurchase, abandoned.purchase_id, with_for_update=True)
            if purchase and abandoned.status == "needs_attention":
                purchase.status = "needs_attention"
        await session.commit()
        result = await session.execute(
            _queued_job_statement()
        )
        job = result.scalar_one_or_none()
        purchase_id = None
        if job is not None:
            # Claimed under FOR UPDATE SKIP LOCKED in this same transaction.
            job.status = "running"
            job.attempts += 1
            job.updated_at = _utcnow()
            purchase_id = job.purchase_id
        await session.commit()
    if purchase_id is None:
        await run_number_maintenance_if_due()
        return False

    async with factory() as session:
        purchase = await session.get(NumberPurchase, purchase_id)
        job = await session.execute(select(ProvisionJob).where(ProvisionJob.purchase_id == purchase_id))
        job_row = job.scalar_one()
        if purchase is None:
            job_row.status = "failed"
            job_row.last_error = {"message": "purchase_missing"}
            await session.commit()
            return True
        # Never interpret a paid job using the currently selected provider.
        provider = str(purchase.provider or "")
        if provider not in {"vobiz", "telnyx"}:
            job_row.status = purchase.status = "needs_attention"
            job_row.last_error = {"code": "purchase_provider_unknown"}
            await session.commit()
            return True
        if purchase.status == "active" and purchase.phone_number_id:
            job_row.status = "done"
            await session.commit()
            return True
        provider_number_id = purchase.carrier_number_id
        purchase.status = "provisioning"
        await session.commit()

    async with factory() as session:
        purchase = await session.get(NumberPurchase, purchase_id)
    if purchase is None:
        return True
    phone_number_status = "pending"
    try:
        if provider == "vobiz":
            from server.services.saas.voice_kyc_service import provision_tenant_number

            # The child reconciles its own numbers before POSTing. A crash after
            # purchase is recovered with the same tenant credentials and DID.
            result = await provision_tenant_number(purchase.tenant_id, purchase.e164)
            confirmed_id = _provider_number_id(result)
            if provider_number_id and confirmed_id != provider_number_id:
                raise RuntimeError("provider_number_id_conflict")
            provider_number_id = confirmed_id
            async with factory() as session:
                checkpoint = await session.get(NumberPurchase, purchase_id, with_for_update=True)
                checkpoint.carrier_number_id = provider_number_id
                await session.commit()
        elif provider == "telnyx":
            from server.services.telnyx_client import TelnyxClient
            from server.services.telnyx_provisioning import provision_ordered_number

            client = TelnyxClient()
            result = await provision_ordered_number(client, purchase.e164)
        else:
            raise RuntimeError("purchase_provider_not_supported")
        provider_number_id = _provider_number_id(result)
        phone_number_status = _phone_number_status(provider_number_id)
    except Exception as e:
        logger.warning(
            "provision failed purchase=%s error_type=%s",
            purchase_id,
            type(e).__name__,
        )
        provider_status = getattr(e, "status", None)
        if provider_status is None:
            # Our own gates (KYC revoked → 403, verification unavailable → 503)
            # raise HTTPException / VoiceKycError with ``status_code``. A
            # definitive 4xx refusal before any carrier call must refund, not
            # park the paid purchase in "needs_attention" forever.
            provider_status = getattr(e, "status_code", None)
        failure_code, failure_context, definitive = await _classify_provision_failure(
            provider, e, provider_status, provider_number_id, purchase
        )
        vobiz_result_may_exist = (
            not definitive
            and provider == "vobiz"
            and (
                provider_number_id is not None
                or provider_status is None
                or provider_status >= 500
                or provider_status in {408, 409, 429}
            )
        )
        if vobiz_result_may_exist:
            async with factory() as session:
                purchase = await session.get(NumberPurchase, purchase_id, with_for_update=True)
                job = (
                    await session.execute(
                        select(ProvisionJob).where(ProvisionJob.purchase_id == purchase_id)
                    )
                ).scalar_one()
                retry = job.attempts < 5
                job.status = "queued" if retry else "needs_attention"
                job.last_error = {
                    "code": failure_code
                    or (
                        "provider_confirmation_pending"
                        if provider_number_id is None
                        else "provider_activation_pending"
                    ),
                    "error_type": type(e).__name__,
                    **({"providerStatus": provider_status} if provider_status is not None else {}),
                    **({"context": failure_context} if failure_context else {}),
                }
                job.updated_at = (
                    _utcnow() + timedelta(seconds=min(300, 10 * (2 ** max(0, job.attempts - 1))))
                    if retry
                    else _utcnow()
                )
                if purchase is not None:
                    purchase.status = "provisioning" if retry else "needs_attention"
                    if provider_number_id:
                        purchase.carrier_number_id = provider_number_id
                    purchase.updated_at = _utcnow()
                await session.commit()
            if not retry and purchase is not None:
                from server.services.saas.activity_log import record_event

                await record_event(
                    action="number.provision.needs_attention",
                    resource_type="number_purchase",
                    resource_id=str(purchase_id),
                    actor="system",
                    tenant_id=purchase.tenant_id,
                    payload={
                        "errorType": type(e).__name__,
                        "provider": "vobiz",
                        "code": job.last_error.get("code") if isinstance(job.last_error, dict) else None,
                        "e164": purchase.e164,
                    },
                    source="system",
                    outcome="warning",
                    severity="warning",
                )
            return True

        refund_tenant = None
        refund_user = None
        refund_wallet = False
        async with factory() as session:
            purchase = await session.get(NumberPurchase, purchase_id)
            job = (
                await session.execute(select(ProvisionJob).where(ProvisionJob.purchase_id == purchase_id))
            ).scalar_one()
            job.status = "failed"
            job.last_error = {
                "code": failure_code or "provider_provision_failed",
                "error_type": type(e).__name__,
                **({"providerStatus": provider_status} if provider_status is not None else {}),
                **({"context": failure_context} if failure_context else {}),
            }
            if purchase:
                purchase.status = "failed"
                refund_tenant = purchase.tenant_id
                refund_user = purchase.user_id
                refund_wallet = not purchase.stripe_checkout_session_id
                # Release the hold. The number was never bought, so leaving a
                # reservation would make it look reserved by "another checkout"
                # for the rest of the TTL — and the unique index would block the
                # retry outright.
                await session.execute(
                    delete(NumberReservation).where(
                        NumberReservation.purchase_id == purchase_id
                    )
                )
            await session.commit()
        refunded = False  # initialised before the try so the audit log never hits NameError
        if refund_wallet and refund_tenant is not None:
            try:
                from server.services.saas.billing_wallet_service import refund_did_purchase

                await refund_did_purchase(
                    refund_tenant,
                    user_id=refund_user,
                    purchase_id=purchase_id,
                )
                refunded = True
            except Exception:
                logger.warning("did refund failed purchase=%s", purchase_id)
            # The admin panel reads the refund outcome off the job, so a failed
            # refund is visible next to the failure that caused it.
            try:
                async with factory() as session:
                    job = (
                        await session.execute(
                            select(ProvisionJob).where(ProvisionJob.purchase_id == purchase_id)
                        )
                    ).scalar_one_or_none()
                    if job is not None:
                        job.last_error = {
                            **(job.last_error if isinstance(job.last_error, dict) else {}),
                            "refund": "done" if refunded else "failed",
                        }
                        await session.commit()
            except Exception:
                logger.warning("could not record refund outcome purchase=%s", purchase_id)
        # The single most important row in the log: money was taken and then
        # returned, or was taken and could not be returned. Either way the
        # operator has to be able to find it without reconstructing the job.
        from server.services.saas.activity_log import record_event

        await record_event(
            action="number.provision.failed",
            resource_type="number_purchase",
            resource_id=str(purchase_id),
            actor="system",
            tenant_id=refund_tenant,
            payload={
                "errorType": type(e).__name__,
                "code": failure_code or "provider_provision_failed",
                "providerStatus": provider_status,
                "context": failure_context or None,
                "e164": purchase.e164 if purchase is not None else None,
                "refunded": refunded if refund_wallet else False,
                "refundAttempted": refund_wallet,
            },
            source="system",
            outcome="error",
            severity="error",
        )
        return True

    async with factory() as session:
        purchase = await session.get(NumberPurchase, purchase_id, with_for_update=True)
        job = (
            await session.execute(select(ProvisionJob).where(ProvisionJob.purchase_id == purchase_id))
        ).scalar_one()
        if purchase is None:
            return True
        if purchase.phone_number_id:
            job.status = "done"
            await session.commit()
            return True
        phone_tenant_id = purchase.tenant_id
        if purchase.user_id:
            from server.db.models.saas_models import User
            from server.services.saas.dev_tester_workspace import workspace_tenant_id_for_subscriber

            user = await session.get(User, purchase.user_id)
            if user:
                phone_tenant_id = workspace_tenant_id_for_subscriber(purchase.tenant_id, user.email)
        pn = PhoneNumber(
            tenant_id=phone_tenant_id,
            e164=purchase.e164,
            status=phone_number_status,
            purchase_id=purchase.id,
            billing_source="wallet" if not purchase.stripe_checkout_session_id else "stripe",
            inbound_enabled=True,
            outbound_enabled=True,
            agent_id=purchase.assign_agent_id,
            carrier_number_id=provider_number_id if provider == "vobiz" else None,
            vobiz_account_scope="tenant" if provider == "vobiz" else None,
            vobiz_account_tenant_id=purchase.tenant_id if provider == "vobiz" else None,
            telnyx_number_id=provider_number_id if provider == "telnyx" else None,
            created_at=_utcnow(),
        )
        session.add(pn)
        await session.flush()
        purchase.phone_number_id = pn.id
        purchase.status = "active" if phone_number_status == "active" else "provisioning"
        job.status = "done" if phone_number_status == "active" else "failed"
        job.last_error = (
            None
            if phone_number_status == "active"
            else {"code": "provider_number_id_unavailable"}
        )
        job.updated_at = _utcnow()
        # The number is now owned, so the in-flight hold has done its job. Leaving
        # it would collide with the unique index on the next purchase of any
        # number, and read as a false "reserved by another checkout".
        await session.execute(
            delete(NumberReservation).where(
                NumberReservation.purchase_id == purchase_id
            )
        )
        await session.commit()

    from server.services.saas.activity_log import record_event

    await record_event(
        action=(
            "number.provision.done"
            if phone_number_status == "active"
            else "number.provision.awaiting_provider_id"
        ),
        resource_type="phone_number",
        resource_id=str(pn.id),
        actor="system",
        tenant_id=phone_tenant_id,
        payload={
            "purchaseId": str(purchase_id),
            "assignedAgentId": purchase.assign_agent_id,
        },
        source="system",
        outcome="success" if phone_number_status == "active" else "warning",
        severity="info" if phone_number_status == "active" else "warning",
    )
    return True
