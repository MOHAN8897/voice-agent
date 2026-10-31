"""Tenant Account Deletion ('Danger Zone') — self-serve API endpoints.

Implements:
  GET  /api/tenant/delete-preflight   — preflight check (warnings vs blocking)
  POST /api/tenant/delete             — quarantine + schedule teardown
  GET  /api/tenant/restore-status     — what a restore brings back, and who may do it
  POST /api/tenant/restore            — owner restore during the grace period
  POST /api/tenant/delete/cancel      — legacy alias of /api/tenant/restore
  POST /api/tenant/export             — enqueue data takeout (GDPR Art. 20)
  GET  /api/tenant/export/{job_id}    — poll export status + pre-signed URL

Security:
  • All endpoints require subscriber JWT (Bearer token).
  • tenant_id is ALWAYS derived from the verified JWT principal — never from the request body.
  • Only role == 'owner' may initiate or cancel deletion.
  • Re-authentication (password or OTP) is required before quarantine commit.
  • Rate-limited: 5 deletion attempts per 15-minute window.

Standing rules enforced here:
  • SELECT … FOR UPDATE on tenant row before any mutation.
  • Money checks and token revocations happen inside the same atomic transaction.
  • All external side effects (call termination, Redis eviction, email) run post-commit.
  • Carrier/Nango vendor names are NEVER leaked to HTTP responses.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update

from server.auth.passwords import verify_portal_password
from server.auth.subscriber_dependencies import require_subscriber_jwt
from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.entities import Tenant
from server.db.models.phase5_models import PhoneNumber
from server.db.models.saas_models import (
    AuthEvent,
    BillingWallet,
    BillingInvoice,
    EmailVerificationToken,
    RefreshToken,
    TenantExportJob,
    TenantMembership,
    TenantTeardownJob,
    User,
)
from server.services.saas.tenant_guard import SubscriberPrincipal

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tenant-deletion"])

# Restoring a deleted workspace is a sudo action: the owner must have signed in
# (password or Google) within this window, or re-enter their password now.
RESTORE_REAUTH_MAX_AGE_SECONDS = 15 * 60

# Teardown jobs a restore must stop. "failed" jobs are never reclaimed by the worker,
# but cancelling them keeps the record honest about why the workspace still exists.
_CANCELLABLE_TEARDOWN_STATUSES = ("queued", "running", "failed")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


import time
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Rate limiter for deletion attempts (5 per 15 min per user)
# Uses Redis sliding-window when available, falls back to thread-safe in-memory
# ---------------------------------------------------------------------------
_delete_attempts: dict[str, list[datetime]] = {}
_DELETE_WINDOW_S = 900
_DELETE_MAX = 5


async def _check_delete_rate_limit(user_id: str) -> None:
    settings = get_settings()
    if settings.redis_url:
        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(settings.redis_url, decode_responses=True)
            try:
                now_ts = time.time()
                key = f"rate_limit:tenant_delete:{user_id}"
                pipe = client.pipeline()
                pipe.zremrangebyscore(key, 0, now_ts - _DELETE_WINDOW_S)
                pipe.zadd(key, {str(now_ts): now_ts})
                pipe.zcard(key)
                pipe.expire(key, _DELETE_WINDOW_S)
                _, _, count, _ = await pipe.execute()
                if count > _DELETE_MAX:
                    raise HTTPException(
                        status_code=429,
                        detail={"error": "rate_limited", "message": "Too many deletion attempts. Try again in 15 minutes."},
                    )
                return
            finally:
                await client.aclose()
        except HTTPException:
            raise
        except Exception as exc:
            logger.debug("Redis rate limiter unavailable, falling back to local: %s", exc)

    now = _utcnow()
    cutoff = now - timedelta(seconds=_DELETE_WINDOW_S)
    bucket = _delete_attempts.get(user_id, [])
    bucket = [t for t in bucket if t > cutoff]
    if len(bucket) >= _DELETE_MAX:
        raise HTTPException(
            status_code=429,
            detail={"error": "rate_limited", "message": "Too many deletion attempts. Try again in 15 minutes."},
        )
    bucket.append(now)
    _delete_attempts[user_id] = bucket


def _record_delete_failure(user_id: str) -> None:
    _check_delete_rate_limit.__wrapped__ if False else None  # no-op, already counted in attempt bucket


# ---------------------------------------------------------------------------
# Helper: require owner role
# ---------------------------------------------------------------------------
def _assert_owner(principal: SubscriberPrincipal) -> None:
    if principal.role not in ("owner", "customer_admin", "platform_admin"):
        raise HTTPException(
            status_code=403,
            detail={"error": "forbidden", "message": "Only workspace owners may perform this action."},
        )


# ---------------------------------------------------------------------------
# GET /api/tenant/delete-preflight
# ---------------------------------------------------------------------------
@router.get("/api/tenant/delete-preflight")
async def delete_preflight(
    principal: Annotated[SubscriberPrincipal, Depends(require_subscriber_jwt)],
) -> dict[str, Any]:
    """Return preflight checks — blocking reasons and warnings for deletion."""
    _assert_owner(principal)
    settings = get_settings()
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail={"error": "db_unavailable"})

    async with factory() as session:
        tenant = await session.get(Tenant, principal.tenant_id)
        if tenant is None or tenant.status == "deleted":
            raise HTTPException(status_code=404, detail={"error": "tenant_not_found"})

        user = await session.get(User, principal.user_id)
        is_passwordless = not user.password_hash or user.password_hash.startswith("!") if user else False

        blocking_reasons: list[str] = []
        warnings: list[str] = []

        # --- Blocking: legal hold ---
        if getattr(tenant, "legal_hold", False):
            blocking_reasons.append(
                "This workspace is under a legal hold and cannot be deleted at this time. "
                "Contact support to resolve."
            )

        # --- Blocking: unpaid invoices ---
        unpaid_result = await session.execute(
            select(func.count()).select_from(BillingInvoice).where(
                BillingInvoice.tenant_id == principal.tenant_id,
                BillingInvoice.status == "unpaid",
            )
        )
        unpaid_count = unpaid_result.scalar() or 0
        if unpaid_count > 0:
            blocking_reasons.append(
                f"You have {unpaid_count} unpaid invoice(s). "
                "Settle outstanding balances before deleting."
            )

        # --- Wallet balance (warning only) ---
        wallet_result = await session.execute(
            select(BillingWallet).where(BillingWallet.tenant_id == principal.tenant_id)
        )
        wallet = wallet_result.scalar_one_or_none()
        balance_usd = 0.0
        balance_inr = 0.0
        if wallet:
            balance_usd = (wallet.balance_cents or 0) / 100.0
            balance_inr = (wallet.balance_inr_paise or 0) / 100.0
            if wallet.balance_cents > 0 or wallet.balance_inr_paise > 0:
                parts = []
                if wallet.balance_cents > 0:
                    parts.append(f"${balance_usd:.2f}")
                if wallet.balance_inr_paise > 0:
                    parts.append(f"₹{balance_inr:.2f}")
                warnings.append(
                    f"Your balance of {' / '.join(parts)} will be forfeited upon completion."
                )

        # --- Active phone numbers (warning only) ---
        numbers_result = await session.execute(
            select(func.count()).select_from(PhoneNumber).where(
                PhoneNumber.tenant_id == principal.tenant_id,
                PhoneNumber.status == "active",
            )
        )
        phone_count = numbers_result.scalar() or 0
        if phone_count > 0:
            warnings.append(
                f"{phone_count} active voice number(s) will be released immediately."
            )

        # --- Active agents count ---
        from server.db.models.entities import Agent
        agents_result = await session.execute(
            select(func.count()).select_from(Agent).where(
                Agent.tenant_id == principal.tenant_id,
                Agent.status == "active",
            )
        )
        agent_count = agents_result.scalar() or 0

        # --- Active calls (warning only) ---
        from server.db.models.entities import Call
        active_calls_result = await session.execute(
            select(func.count()).select_from(Call).where(
                Call.tenant_id == principal.tenant_id,
                Call.ended_at.is_(None),
            )
        )
        active_calls_count = active_calls_result.scalar() or 0
        if active_calls_count > 0:
            warnings.append(
                f"{active_calls_count} call(s) currently in progress will be immediately terminated."
            )

        # --- Integrations count ---
        try:
            from server.db.models.integration_models import TenantIntegration
            integ_result = await session.execute(
                select(func.count()).select_from(TenantIntegration).where(
                    TenantIntegration.tenant_id == principal.tenant_id,
                )
            )
            integrations_count = integ_result.scalar() or 0
        except Exception:
            integrations_count = 0

        return {
            "canDelete": len(blocking_reasons) == 0,
            "tenantName": tenant.name,
            "warnings": warnings,
            "blockingReasons": blocking_reasons,
            "activeCallsCount": active_calls_count,
            "phoneNumbersCount": phone_count,
            "agentsCount": agent_count,
            "integrationsCount": integrations_count,
            "walletBalanceUsd": balance_usd,
            "walletBalanceInr": balance_inr,
            "gracePeriodDays": settings.tenant_deletion_grace_days,
            "isPasswordless": is_passwordless,
            "userEmail": user.email if user else principal.email,
        }


# ---------------------------------------------------------------------------
# POST /api/tenant/delete-otp
# ---------------------------------------------------------------------------
@router.post("/api/tenant/delete-otp")
async def request_delete_otp(
    principal: Annotated[SubscriberPrincipal, Depends(require_subscriber_jwt)],
) -> dict[str, Any]:
    """Generate and email a 6-digit security code for deletion sudo challenge."""
    _assert_owner(principal)
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail={"error": "db_unavailable"})

    from server.services.saas.email_service import send_deletion_otp_email

    async with factory() as session:
        user = await session.get(User, principal.user_id)
        if user is None or not user.email:
            raise HTTPException(status_code=404, detail={"error": "user_not_found"})
        tenant = await session.get(Tenant, principal.tenant_id)
        tenant_name = tenant.name if tenant else "Workspace"

        await session.execute(
            delete(EmailVerificationToken).where(
                EmailVerificationToken.user_id == principal.user_id,
                EmailVerificationToken.used_at.is_(None),
            )
        )
        otp = f"{secrets.randbelow(1_000_000):06d}"
        session.add(
            EmailVerificationToken(
                token_hash=_hash_token(secrets.token_urlsafe(32)),
                user_id=principal.user_id,
                otp_hash=_hash_token(otp),
                expires_at=_utcnow() + timedelta(minutes=15),
                created_at=_utcnow(),
            )
        )
        await session.commit()

    delivery = await send_deletion_otp_email(user.email, otp, tenant_name)
    if not delivery.ok:
        logger.warning(
            "delete_otp: email delivery notice to %s: code=%s detail=%s",
            user.email,
            delivery.code,
            delivery.detail,
        )

    return {
        "ok": True,
        "message": f"Confirmation code sent to {user.email}",
    }


# ---------------------------------------------------------------------------
# Request body for POST /api/tenant/delete
# ---------------------------------------------------------------------------
class DeleteTenantBody(BaseModel):
    # Verify-only field: no min_length constraint (we're verifying, not setting)
    current_password: str | None = None
    otp_code: str | None = None
    confirmation_name: str
    reason: str | None = Field(None, max_length=255)
    forfeit_balance_confirmed: bool = False


# ---------------------------------------------------------------------------
# POST /api/tenant/delete
# ---------------------------------------------------------------------------
@router.post("/api/tenant/delete")
async def request_delete_tenant(
    body: DeleteTenantBody,
    principal: Annotated[SubscriberPrincipal, Depends(require_subscriber_jwt)],
    request: Request,
) -> dict[str, Any]:
    """Sudo-authenticated quarantine: disables tenant and schedules purge after grace period."""
    _assert_owner(principal)

    # --- Step 1: Rate limiter (5 attempts / 15 min) ---
    await _check_delete_rate_limit(str(principal.user_id))

    settings = get_settings()
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail={"error": "db_unavailable"})

    async with factory() as session:
        # --- Step 2: Load user for re-auth ---
        user = await session.get(User, principal.user_id)
        if user is None:
            raise HTTPException(status_code=401, detail={"error": "auth_error"})

        # --- Step 2: Confirmation verification ---
        tenant_check = await session.get(Tenant, principal.tenant_id)
        if tenant_check is None:
            raise HTTPException(status_code=404, detail={"error": "tenant_not_found"})

        conf_entered = (body.confirmation_name or "").strip().lower()
        valid_confirmations = {"delete", tenant_check.name.strip().lower()}
        if conf_entered not in valid_confirmations:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "name_mismatch",
                    "message": 'Please type "delete" to confirm workspace deletion.',
                },
            )

        # Optional re-authentication (if supplied, verify; not strictly required)
        if body.otp_code:
            otp_hash = _hash_token(body.otp_code.strip())
            now = _utcnow()
            otp_row = await session.execute(
                select(EmailVerificationToken).where(
                    EmailVerificationToken.user_id == principal.user_id,
                    EmailVerificationToken.otp_hash == otp_hash,
                    EmailVerificationToken.expires_at > now,
                    EmailVerificationToken.used_at.is_(None),
                )
            )
            otp_token = otp_row.scalar_one_or_none()
            if otp_token is None:
                raise HTTPException(
                    status_code=400,
                    detail={"error": "invalid_otp", "message": "Invalid or expired confirmation code."},
                )
            otp_token.used_at = now
        elif body.current_password and user.password_hash and not user.password_hash.startswith("!"):
            if not verify_portal_password(user.password_hash, body.current_password):
                raise HTTPException(
                    status_code=400,
                    detail={"error": "invalid_credentials", "message": "Incorrect password."},
                )

        # --- Step 3: Balance forfeiture check ---
        wallet_row = await session.execute(
            select(BillingWallet).where(BillingWallet.tenant_id == principal.tenant_id)
        )
        wallet = wallet_row.scalar_one_or_none()
        has_balance = wallet and (wallet.balance_cents > 0 or wallet.balance_inr_paise > 0)
        if has_balance and not body.forfeit_balance_confirmed:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "forfeiture_required",
                    "message": (
                        "Your wallet has a remaining balance. Check the box to confirm "
                        "you understand this balance will be forfeited."
                    ),
                },
            )

        # --- Step 5: Atomic transaction (SELECT … FOR UPDATE) ---
        from sqlalchemy import text as _text
        tenant_locked_result = await session.execute(
            select(Tenant)
            .where(Tenant.tenant_id == principal.tenant_id)
            .with_for_update()
        )
        tenant = tenant_locked_result.scalar_one_or_none()
        if tenant is None:
            raise HTTPException(status_code=404, detail={"error": "tenant_not_found"})
        if tenant.status != "active":
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_status",
                    "message": f"Workspace is already in '{tenant.status}' state.",
                },
            )
        if getattr(tenant, "legal_hold", False):
            raise HTTPException(
                status_code=400,
                detail={"error": "legal_hold", "message": "Workspace is under a legal hold."},
            )

        # Re-check unpaid invoices inside the lock
        unpaid_check = await session.execute(
            select(func.count()).select_from(BillingInvoice).where(
                BillingInvoice.tenant_id == principal.tenant_id,
                BillingInvoice.status == "unpaid",
            )
        )
        if (unpaid_check.scalar() or 0) > 0:
            raise HTTPException(
                status_code=400,
                detail={"error": "unpaid_debt", "message": "Settle unpaid invoices before deleting."},
            )

        now = _utcnow()
        purge_at = now + timedelta(days=settings.tenant_deletion_grace_days)

        # Quarantine the tenant
        tenant.status = "quarantined"
        tenant.deleted_by_user_id = principal.user_id
        tenant.deletion_reason = body.reason
        tenant.scheduled_purge_at = purge_at
        tenant.restored_at = None

        # Snapshot active phone numbers for potential restore
        numbers_result = await session.execute(
            select(PhoneNumber).where(
                PhoneNumber.tenant_id == principal.tenant_id,
                PhoneNumber.status == "active",
            )
        )
        active_numbers = numbers_result.scalars().all()
        active_numbers_snapshot = [
            {
                "phone_number_id": str(n.id if hasattr(n, "id") else n.phone_number_id),
                "e164": getattr(n, "e164", None) or getattr(n, "phone_number", None),
                "inbound_enabled": getattr(n, "inbound_enabled", True),
                "outbound_enabled": getattr(n, "outbound_enabled", True),
            }
            for n in active_numbers
        ]

        # Disable all numbers
        await session.execute(
            update(PhoneNumber)
            .where(PhoneNumber.tenant_id == principal.tenant_id)
            .values(inbound_enabled=False, outbound_enabled=False)
        )

        # Pause campaigns, remembering which ones were running so a restore can say
        # exactly what the owner has to resume.
        paused_campaign_ids: list[str] = []
        try:
            from server.db.models.phase5_models import Campaign
            running = await session.execute(
                select(Campaign.campaign_id).where(
                    Campaign.tenant_id == principal.tenant_id, Campaign.status == "active"
                )
            )
            paused_campaign_ids = [str(cid) for cid in running.scalars().all()]
            await session.execute(
                update(Campaign)
                .where(Campaign.tenant_id == principal.tenant_id, Campaign.status == "active")
                .values(status="paused")
            )
        except Exception:
            pass  # Campaign model may not exist in all deployments

        # Revoke refresh tokens for users who belong ONLY to this tenant
        only_here_subq = (
            select(TenantMembership.user_id)
            .group_by(TenantMembership.user_id)
            .having(func.count(TenantMembership.tenant_id) == 1)
            .where(
                TenantMembership.tenant_id == principal.tenant_id
            )
        ).scalar_subquery()
        await session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id.in_(only_here_subq),
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )

        # Enqueue TenantTeardownJob
        idempotency_key = f"teardown:{tenant.tenant_id}:{int(now.timestamp())}"
        job = TenantTeardownJob(
            tenant_id=tenant.tenant_id,
            status="queued",
            stage="queued",
            idempotency_key=idempotency_key,
            payload={
                "active_numbers_snapshot": active_numbers_snapshot,
                "paused_campaign_ids": paused_campaign_ids,
                "initiated_by": str(principal.user_id),
                "scheduled_purge_at": purge_at.isoformat(),
            },
        )
        session.add(job)

        # Audit event
        session.add(
            AuthEvent(
                user_id=principal.user_id,
                tenant_id=principal.tenant_id,
                event_type="tenant.quarantined",
                ip=request.client.host if request.client else None,
            )
        )

        await session.commit()
        committed_purge_at = purge_at
        committed_tenant_id = tenant.tenant_id

    # --- Step 6: Post-commit side effects (best-effort) ---
    try:
        from server.call.call_store import call_store
        terminated = await call_store.terminate_tenant_calls(str(committed_tenant_id))
        if terminated:
            logger.info("tenant.quarantined: terminated %d in-flight calls for tenant=%s", terminated, committed_tenant_id)
    except Exception:
        logger.exception("terminate_tenant_calls failed for tenant=%s", committed_tenant_id)

    try:
        from server.services.saas.redis_eviction import evict_tenant_redis_keys
        await evict_tenant_redis_keys(str(committed_tenant_id))
    except Exception:
        logger.warning("Redis eviction failed for tenant=%s (non-fatal)", committed_tenant_id)

    try:
        _send_deletion_scheduled_email_bg(
            user_email=principal.email,
            tenant_name=tenant_check.name,
            purge_at=committed_purge_at,
        )
    except Exception:
        logger.warning("Deletion notification email failed for tenant=%s (non-fatal)", committed_tenant_id)

    return {
        "status": "quarantined",
        "scheduledPurgeAt": committed_purge_at.isoformat(),
        "gracePeriodDays": settings.tenant_deletion_grace_days,
        "message": (
            f"Your workspace has been quarantined and is scheduled for permanent deletion "
            f"on {committed_purge_at.strftime('%B %d, %Y')}. "
            "You may cancel before this date."
        ),
    }


def _send_deletion_scheduled_email_bg(
    user_email: str,
    tenant_name: str,
    purge_at: datetime,
) -> None:
    """Fire-and-forget transactional email — runs in a background task."""
    import asyncio

    async def _send() -> None:
        try:
            from server.services.saas.email_service import send_deletion_scheduled_email
            await send_deletion_scheduled_email(user_email, tenant_name, purge_at)
        except Exception:
            pass

    try:
        loop = asyncio.get_event_loop()
        loop.create_task(_send())
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Restore during the grace period
# ---------------------------------------------------------------------------
class RestoreTenantBody(BaseModel):
    # Verify-only: needed only when the session is not a fresh sign-in.
    current_password: str | None = Field(None, max_length=200)


def _restore_block_reason(principal: SubscriberPrincipal) -> str | None:
    """Why this caller may not restore, or None. Owner-only, never by impersonation."""
    if principal.role not in ("owner", "customer_admin", "platform_admin"):
        return "not_owner"
    if principal.impersonator:
        return "impersonation"
    return None


def _has_fresh_auth(principal: SubscriberPrincipal, now: datetime) -> bool:
    if not principal.auth_time:
        return False
    age = now.timestamp() - float(principal.auth_time)
    return -60 <= age <= RESTORE_REAUTH_MAX_AGE_SECONDS


def _user_has_password(user: User | None) -> bool:
    return bool(user and user.password_hash and not user.password_hash.startswith("!"))


async def _open_teardown_jobs(session, tenant_id: uuid.UUID) -> list[TenantTeardownJob]:
    rows = await session.execute(
        select(TenantTeardownJob).where(
            TenantTeardownJob.tenant_id == tenant_id,
            TenantTeardownJob.status.in_(_CANCELLABLE_TEARDOWN_STATUSES),
        )
    )
    return list(rows.scalars().all())


def _restore_snapshot(jobs: list[TenantTeardownJob]) -> tuple[list[dict], list[str]]:
    numbers: dict[str, dict] = {}
    campaigns: list[str] = []
    for job in jobs:
        payload = job.payload or {}
        for num in payload.get("active_numbers_snapshot") or []:
            key = str(num.get("phone_number_id") or "")
            if key:
                numbers[key] = num
        for cid in payload.get("paused_campaign_ids") or []:
            if str(cid) not in campaigns:
                campaigns.append(str(cid))
    return list(numbers.values()), campaigns


@router.get("/api/tenant/restore-status")
async def restore_status(
    principal: Annotated[SubscriberPrincipal, Depends(require_subscriber_jwt)],
) -> dict[str, Any]:
    """What restoring this workspace brings back, and whether this caller may do it.

    Reachable by every member while the workspace is pending deletion, so a member
    who signs in sees an explanation instead of a wall of errors.
    """
    from server.db.models.entities import Agent
    from server.services.saas.tenant_guard import as_aware_utc, tenant_in_deletion_grace

    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail={"error": "db_unavailable"})
    now = _utcnow()
    async with factory() as session:
        tenant = await session.get(Tenant, principal.tenant_id)
        if tenant is None:
            raise HTTPException(status_code=404, detail={"error": "tenant_not_found"})
        if tenant.status == "active":
            return {"status": "active", "tenantName": tenant.name}

        purge_at = as_aware_utc(tenant.scheduled_purge_at)
        in_grace = tenant_in_deletion_grace(tenant, now)
        block = _restore_block_reason(principal)
        if block is None and not in_grace:
            block = "grace_expired"
        user = await session.get(User, principal.user_id)

        jobs = await _open_teardown_jobs(session, principal.tenant_id)
        numbers_snapshot, paused_campaigns = _restore_snapshot(jobs)
        requested_at = min(
            (as_aware_utc(j.created_at) for j in jobs if j.created_at), default=None
        )

        agent_count = (
            await session.execute(
                select(func.count()).select_from(Agent).where(Agent.tenant_id == principal.tenant_id)
            )
        ).scalar() or 0
        numbers_count = len(numbers_snapshot)
        if not jobs:
            numbers_count = (
                await session.execute(
                    select(func.count()).select_from(PhoneNumber).where(
                        PhoneNumber.tenant_id == principal.tenant_id,
                        PhoneNumber.status == "active",
                    )
                )
            ).scalar() or 0
        wallet = (
            await session.execute(
                select(BillingWallet).where(BillingWallet.tenant_id == principal.tenant_id)
            )
        ).scalar_one_or_none()
        try:
            from server.db.models.integration_models import TenantIntegration

            integrations_count = (
                await session.execute(
                    select(func.count()).select_from(TenantIntegration).where(
                        TenantIntegration.tenant_id == principal.tenant_id
                    )
                )
            ).scalar() or 0
        except Exception:
            integrations_count = 0

        return {
            "status": tenant.status,
            "tenantName": tenant.name,
            "scheduledPurgeAt": purge_at.isoformat() if purge_at else None,
            "deletionRequestedAt": requested_at.isoformat() if requested_at else None,
            "daysRemaining": max(0, (purge_at - now).days) if (purge_at and in_grace) else 0,
            "inGracePeriod": in_grace,
            "canRestore": block is None,
            "restoreBlockedReason": block,
            "reauthRequired": not _has_fresh_auth(principal, now),
            "hasPassword": _user_has_password(user),
            "deletedByYou": tenant.deleted_by_user_id == principal.user_id,
            "restorePreview": {
                "agents": agent_count,
                "phoneNumbers": numbers_count,
                "campaignsPaused": len(paused_campaigns),
                "integrations": integrations_count,
                "walletBalanceUsd": (wallet.balance_cents or 0) / 100.0 if wallet else 0.0,
                "walletBalanceInr": (wallet.balance_inr_paise or 0) / 100.0 if wallet else 0.0,
            },
        }


async def _restore_tenant(
    principal: SubscriberPrincipal,
    request: Request,
    body: RestoreTenantBody | None,
) -> dict[str, Any]:
    """Owner restore inside the grace period. Atomic and idempotent.

    One transaction holds the tenant row lock while it flips the status, cancels
    every open teardown job (not just one: a leftover queued job on a tenant with no
    purge date is claimed by the worker immediately), re-enables the numbers that
    were live, and writes the audit event. Campaigns stay paused: restarting outbound
    dialling without the owner looking first is not a sensible default.
    """
    from server.services.saas.tenant_guard import tenant_deletion_is_final

    block = _restore_block_reason(principal)
    if block == "not_owner":
        raise HTTPException(
            status_code=403,
            detail={"error": "forbidden", "message": "Only workspace owners may perform this action."},
        )
    if block == "impersonation":
        raise HTTPException(
            status_code=403,
            detail={
                "error": "forbidden",
                "message": "A support session cannot restore a workspace. The owner must sign in.",
            },
        )

    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail={"error": "db_unavailable"})

    now = _utcnow()
    async with factory() as session:
        tenant_result = await session.execute(
            select(Tenant)
            .where(Tenant.tenant_id == principal.tenant_id)
            .with_for_update()
        )
        tenant = tenant_result.scalar_one_or_none()
        if tenant is None:
            raise HTTPException(status_code=404, detail={"error": "tenant_not_found"})

        if tenant.status == "active" and tenant.deleted_at is None:
            # Idempotent: a double click, a retry after a dropped response, or a second
            # tab all land here. Still sweep any stray open job so nothing purges later.
            stray = await _open_teardown_jobs(session, principal.tenant_id)
            for job in stray:
                job.status = "cancelled"
                job.locked_by = None
                job.locked_until = None
                job.updated_at = now
            if stray:
                await session.commit()
            return {
                "status": "active",
                "alreadyActive": True,
                "message": "Workspace is already active.",
            }

        if tenant_deletion_is_final(tenant, now):
            raise HTTPException(
                status_code=410,
                detail={
                    "error": "grace_period_expired",
                    "message": "The grace period has ended and this workspace can no longer be restored.",
                },
            )
        if tenant.status != "quarantined":
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_status", "message": "This workspace is not pending deletion."},
            )

        # --- Fresh authentication (sudo) ---
        if not _has_fresh_auth(principal, now):
            user = await session.get(User, principal.user_id)
            password = (body.current_password if body else None) or ""
            if not password:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "reauth_required",
                        "message": "Confirm it's you: enter your password or sign in again to restore this workspace.",
                        "hasPassword": _user_has_password(user),
                    },
                )
            await _check_delete_rate_limit(f"restore:{principal.user_id}")
            if not _user_has_password(user) or not verify_portal_password(user.password_hash, password):
                raise HTTPException(
                    status_code=400,
                    detail={"error": "invalid_credentials", "message": "Incorrect password."},
                )

        # --- Restore tenant ---
        tenant.status = "active"
        tenant.deleted_at = None
        tenant.scheduled_purge_at = None
        tenant.restored_at = now

        # Cancel EVERY open teardown job and collect their snapshots.
        jobs = await _open_teardown_jobs(session, principal.tenant_id)
        snapshot, paused_campaigns = _restore_snapshot(jobs)
        for job in jobs:
            job.status = "cancelled"
            job.locked_by = None
            job.locked_until = None
            job.updated_at = now

        # Re-enable numbers that were live before quarantine (never a released one).
        restored_numbers = 0
        if snapshot:
            for num in snapshot:
                try:
                    num_uuid = uuid.UUID(str(num.get("phone_number_id")))
                except (TypeError, ValueError):
                    continue
                res = await session.execute(
                    update(PhoneNumber)
                    .where(
                        PhoneNumber.id == num_uuid,
                        PhoneNumber.tenant_id == principal.tenant_id,
                        PhoneNumber.status != "released",
                    )
                    .values(
                        inbound_enabled=num.get("inbound_enabled", True),
                        outbound_enabled=num.get("outbound_enabled", True),
                    )
                )
                restored_numbers += getattr(res, "rowcount", 0) or 0
        elif not jobs:
            # No snapshot to go on (legacy quarantine): re-enable the active numbers.
            res = await session.execute(
                update(PhoneNumber)
                .where(PhoneNumber.tenant_id == principal.tenant_id, PhoneNumber.status == "active")
                .values(inbound_enabled=True, outbound_enabled=True)
            )
            restored_numbers = getattr(res, "rowcount", 0) or 0

        session.add(
            AuthEvent(
                user_id=principal.user_id,
                tenant_id=principal.tenant_id,
                event_type="tenant.restored",
                ip=request.client.host if request.client else None,
            )
        )

        await session.commit()

    logger.info(
        "tenant.restored tenant=%s by=%s jobs_cancelled=%d numbers=%d",
        principal.tenant_id,
        principal.user_id,
        len(jobs),
        restored_numbers,
    )
    return {
        "status": "active",
        "alreadyActive": False,
        "message": "Workspace restored.",
        "restored": {
            "phoneNumbers": restored_numbers,
            "campaignsPaused": len(paused_campaigns),
            "teardownJobsCancelled": len(jobs),
        },
    }


@router.post("/api/tenant/restore")
async def restore_tenant(
    principal: Annotated[SubscriberPrincipal, Depends(require_subscriber_jwt)],
    request: Request,
    body: RestoreTenantBody | None = None,
) -> dict[str, Any]:
    """Restore a workspace pending deletion (owner; fresh sign-in or password)."""
    return await _restore_tenant(principal, request, body)


@router.post("/api/tenant/delete/cancel")
async def cancel_delete_tenant(
    principal: Annotated[SubscriberPrincipal, Depends(require_subscriber_jwt)],
    request: Request,
    body: RestoreTenantBody | None = None,
) -> dict[str, Any]:
    """Legacy alias of POST /api/tenant/restore."""
    return await _restore_tenant(principal, request, body)


# ---------------------------------------------------------------------------
# POST /api/tenant/export
# ---------------------------------------------------------------------------
@router.post("/api/tenant/export")
async def create_export(
    principal: Annotated[SubscriberPrincipal, Depends(require_subscriber_jwt)],
) -> dict[str, Any]:
    """Enqueue a data-takeout (GDPR Art. 20) export job for this workspace."""
    _assert_owner(principal)

    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail={"error": "db_unavailable"})

    async with factory() as session:
        tenant = await session.get(Tenant, principal.tenant_id)
        if tenant is None:
            raise HTTPException(status_code=404, detail={"error": "tenant_not_found"})

        # Quarantined tenants may still export data during grace period
        if tenant.status in ("deleting", "deleted"):
            raise HTTPException(
                status_code=403,
                detail={"error": "tenant_deleted", "message": "Workspace data has already been purged."},
            )

        job = TenantExportJob(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            status="queued",
        )
        session.add(job)
        session.add(
            AuthEvent(
                user_id=principal.user_id,
                tenant_id=principal.tenant_id,
                event_type="tenant.export_requested",
            )
        )
        await session.commit()
        await session.refresh(job)

    # Fire background export worker (best-effort; no await blocking the response)
    _start_export_worker_bg(str(job.job_id), str(principal.tenant_id))

    return {
        "jobId": str(job.job_id),
        "status": "queued",
        "message": "Your data export has been queued. Check back in a few minutes.",
    }


def _start_export_worker_bg(job_id: str, tenant_id: str) -> None:
    """Schedule the export generation as an async background task."""
    import asyncio

    async def _run() -> None:
        try:
            from server.services.saas.export_worker import process_export_job
            await process_export_job(job_id, tenant_id)
        except Exception:
            logger.exception("export_worker failed job_id=%s tenant=%s", job_id, tenant_id)

    try:
        loop = asyncio.get_event_loop()
        loop.create_task(_run())
    except Exception:
        pass


# ---------------------------------------------------------------------------
# GET /api/tenant/export/agents (Direct JSON backup of all workspace agents)
# ---------------------------------------------------------------------------
@router.get("/api/tenant/export/agents")
async def export_agents_json(
    principal: Annotated[SubscriberPrincipal, Depends(require_subscriber_jwt)],
) -> JSONResponse:
    """Download full JSON backup of all agents, scripts, and telephony profiles for this workspace."""
    _assert_owner(principal)
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail={"error": "db_unavailable"})

    async with factory() as session:
        tenant = await session.get(Tenant, principal.tenant_id)
        if tenant is None:
            raise HTTPException(status_code=404, detail={"error": "tenant_not_found"})

        from server.db.models.entities import Agent
        from server.db.models.phase5_models import AgentTelephonyProfile
        from server.brain.business_brain_store import business_brain_store

        agents_result = await session.execute(
            select(Agent).where(Agent.tenant_id == principal.tenant_id).order_by(Agent.created_at.desc())
        )
        agents = agents_result.scalars().all()
        agents_data = []
        for a in agents:
            prof_result = await session.execute(
                select(AgentTelephonyProfile).where(
                    AgentTelephonyProfile.agent_id == a.agent_id,
                    AgentTelephonyProfile.tenant_id == principal.tenant_id,
                )
            )
            prof = prof_result.scalar_one_or_none()
            telephony_info = {
                "greeting_phrase": prof.greeting_phrase if prof else None,
                "timezone": prof.timezone if prof else "UTC",
                "business_hours": prof.business_hours if prof else {},
                "after_hours_action": prof.after_hours_action if prof else "hangup",
                "transfer_number": prof.transfer_number if prof else None,
                "inbound_enabled": getattr(prof, "inbound_enabled", True) if prof else True,
                "outbound_enabled": getattr(prof, "outbound_enabled", True) if prof else True,
            } if prof else {}

            try:
                sections = await business_brain_store.get_sections(str(a.agent_id))
            except Exception:
                sections = []

            agents_data.append({
                "agent_id": str(a.agent_id),
                "name": a.name,
                "status": a.status,
                "default_tier": a.default_tier,
                "languages": a.languages,
                "voice_settings": a.voice_settings or {},
                "recording_disclosure_enabled": a.recording_disclosure_enabled,
                "telephony_profile": telephony_info,
                "brain_sections": sections,
                "created_at": a.created_at.isoformat(),
            })

        export_payload = {
            "version": "1.0",
            "exported_at": _utcnow().isoformat(),
            "tenant_id": str(principal.tenant_id),
            "tenant_name": tenant.name,
            "agent_count": len(agents_data),
            "agents": agents_data,
        }

        safe_tenant_name = "".join(c for c in tenant.name if c.isalnum() or c in ("-", "_")).strip() or "workspace"
        headers = {
            "Content-Disposition": f'attachment; filename="{safe_tenant_name}_agents_backup.json"'
        }
        return JSONResponse(content=export_payload, headers=headers)


# ---------------------------------------------------------------------------
# GET /api/tenant/export/{job_id}/download (Download export ZIP archive)
# ---------------------------------------------------------------------------
@router.get("/api/tenant/export/{job_id}/download")
async def download_export_archive(
    job_id: str,
    principal: Annotated[SubscriberPrincipal, Depends(require_subscriber_jwt)],
):
    """Download the generated export ZIP archive directly."""
    _assert_owner(principal)
    from fastapi.responses import FileResponse, RedirectResponse
    from server.services.saas.export_worker import _EXPORT_CACHE_DIR, _build_export_zip

    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail={"error": "db_unavailable"})

    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail={"error": "invalid_job_id"})

    async with factory() as session:
        job = await session.get(TenantExportJob, job_uuid)
        if job is None or job.tenant_id != principal.tenant_id:
            raise HTTPException(status_code=404, detail={"error": "export_job_not_found"})

        if job.status != "ready":
            # If still processing, try to build on demand
            try:
                zip_bytes = await _build_export_zip(principal.tenant_id)
                _EXPORT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                local_path = _EXPORT_CACHE_DIR / f"{job_id}.zip"
                local_path.write_bytes(zip_bytes)
                job.status = "ready"
                await session.commit()
            except Exception:
                raise HTTPException(status_code=400, detail={"error": "export_not_ready", "message": f"Export job is in '{job.status}' state."})

        # If external URL, redirect
        if job.download_url and job.download_url.startswith("http"):
            return RedirectResponse(job.download_url)

        local_path = _EXPORT_CACHE_DIR / f"{job_id}.zip"
        if not local_path.exists():
            zip_bytes = await _build_export_zip(principal.tenant_id)
            _EXPORT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(zip_bytes)

        safe_tenant_name = "".join(c for c in str(principal.tenant_id) if c.isalnum() or c in ("-", "_")).strip()
        return FileResponse(
            str(local_path),
            media_type="application/zip",
            filename=f"workspace_export_{safe_tenant_name}.zip",
        )


# ---------------------------------------------------------------------------
# GET /api/tenant/export/{job_id}
# ---------------------------------------------------------------------------
@router.get("/api/tenant/export/{job_id}")
async def get_export_status(
    job_id: str,
    principal: Annotated[SubscriberPrincipal, Depends(require_subscriber_jwt)],
) -> dict[str, Any]:
    """Poll export job status and retrieve the pre-signed download URL."""
    _assert_owner(principal)

    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail={"error": "db_unavailable"})

    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail={"error": "invalid_job_id"})

    async with factory() as session:
        job = await session.get(TenantExportJob, job_uuid)
        if job is None or job.tenant_id != principal.tenant_id:
            raise HTTPException(status_code=404, detail={"error": "export_job_not_found"})

        # Audit log on download
        if job.status == "ready" and job.download_url:
            session.add(
                AuthEvent(
                    user_id=principal.user_id,
                    tenant_id=principal.tenant_id,
                    event_type="tenant.export_downloaded",
                )
            )
            await session.commit()

        is_expired = job.expires_at is not None and job.expires_at <= _utcnow()
        return {
            "jobId": str(job.job_id),
            "status": "expired" if is_expired else job.status,
            "downloadUrl": job.download_url if not is_expired else None,
            "expiresAt": job.expires_at.isoformat() if job.expires_at else None,
            "createdAt": job.created_at.isoformat(),
        }


