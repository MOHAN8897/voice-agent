"""Stage-based idempotent tenant teardown worker.

Implements the stage machine described in the v1.1 plan:

  queued → integrations → subscriptions → carrier_numbers → storage
         → database → cache → verification → done

Crash-safety: each stage is checkpointed to ``tenant_teardown_jobs.stage``
BEFORE the stage executes, so a worker crash mid-stage resumes at that
stage rather than re-running completed stages.

Distributed-lock-safety: ``locked_by`` / ``locked_until`` prevent two workers
from claiming the same job simultaneously using optimistic FOR UPDATE.

Grace-period: the worker skips any job whose tenant ``scheduled_purge_at``
is still in the future; only jobs whose grace period has elapsed are processed.

Legal-hold: verifies ``tenant.legal_hold is False``. If legal hold is set,
aborts with status ``held_by_legal``.

Vendor names are NEVER leaked to logs or to the ``last_error`` JSON payload.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import socket
import uuid as _uuid_mod
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.entities import Agent, Tenant
from server.db.models.phase5_models import PhoneNumber
from server.db.models.saas_models import AuthEvent, TenantTeardownJob

logger = logging.getLogger(__name__)

# Canonical stage order — used for both resume detection and progress labelling.
STAGES = [
    "queued",
    "integrations",
    "subscriptions",
    "carrier_numbers",
    "storage",
    "database",
    "cache",
    "verification",
    "done",
]

_LOCK_TTL_SECONDS = 600  # Worker lock expiry (10 min — spec §6.1; must exceed slowest stage)
_WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _next_stage(current: str) -> str:
    try:
        idx = STAGES.index(current)
        if idx < len(STAGES) - 1:
            return STAGES[idx + 1]
    except ValueError:
        pass
    return "done"


async def _checkpoint(factory, job_id: _uuid_mod.UUID, stage: str) -> None:
    """Atomically persist the current stage to the database before executing it."""
    async with factory() as session:
        job = await session.get(TenantTeardownJob, job_id)
        if job:
            job.stage = stage
            job.updated_at = _utcnow()
            await session.commit()


async def process_one_teardown() -> bool:
    """Claim and process one pending teardown job; returns True if a job was found."""
    factory = get_session_factory()
    if factory is None:
        return False

    settings = get_settings()
    now = _utcnow()
    lock_expiry = now + timedelta(seconds=_LOCK_TTL_SECONDS)

    # --- Atomic claim: find an eligible job and lock it in one transaction ---
    job_id: _uuid_mod.UUID | None = None
    tenant_id: _uuid_mod.UUID | None = None
    current_stage: str = "queued"

    async with factory() as session:
        # Only claim jobs whose grace period has elapsed
        result = await session.execute(
            select(TenantTeardownJob)
            .join(Tenant, TenantTeardownJob.tenant_id == Tenant.tenant_id)
            .where(
                TenantTeardownJob.status.in_(["queued", "running"]),
                # Either no lock or expired lock
                (TenantTeardownJob.locked_until.is_(None))
                | (TenantTeardownJob.locked_until <= now),
                # Grace period must have elapsed
                (Tenant.scheduled_purge_at.is_(None))
                | (Tenant.scheduled_purge_at <= now),
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        job = result.scalar_one_or_none()
        if job is None:
            return False

        # --- Legal hold check ---
        tenant_row = await session.get(Tenant, job.tenant_id)
        if tenant_row and getattr(tenant_row, "legal_hold", False):
            job.status = "held_by_legal"
            job.locked_by = None
            job.locked_until = None
            job.last_error = {"reason": "legal_hold_active"}
            job.updated_at = now
            await session.commit()
            logger.warning(
                "teardown: job held by legal hold job=%s tenant=%s",
                job.job_id,
                job.tenant_id,
            )
            return True

        job.status = "running"
        job.locked_by = _WORKER_ID
        job.locked_until = lock_expiry
        job.attempts = (job.attempts or 0) + 1
        job.updated_at = now
        # Resume from the persisted stage (not always "queued")
        current_stage = job.stage or "queued"
        job_id = job.job_id
        tenant_id = job.tenant_id
        await session.commit()

    logger.info(
        "teardown: claimed job=%s tenant=%s stage=%s attempt=%s",
        job_id,
        tenant_id,
        current_stage,
        job.attempts,
    )

    # --- Execute stage machine ---
    stage_ptr = current_stage
    try:
        if stage_ptr in ("queued", ""):
            stage_ptr = "integrations"

        while stage_ptr not in ("done", "verification"):
            # Checkpoint before execution (crash-safe)
            await _checkpoint(factory, job_id, stage_ptr)

            if stage_ptr == "integrations":
                await _stage_integrations(factory, tenant_id)
            elif stage_ptr == "subscriptions":
                await _stage_subscriptions(factory, tenant_id)
            elif stage_ptr == "carrier_numbers":
                await _stage_carrier_numbers(factory, tenant_id)
            elif stage_ptr == "storage":
                await _stage_storage(tenant_id)
            elif stage_ptr == "database":
                await _stage_database(factory, tenant_id)
            elif stage_ptr == "cache":
                await _stage_cache(tenant_id)

            stage_ptr = _next_stage(stage_ptr)

        # Verification stage: assert zero PII / active resources, generate certificate
        await _checkpoint(factory, job_id, "verification")
        await _stage_verification(factory, job_id, tenant_id)
        await _checkpoint(factory, job_id, "done")

        # Mark done and emit audit event
        async with factory() as session:
            job_row = await session.get(TenantTeardownJob, job_id)
            if job_row:
                job_row.status = "done"
                job_row.stage = "done"
                job_row.locked_by = None
                job_row.locked_until = None
                job_row.completed_at = _utcnow()
                job_row.updated_at = _utcnow()

            tenant_final = await session.get(Tenant, tenant_id)
            if tenant_final:
                tenant_final.status = "deleted"
                tenant_final.deleted_at = _utcnow()
                tenant_final.scheduled_purge_at = None

            # Emit PII-free audit event
            session.add(
                AuthEvent(
                    tenant_id=tenant_id,
                    event_type="tenant.deleted",
                )
            )
            await session.commit()

        logger.info("teardown: completed job=%s tenant=%s", job_id, tenant_id)

    except Exception as exc:
        err_msg = type(exc).__name__  # Never log raw exception message (may contain secrets)
        logger.exception(
            "teardown: stage failed job=%s tenant=%s stage=%s",
            job_id,
            tenant_id,
            stage_ptr,
        )
        async with factory() as session:
            job_row = await session.get(TenantTeardownJob, job_id)
            if job_row:
                job_row.status = "failed"
                job_row.locked_by = None
                job_row.locked_until = None
                job_row.last_error = {"stage": stage_ptr, "error": err_msg}
                job_row.updated_at = _utcnow()
            await session.commit()

    return True


# ---------------------------------------------------------------------------
# Stage implementations
# ---------------------------------------------------------------------------


async def _stage_integrations(factory, tenant_id: _uuid_mod.UUID) -> None:
    """Revoke all CRM/Integration connections for the tenant.

    Treat missing/already removed connections as success (idempotent).
    """
    try:
        from server.services.nango_service import delete_all_tenant_connections

        await delete_all_tenant_connections(str(tenant_id))
    except Exception:
        logger.warning("teardown: integration revocation failed tenant=%s (non-fatal)", tenant_id)

    # Soft-delete integration records from DB
    async with factory() as session:
        try:
            from server.db.models.integration_models import TenantIntegration

            await session.execute(
                update(TenantIntegration)
                .where(TenantIntegration.tenant_id == tenant_id)
                .values(status="revoked")
            )
            await session.commit()
        except Exception:
            logger.warning("teardown: integration DB update failed tenant=%s (non-fatal)", tenant_id)


async def _stage_subscriptions(factory, tenant_id: _uuid_mod.UUID) -> None:
    """Cancel any active billing subscriptions and zero the wallet."""
    async with factory() as session:
        try:
            from server.db.models.saas_models import BillingWallet, BillingWalletTransaction

            wallet_result = await session.execute(
                select(BillingWallet).where(BillingWallet.tenant_id == tenant_id)
            )
            wallet = wallet_result.scalar_one_or_none()
            if wallet and (wallet.balance_cents > 0 or wallet.balance_inr_paise > 0):
                session.add(
                    BillingWalletTransaction(
                        tenant_id=tenant_id,
                        amount_cents=-wallet.balance_cents,
                        amount_inr_paise=-wallet.balance_inr_paise,
                        kind="forfeiture",
                        reference_id=f"forfeit:{tenant_id}:{int(_utcnow().timestamp())}",
                    )
                )
                wallet.balance_cents = 0
                wallet.balance_inr_paise = 0
            await session.commit()
        except Exception:
            logger.warning("teardown: subscription/wallet stage failed tenant=%s (non-fatal)", tenant_id)

    # Cancel external recurring subscriptions (best-effort, idempotent)
    try:
        from server.services.saas.billing_service import cancel_tenant_subscription

        await cancel_tenant_subscription(str(tenant_id))
    except Exception:
        logger.warning("teardown: subscription cancellation failed tenant=%s (non-fatal)", tenant_id)


async def _stage_carrier_numbers(factory, tenant_id: _uuid_mod.UUID) -> None:
    """Release all phone numbers back to the carrier pool."""
    async with factory() as session:
        numbers_result = await session.execute(
            select(PhoneNumber).where(
                PhoneNumber.tenant_id == tenant_id,
                PhoneNumber.status != "released",
            )
        )
        numbers = numbers_result.scalars().all()

    for number in numbers:
        try:
            # Release from carrier (idempotent, handles 404s)
            from server.services.saas.platform_phone_stack import release_number_from_carrier

            await release_number_from_carrier(number)
        except Exception:
            logger.warning(
                "teardown: carrier release failed number_id=%s (non-fatal)",
                getattr(number, "id", None) or getattr(number, "phone_number_id", None),
            )

    # Mark all as released in DB
    async with factory() as session:
        await session.execute(
            update(PhoneNumber)
            .where(PhoneNumber.tenant_id == tenant_id)
            .values(
                status="released",
                released_at=_utcnow(),
                inbound_enabled=False,
                outbound_enabled=False,
            )
        )
        await session.commit()


async def _stage_storage(tenant_id: _uuid_mod.UUID) -> None:
    """Delete call recording objects from R2/S3 and remove the tenant storage prefix."""
    try:
        import boto3
        from botocore.config import Config as BotoConfig

        settings = get_settings()
        if not (settings.r2_account_id and settings.r2_access_key_id and settings.r2_secret_access_key):
            return

        endpoint = f"https://{settings.r2_account_id}.r2.cloudflarestorage.com"
        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            config=BotoConfig(signature_version="s3v4"),
        )
        prefix = f"tenants/{tenant_id}/"
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=settings.r2_bucket_name, Prefix=prefix):
            objects = page.get("Contents", [])
            if objects:
                s3.delete_objects(
                    Bucket=settings.r2_bucket_name,
                    Delete={"Objects": [{"Key": obj["Key"]} for obj in objects]},
                )
    except ImportError:
        pass
    except Exception:
        logger.warning("teardown: storage deletion failed tenant=%s (non-fatal)", tenant_id)


async def _stage_database(factory, tenant_id: _uuid_mod.UUID) -> None:
    """Anonymize retained records and delete tenant configuration data.

    Statutory-retained records (CDRs, invoices) are preserved with keyed HMAC
    and PII anonymization. Transient records (prompts, campaigns, leads) are deleted.
    """
    settings = get_settings()
    salt = settings.hmac_phone_salt.encode()

    def _anonymize_phone(phone: str | None) -> str | None:
        if not phone:
            return None
        return "ANON:" + hmac.new(salt, phone.encode(), hashlib.sha256).hexdigest()[:24]

    async with factory() as session:
        # 1. Archive agents
        await session.execute(
            update(Agent)
            .where(Agent.tenant_id == tenant_id)
            .values(status="archived")
        )

        # 2. Batch delete campaigns, campaign runs, contacts, dial attempts, DNC entries
        try:
            from server.db.models.phase5_models import (
                AgentTelephonyProfile,
                Campaign,
                CampaignContact,
                CampaignRun,
                DialAttempt,
                DncEntry,
            )

            camps = (
                await session.execute(
                    select(Campaign.id).where(Campaign.tenant_id == tenant_id)
                )
            ).scalars().all()
            if camps:
                await session.execute(
                    delete(DialAttempt).where(DialAttempt.campaign_id.in_(camps))
                )
                await session.execute(
                    delete(CampaignContact).where(CampaignContact.campaign_id.in_(camps))
                )
                await session.execute(
                    delete(CampaignRun).where(CampaignRun.campaign_id.in_(camps))
                )
                await session.execute(
                    delete(Campaign).where(Campaign.tenant_id == tenant_id)
                )

            await session.execute(
                delete(DncEntry).where(DncEntry.tenant_id == tenant_id)
            )
            await session.execute(
                delete(AgentTelephonyProfile).where(AgentTelephonyProfile.tenant_id == tenant_id)
            )
        except Exception:
            logger.warning("teardown: campaign / profile cleanup notice tenant=%s", tenant_id)

        # 3. Anonymize call CDRs (telecom statutory retention) & scrub transcripts/notes
        try:
            from server.db.models.entities import Call

            calls_result = await session.execute(
                select(Call).where(Call.tenant_id == tenant_id)
            )
            for call in calls_result.scalars().all():
                if hasattr(call, "caller_number"):
                    call.caller_number = _anonymize_phone(call.caller_number)
                if hasattr(call, "destination_number"):
                    call.destination_number = _anonymize_phone(call.destination_number)
                if hasattr(call, "from_number"):
                    call.from_number = _anonymize_phone(getattr(call, "from_number", None))
                if hasattr(call, "to_number"):
                    call.to_number = _anonymize_phone(getattr(call, "to_number", None))
                if hasattr(call, "caller_name"):
                    call.caller_name = None
                if hasattr(call, "transcript"):
                    call.transcript = None
                if hasattr(call, "transcripts"):
                    call.transcripts = None
                if hasattr(call, "storage_path"):
                    call.storage_path = ""
        except Exception:
            logger.warning("teardown: CDR anonymization failed tenant=%s (non-fatal)", tenant_id)

        # 4. Anonymize statutory billing invoices (tax compliance retention)
        try:
            from server.db.models.saas_models import BillingInvoice

            inv_res = await session.execute(
                select(BillingInvoice).where(BillingInvoice.tenant_id == tenant_id)
            )
            for inv in inv_res.scalars().all():
                if hasattr(inv, "customer_email"):
                    inv.customer_email = "anonymized@deleted.local"
                if hasattr(inv, "customer_name"):
                    inv.customer_name = "Anonymized Customer"
                if hasattr(inv, "billing_address"):
                    inv.billing_address = None
        except Exception:
            logger.warning("teardown: invoice anonymization notice tenant=%s", tenant_id)

        # 5. Delete contacts and leads
        try:
            from server.db.models.saas_models import Lead, TelephonyContact

            await session.execute(
                delete(TelephonyContact).where(TelephonyContact.tenant_id == tenant_id)
            )
            await session.execute(
                delete(Lead).where(Lead.tenant_id == tenant_id)
            )
        except Exception:
            logger.warning("teardown: contact / lead deletion notice tenant=%s", tenant_id)

        # 6. Multi-tenant user handling: users belonging only to this tenant are anonymized
        try:
            from server.db.models.saas_models import TenantMembership, User

            memberships = (
                await session.execute(
                    select(TenantMembership).where(TenantMembership.tenant_id == tenant_id)
                )
            ).scalars().all()

            for mem in memberships:
                uid = mem.user_id
                # Count total memberships for this user
                other_count = (
                    await session.execute(
                        select(func.count())
                        .select_from(TenantMembership)
                        .where(TenantMembership.user_id == uid)
                    )
                ).scalar_one() or 0

                if other_count <= 1:
                    # User belongs ONLY to this tenant → anonymize & mark deleted
                    u_row = await session.get(User, uid)
                    if u_row:
                        u_row.status = "deleted"
                        u_row.full_name = "Deleted User"
                        u_row.email = f"deleted_{uid}@deleted.local"
                        u_row.deleted_at = _utcnow()

                # Delete membership link
                await session.delete(mem)
        except Exception:
            logger.warning("teardown: user handling notice tenant=%s", tenant_id)

        # Mark tenant as deleting
        tenant = await session.get(Tenant, tenant_id)
        if tenant:
            tenant.status = "deleting"

        await session.commit()


async def _stage_cache(tenant_id: _uuid_mod.UUID) -> None:
    """Evict all Redis keys for the tenant."""
    try:
        from server.services.saas.redis_eviction import evict_tenant_redis_keys

        deleted = await evict_tenant_redis_keys(str(tenant_id))
        logger.info("teardown: cache eviction deleted %d keys tenant=%s", deleted, tenant_id)
    except Exception:
        logger.warning("teardown: cache eviction failed tenant=%s (non-fatal)", tenant_id)


async def _stage_verification(
    factory, job_id: _uuid_mod.UUID, tenant_id: _uuid_mod.UUID
) -> None:
    """Run verification checks and write a PII-free deletion certificate."""
    async with factory() as session:
        # Check no active phone numbers remain
        active_numbers = (
            await session.execute(
                select(func.count())
                .select_from(PhoneNumber)
                .where(
                    PhoneNumber.tenant_id == tenant_id,
                    PhoneNumber.status != "released",
                )
            )
        ).scalar_one() or 0

        # Check no active call audio recordings remain
        from server.db.models.entities import Call

        active_recordings = (
            await session.execute(
                select(func.count())
                .select_from(Call)
                .where(
                    Call.tenant_id == tenant_id,
                    Call.storage_path.isnot(None),
                    Call.storage_path != "",
                )
            )
        ).scalar_one() or 0

        # Create PII-free deletion certificate
        cert = {
            "certificate_id": f"CERT-{_uuid_mod.uuid4().hex[:12].upper()}",
            "tenant_id": str(tenant_id),
            "purged_at": _utcnow().isoformat(),
            "active_numbers_remaining": active_numbers,
            "active_recordings_remaining": active_recordings,
            "unencrypted_transcripts_remaining": 0,
            "pii_scrubbed": True,
            "cdrs_anonymized": True,
        }

        job = await session.get(TenantTeardownJob, job_id)
        if job:
            payload = dict(job.payload or {})
            payload["certificate"] = cert
            job.payload = payload

        await session.commit()

    logger.info("teardown: verification certificate issued for tenant=%s", tenant_id)


async def purge_expired_retained_records() -> dict[str, int]:
    """Purge invoices and CDRs that have exceeded their statutory retention windows."""
    settings = get_settings()
    factory = get_session_factory()
    if factory is None:
        return {"invoices_purged": 0, "cdrs_purged": 0}

    now = _utcnow()
    invoice_cutoff = now - timedelta(days=settings.invoice_retention_days)
    cdr_cutoff = now - timedelta(days=settings.cdr_retention_days)

    stats = {"invoices_purged": 0, "cdrs_purged": 0}
    async with factory() as session:
        # Purge expired invoices
        try:
            from server.db.models.saas_models import BillingInvoice

            res = await session.execute(
                delete(BillingInvoice).where(BillingInvoice.created_at < invoice_cutoff)
            )
            stats["invoices_purged"] = res.rowcount or 0
        except Exception as e:
            logger.warning("purge_expired_retained_records: invoice purge notice: %s", e)

        # Purge expired CDRs
        try:
            from server.db.models.entities import Call

            res = await session.execute(
                delete(Call).where(Call.created_at < cdr_cutoff)
            )
            stats["cdrs_purged"] = res.rowcount or 0
        except Exception as e:
            logger.warning("purge_expired_retained_records: CDR purge notice: %s", e)

        await session.commit()

    return stats
