"""Platform dev admin ? SaaS operations (PRD-06)."""
from __future__ import annotations

import io
import logging
import secrets
import uuid
import wave
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import case, delete, desc, func, select, update

from server.config.env import get_settings

logger = logging.getLogger(__name__)

from server.auth.dependencies import require_dev_session, require_permission
from server.auth.passwords import hash_portal_password
from server.auth.rbac import (
    ROLE_ADMINISTRATOR,
    ROLE_CUSTOMER_ADMIN,
    ROLE_CUSTOMER_VIEWER,
    ROLE_DEVELOPER,
    ROLE_PLATFORM_ADMIN,
    ROLE_VOICE_ENGINEER,
)
from server.auth.session import SessionData
from server.db.connection import get_session_factory
from server.db.models.entities import Agent, AgentFallbackClip, Call, CallAttempt, Tenant
from server.db.models.phase5_models import PhoneNumber
from server.db.models.saas_models import (
    AuthEvent,
    BillingWallet,
    BillingWalletTransaction,
    NumberPurchase,
    ProvisionJob,
    RefreshToken,
    TenantMembership,
    User,
)
from server.services.saas.admin_audit import record_admin_action
from server.services.saas.provision_worker import enqueue_provision

router = APIRouter()


def _require_db() -> None:
    if get_session_factory() is None:
        raise HTTPException(status_code=503, detail="DATABASE_URL required")


class TenantPatchBody(BaseModel):
    status: Optional[str] = None
    plan: Optional[str] = None
    limits: Optional[dict[str, Any]] = None
    name: Optional[str] = None
    billingSource: Optional[str] = None
    note: Optional[str] = Field(None, max_length=500)
    releaseNumbers: bool = False
    revokeSessions: bool = False


class ImpersonateBody(BaseModel):
    note: str = Field(..., min_length=8, max_length=500)
    userId: Optional[str] = None
    ttlMinutes: int = Field(30, ge=5, le=120)


class TenantCreateBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    plan: Optional[str] = None
    status: str = "active"
    limits: Optional[dict[str, Any]] = None


_TENANT_STATUS_VALUES = frozenset({"active", "quarantined", "suspended", "past_due", "cancelled", "deleted"})
_TENANT_PLAN_VALUES = frozenset({"starter", "growth", "enterprise", "default", "platform", "dev"})


class TenantDeleteBody(BaseModel):
    force: bool = False
    releaseNumbers: bool = True
    revokeSessions: bool = True
    hard: bool = False
    note: Optional[str] = Field(None, max_length=500)


class TenantBulkActionBody(BaseModel):
    action: str = Field(..., description="delete | restore | suspend | activate | change_plan")
    tenantIds: list[str] = Field(..., min_length=1, max_length=100)
    plan: Optional[str] = None
    note: str = Field("", max_length=500)
    releaseNumbers: bool = True
    revokeSessions: bool = True
    force: bool = False


class UserPatchBody(BaseModel):
    status: str


class AdminCreateUserBody(BaseModel):
    email: str
    fullName: str = ""
    tenantId: str
    role: str = "customer_viewer"


class MembershipBody(BaseModel):
    userId: str
    tenantId: str
    role: str


class PlatformSupportConfigBody(BaseModel):
    supportEmail: Optional[str] = Field(None, max_length=320)
    businessHours: Optional[str] = Field(None, max_length=128)
    slaResponseTime: Optional[str] = Field(None, max_length=128)
    autoReplyMessage: Optional[str] = Field(None, max_length=10000)
    isActive: Optional[bool] = None
    twitterUrl: Optional[str] = Field(None, max_length=512)
    linkedinUrl: Optional[str] = Field(None, max_length=512)
    githubUrl: Optional[str] = Field(None, max_length=512)
    youtubeUrl: Optional[str] = Field(None, max_length=512)
    discordUrl: Optional[str] = Field(None, max_length=512)
    smtpHost: Optional[str] = Field(None, max_length=255)
    smtpPort: Optional[int] = Field(None, ge=1, le=65535)
    smtpUsername: Optional[str] = Field(None, max_length=255)
    smtpPassword: Optional[str] = Field(None, max_length=255)
    smtpUseTls: Optional[bool] = None
    senderEmail: Optional[str] = Field(None, max_length=320)
    senderName: Optional[str] = Field(None, max_length=128)
    notifyCustomerOnTicket: Optional[bool] = None
    notifyAdminOnTicket: Optional[bool] = None
    adminAlertEmail: Optional[str] = Field(None, max_length=320)


class PlatformSmtpTestBody(BaseModel):
    smtpHost: str = Field(..., min_length=1, max_length=255)
    smtpPort: int = Field(587, ge=1, le=65535)
    smtpUsername: Optional[str] = Field(None, max_length=255)
    smtpPassword: Optional[str] = Field(None, max_length=255)
    smtpUseTls: bool = True


class PlatformSupportInquiryPatchBody(BaseModel):
    status: Optional[str] = Field(None, pattern="^(new|in_progress|waiting_on_customer|resolved|closed)$")
    assignedTo: Optional[str] = Field(None, max_length=320)
    adminNotes: Optional[str] = Field(None, max_length=10000)
    resolutionNotes: Optional[str] = Field(None, max_length=10000)
    replyMessage: Optional[str] = Field(None, max_length=10000)
    tags: Optional[list[str]] = Field(None, max_length=30)


class DirectCarrierPurchaseBody(BaseModel):
    e164: str = Field(..., min_length=8, max_length=20)
    provider: str = Field("vobiz", pattern="^(vobiz|telnyx)$")
    country: str = Field("US", max_length=8)
    tenantId: str
    reason: str = Field(..., min_length=8, max_length=500)


class AllocateNumberBody(BaseModel):
    e164: str
    tenantId: str
    telnyxNumberId: Optional[str] = None


class NumberPatchBody(BaseModel):
    tenantId: Optional[str] = None
    agentId: Optional[str] = None


@router.get("/api/dev/admin/dashboard")
async def admin_dashboard(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.tenants")
    _require_db()
    async with get_session_factory()() as db:
        tenants = int((await db.execute(select(func.count()).select_from(Tenant))).scalar_one() or 0)
        users = int((await db.execute(select(func.count()).select_from(User))).scalar_one() or 0)
        numbers = int(
            (
                await db.execute(
                    select(func.count()).select_from(PhoneNumber).where(PhoneNumber.released_at.is_(None))
                )
            ).scalar_one()
            or 0
        )
        failed = int(
            (
                await db.execute(
                    select(func.count()).select_from(NumberPurchase).where(NumberPurchase.status == "failed")
                )
            ).scalar_one()
            or 0
        )
    return {"tenants": tenants, "users": users, "activeNumbers": numbers, "failedPurchases": failed}


@router.get("/api/dev/admin/tenants")
async def list_tenants(
    q: str = "",
    status: str | None = None,
    plan: str | None = None,
    excludeInventory: bool = Query(True, alias="excludeInventory"),
    includeDeleted: bool = Query(False, alias="includeDeleted"),
    hasNumbers: bool | None = Query(None, alias="hasNumbers"),
    minBalanceUsd: float | None = Query(None, alias="minBalanceUsd"),
    maxBalanceUsd: float | None = Query(None, alias="maxBalanceUsd"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.tenants")
    _require_db()
    from server.services.saas.number_inventory import INVENTORY_TENANT_NAME

    async with get_session_factory()() as db:
        stmt = select(Tenant)
        if not includeDeleted:
            stmt = stmt.where(Tenant.deleted_at.is_(None))
        if q.strip():
            stmt = stmt.where(Tenant.name.ilike(f"%{q.strip()}%"))
        if status and status.strip():
            stmt = stmt.where(Tenant.status == status.strip())
        if plan and plan.strip():
            stmt = stmt.where(Tenant.plan == plan.strip())
        if excludeInventory:
            stmt = stmt.where(Tenant.name != INVENTORY_TENANT_NAME)
        stmt = stmt.order_by(desc(Tenant.created_at))
        all_rows = (await db.execute(stmt)).scalars().all()

        wallets = {
            w.tenant_id: w
            for w in (
                await db.execute(
                    select(BillingWallet).where(
                        BillingWallet.tenant_id.in_([t.tenant_id for t in all_rows] or [uuid.uuid4()])
                    )
                )
            ).scalars().all()
        }
        created = False
        for t in all_rows:
            if t.tenant_id not in wallets:
                w = BillingWallet(
                    tenant_id=t.tenant_id,
                    balance_cents=0,
                    balance_inr_paise=0,
                    currency="usd",
                    updated_at=datetime.now(timezone.utc),
                )
                db.add(w)
                wallets[t.tenant_id] = w
                created = True
        if created:
            await db.commit()

        number_counts: dict[uuid.UUID, int] = {}
        if all_rows:
            count_rows = (
                await db.execute(
                    select(PhoneNumber.tenant_id, func.count())
                    .where(
                        PhoneNumber.tenant_id.in_([t.tenant_id for t in all_rows]),
                        PhoneNumber.released_at.is_(None),
                    )
                    .group_by(PhoneNumber.tenant_id)
                )
            ).all()
            number_counts = {tid: int(c or 0) for tid, c in count_rows}

        member_counts: dict[uuid.UUID, int] = {}
        if all_rows:
            mem_rows = (
                await db.execute(
                    select(TenantMembership.tenant_id, func.count())
                    .where(TenantMembership.tenant_id.in_([t.tenant_id for t in all_rows]))
                    .group_by(TenantMembership.tenant_id)
                )
            ).all()
            member_counts = {tid: int(c or 0) for tid, c in mem_rows}

        from server.services.saas.billing_rates import load_current_rates

        fx = float((await load_current_rates())["fx_rate_inr"])

        def _usd_balance(tid: uuid.UUID) -> float:
            w = wallets.get(tid)
            if w is None:
                return 0.0
            cents = int(w.balance_cents or 0)
            if cents > 0:
                return cents / 100.0
            paise = int(w.balance_inr_paise or 0)
            return round((paise / 100.0) / fx, 2) if paise else 0.0

        filtered = []
        for t in all_rows:
            n_count = number_counts.get(t.tenant_id, 0)
            if hasNumbers is True and n_count <= 0:
                continue
            if hasNumbers is False and n_count > 0:
                continue
            bal = _usd_balance(t.tenant_id)
            if minBalanceUsd is not None and bal < minBalanceUsd:
                continue
            if maxBalanceUsd is not None and bal > maxBalanceUsd:
                continue
            filtered.append((t, bal, n_count))

        total = len(filtered)
        page = filtered[offset : offset + limit]
        tenants_out = []
        for t, bal, n_count in page:
            w = wallets[t.tenant_id]
            tenants_out.append(
                {
                    "tenantId": str(t.tenant_id),
                    "name": t.name,
                    "plan": t.plan,
                    "status": getattr(t, "status", "active"),
                    "createdAt": t.created_at.isoformat() if t.created_at else None,
                    "deletedAt": t.deleted_at.isoformat() if t.deleted_at else None,
                    "walletBalanceUsd": round(bal, 2),
                    "walletBalanceInr": round((w.balance_inr_paise or 0) / 100.0, 2),
                    "walletCurrency": (w.currency or "usd").upper(),
                    "numberCount": n_count,
                    "memberCount": member_counts.get(t.tenant_id, 0),
                    "isInventory": t.name == INVENTORY_TENANT_NAME,
                }
            )
    return {"tenants": tenants_out, "total": total, "limit": limit, "offset": offset}


@router.get("/api/dev/admin/tenants/{tenant_id}")
async def tenant_detail(tenant_id: str, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.tenants")
    _require_db()
    tid = uuid.UUID(tenant_id)
    async with get_session_factory()() as db:
        tenant = await db.get(Tenant, tid)
        if tenant is None or tenant.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Not found")
        agents = (await db.execute(select(Agent).where(Agent.tenant_id == tid))).scalars().all()
        numbers = (
            await db.execute(select(PhoneNumber).where(PhoneNumber.tenant_id == tid, PhoneNumber.released_at.is_(None)))
        ).scalars().all()
        mems = (
            await db.execute(select(TenantMembership, User).join(User, User.user_id == TenantMembership.user_id).where(TenantMembership.tenant_id == tid))
        ).all()
        calls = (
            await db.execute(select(Call).where(Call.tenant_id == tid).order_by(desc(Call.started_at)).limit(20))
        ).scalars().all()
        wallet = await db.get(BillingWallet, tid)
        call_count = int(
            (await db.execute(select(func.count()).select_from(Call).where(Call.tenant_id == tid))).scalar_one() or 0
        )
    from server.services.saas.billing_wallet_service import list_wallet_transactions
    from server.services.saas import kyc_service
    from server.services.saas.billing_rates import load_current_rates

    fx_rate_inr = float((await load_current_rates())["fx_rate_inr"])
    transactions = await list_wallet_transactions(tid, limit=50)
    verifications = []
    for _m, u in mems:
        try:
            st = await kyc_service.get_status(u.user_id)
            verifications.append(
                {
                    "userId": str(u.user_id),
                    "email": u.email,
                    "fullName": u.full_name,
                    "status": st.get("status") or st.get("state") or "Not Started",
                    "approved": bool(st.get("approved")),
                    "updatedAt": st.get("updatedAt") or st.get("verifiedAt"),
                }
            )
        except Exception:
            verifications.append(
                {
                    "userId": str(u.user_id),
                    "email": u.email,
                    "fullName": u.full_name,
                    "status": "Not Started",
                    "approved": False,
                    "updatedAt": None,
                }
            )
    wallet_payload = None
    if wallet is not None:
        wallet_payload = {
            "balanceUsd": round((wallet.balance_cents or 0) / 100.0, 2),
            "balanceInr": round((wallet.balance_inr_paise or 0) / 100.0, 2),
            "balanceCents": int(wallet.balance_cents or 0),
            "balanceInrPaise": int(wallet.balance_inr_paise or 0),
            "currency": (wallet.currency or "usd").upper(),
            "updatedAt": wallet.updated_at.isoformat() if wallet.updated_at else None,
        }
    from server.services.saas import voice_kyc_service
    voice_kyc = None
    try:
        voice_kyc = await voice_kyc_service.refresh_kyc_status(tid)
    except Exception as exc:
        logger.warning("Tenant voice KYC status lookup failed: %s", exc)
        voice_kyc = None

    return {
        "tenant": {
            "tenantId": str(tenant.tenant_id),
            "name": tenant.name,
            "status": tenant.status,
            "plan": tenant.plan,
            "limits": tenant.limits or {},
            "billingSource": tenant.billing_source,
            "createdAt": tenant.created_at.isoformat() if tenant.created_at else None,
            "stripeCustomerId": tenant.stripe_customer_id,
        },
        "wallet": wallet_payload,
        "walletTransactions": transactions,
        "fxRateInr": fx_rate_inr,
        "verifications": verifications,
        "voiceKyc": voice_kyc,
        "counts": {
            "agents": len(agents),
            "numbers": len(numbers),
            "members": len(mems),
            "calls": call_count,
        },
        "agents": [
            {
                "agentId": str(a.agent_id),
                "name": a.name,
                "status": a.status,
                "languages": a.languages if isinstance(getattr(a, "languages", None), list) else [],
            }
            for a in agents
        ],
        "numbers": [
            {
                "id": str(n.id),
                "e164": n.e164,
                "agentId": str(n.agent_id) if n.agent_id else None,
                "status": n.status,
            }
            for n in numbers
        ],
        "users": [{"userId": str(u.user_id), "email": u.email, "role": m.role, "fullName": u.full_name} for m, u in mems],
        "members": [{"userId": str(u.user_id), "email": u.email, "role": m.role} for m, u in mems],
        "recentCalls": [
            {
                "callId": str(c.call_id),
                "startedAt": c.started_at.isoformat() if c.started_at else None,
                "direction": getattr(c, "direction", None),
                "status": getattr(c, "status", None),
            }
            for c in calls
        ],
    }


@router.post("/api/dev/admin/tenants")
async def create_tenant(body: TenantCreateBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.tenants")
    _require_db()
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    tid = uuid.uuid4()
    async with get_session_factory()() as db:
        tenant = Tenant(
            tenant_id=tid,
            name=name,
            plan=(body.plan or "").strip() or "default",
            status=(body.status or "active").strip() or "active",
            limits=body.limits or {},
            billing_source="self_serve",
            created_at=datetime.now(timezone.utc),
        )
        db.add(tenant)
        db.add(
            BillingWallet(
                tenant_id=tid,
                balance_cents=0,
                balance_inr_paise=0,
                currency="usd",
                updated_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()
    await record_admin_action(
        actor=session.subject,
        action="tenant.create",
        resource_type="tenant",
        resource_id=str(tid),
        tenant_id=tid,
        payload={"name": name, "plan": body.plan, "status": body.status},
    )
    return {"ok": True, "tenantId": str(tid)}


def _clean_query_bool(val: Any, default: bool = False) -> bool:
    if isinstance(val, bool):
        return val
    if hasattr(val, "default"):
        return bool(val.default)
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes")
    return bool(val) if val is not None else default


def _clean_query_str(val: Any, default: str = "") -> str:
    if isinstance(val, str):
        return val
    if hasattr(val, "default"):
        return str(val.default) if val.default is not None else default
    return str(val) if val is not None else default


@router.delete("/api/dev/admin/tenants/{tenant_id}")
async def delete_tenant(
    tenant_id: str,
    force: bool = Query(False),
    release_numbers: bool = Query(True, alias="releaseNumbers"),
    revoke_sessions: bool = Query(True, alias="revokeSessions"),
    hard: bool = Query(False),
    note: str = Query(""),
    body: Optional[TenantDeleteBody] = None,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.tenants")
    _require_db()
    tid = uuid.UUID(tenant_id)
    eff_force = _clean_query_bool(body.force if body and body.force is not None else force, False)
    eff_release = _clean_query_bool(body.releaseNumbers if body and body.releaseNumbers is not None else release_numbers, True)
    eff_revoke = _clean_query_bool(body.revokeSessions if body and body.revokeSessions is not None else revoke_sessions, True)
    eff_hard = _clean_query_bool(body.hard if body and body.hard is not None else hard, False)
    eff_note = _clean_query_str(body.note if body and body.note is not None else note, "").strip()

    released_numbers: list[str] = []
    revoked_sessions: int = 0

    if eff_release:
        from server.services.saas.number_inventory import move_to_inventory

        async with get_session_factory()() as db:
            nums = (
                await db.execute(
                    select(PhoneNumber).where(
                        PhoneNumber.tenant_id == tid,
                        PhoneNumber.released_at.is_(None),
                    )
                )
            ).scalars().all()
            e164s = [n.e164 for n in nums if n.e164]
        for e164 in e164s:
            try:
                await move_to_inventory(e164=e164)
                released_numbers.append(e164)
            except Exception as e:
                logger.warning(f"Failed to release number {e164} for tenant {tid}: {e}")

    async with get_session_factory()() as db:
        tenant = await db.get(Tenant, tid)
        if tenant is None:
            raise HTTPException(status_code=404, detail="Not found")
        if tenant.deleted_at is not None and not eff_hard:
            return {"ok": True, "alreadyDeleted": True}

        active_numbers = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(PhoneNumber)
                    .where(PhoneNumber.tenant_id == tid, PhoneNumber.released_at.is_(None))
                )
            ).scalar_one()
            or 0
        )
        if active_numbers and not eff_force:
            raise HTTPException(
                status_code=400,
                detail=f"Tenant still has {active_numbers} active number(s). Choose 'Release numbers' or pass force=true.",
            )

        if eff_revoke:
            member_ids = (
                await db.execute(
                    select(TenantMembership.user_id).where(TenantMembership.tenant_id == tid)
                )
            ).scalars().all()
            if member_ids:
                result = await db.execute(
                    update(RefreshToken)
                    .where(
                        RefreshToken.user_id.in_(list(member_ids)),
                        RefreshToken.revoked_at.is_(None),
                    )
                    .values(revoked_at=datetime.now(timezone.utc))
                )
                revoked_sessions = int(result.rowcount or 0)

        tenant.status = "deleted"
        tenant.deleted_at = datetime.now(timezone.utc)
        await db.commit()

    await record_admin_action(
        actor=session.subject,
        action="tenant.delete",
        resource_type="tenant",
        resource_id=tenant_id,
        tenant_id=tid,
        payload={
            "force": eff_force,
            "releaseNumbers": eff_release,
            "revokeSessions": eff_revoke,
            "hard": eff_hard,
            "note": eff_note or None,
            "releasedCount": len(released_numbers),
            "revokedSessions": revoked_sessions,
        },
    )
    return {
        "ok": True,
        "releasedNumbers": released_numbers,
        "revokedSessions": revoked_sessions,
    }


@router.post("/api/dev/admin/tenants/{tenant_id}/restore")
async def restore_tenant(
    tenant_id: str,
    note: str = Query(""),
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.tenants")
    _require_db()
    tid = uuid.UUID(tenant_id)
    async with get_session_factory()() as db:
        tenant = await db.get(Tenant, tid)
        if tenant is None:
            raise HTTPException(status_code=404, detail="Not found")
        tenant.deleted_at = None
        tenant.status = "active"
        await db.commit()

    await record_admin_action(
        actor=session.subject,
        action="tenant.restore",
        resource_type="tenant",
        resource_id=tenant_id,
        tenant_id=tid,
        payload={"note": _clean_query_str(note).strip() or None},
    )
    return {"ok": True}


@router.post("/api/dev/admin/tenants/bulk")
async def bulk_tenant_actions(
    body: TenantBulkActionBody,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.tenants")
    _require_db()
    action = body.action.strip().lower()
    allowed_actions = {"delete", "restore", "suspend", "activate", "change_plan"}
    if action not in allowed_actions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid bulk action. Allowed: {', '.join(sorted(allowed_actions))}",
        )

    if action == "change_plan":
        if not body.plan or body.plan not in _TENANT_PLAN_VALUES:
            raise HTTPException(
                status_code=400,
                detail=f"Valid plan required for change_plan. Options: {', '.join(sorted(_TENANT_PLAN_VALUES))}",
            )

    processed: list[str] = []
    failed: list[dict[str, str]] = []

    from server.services.saas.number_inventory import move_to_inventory

    for raw_id in body.tenantIds:
        try:
            tid = uuid.UUID(raw_id)
        except ValueError:
            failed.append({"tenantId": raw_id, "error": "Invalid UUID"})
            continue

        try:
            async with get_session_factory()() as db:
                tenant = await db.get(Tenant, tid)
                if not tenant:
                    failed.append({"tenantId": raw_id, "error": "Tenant not found"})
                    continue

                if action == "delete":
                    if body.releaseNumbers:
                        nums = (
                            await db.execute(
                                select(PhoneNumber).where(
                                    PhoneNumber.tenant_id == tid,
                                    PhoneNumber.released_at.is_(None),
                                )
                            )
                        ).scalars().all()
                        for n in nums:
                            if n.e164:
                                try:
                                    await move_to_inventory(e164=n.e164)
                                except Exception:
                                    pass
                    if body.revokeSessions:
                        member_ids = (
                            await db.execute(
                                select(TenantMembership.user_id).where(TenantMembership.tenant_id == tid)
                            )
                        ).scalars().all()
                        if member_ids:
                            await db.execute(
                                update(RefreshToken)
                                .where(
                                    RefreshToken.user_id.in_(list(member_ids)),
                                    RefreshToken.revoked_at.is_(None),
                                )
                                .values(revoked_at=datetime.now(timezone.utc))
                            )
                    tenant.status = "deleted"
                    tenant.deleted_at = datetime.now(timezone.utc)

                elif action == "restore":
                    tenant.deleted_at = None
                    tenant.status = "active"

                elif action == "suspend":
                    if body.releaseNumbers:
                        nums = (
                            await db.execute(
                                select(PhoneNumber).where(
                                    PhoneNumber.tenant_id == tid,
                                    PhoneNumber.released_at.is_(None),
                                )
                            )
                        ).scalars().all()
                        for n in nums:
                            if n.e164:
                                try:
                                    await move_to_inventory(e164=n.e164)
                                except Exception:
                                    pass
                    if body.revokeSessions:
                        member_ids = (
                            await db.execute(
                                select(TenantMembership.user_id).where(TenantMembership.tenant_id == tid)
                            )
                        ).scalars().all()
                        if member_ids:
                            await db.execute(
                                update(RefreshToken)
                                .where(
                                    RefreshToken.user_id.in_(list(member_ids)),
                                    RefreshToken.revoked_at.is_(None),
                                )
                                .values(revoked_at=datetime.now(timezone.utc))
                            )
                    tenant.status = "suspended"

                elif action == "activate":
                    if tenant.deleted_at:
                        tenant.deleted_at = None
                    tenant.status = "active"

                elif action == "change_plan":
                    tenant.plan = body.plan

                await db.commit()
                processed.append(raw_id)
        except Exception as exc:
            failed.append({"tenantId": raw_id, "error": str(exc)})

    await record_admin_action(
        actor=session.subject,
        action="tenant.bulk",
        resource_type="tenant",
        resource_id=f"bulk:{len(processed)}",
        payload={
            "action": action,
            "processedCount": len(processed),
            "failedCount": len(failed),
            "plan": body.plan,
            "note": body.note,
        },
    )
    return {"ok": True, "processed": processed, "failed": failed}


@router.patch("/api/dev/admin/tenants/{tenant_id}")
async def patch_tenant(
    tenant_id: str,
    body: TenantPatchBody,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.tenants")
    _require_db()
    tid = uuid.UUID(tenant_id)
    note = (body.note or "").strip()
    status_changing = body.status is not None
    if status_changing:
        status = body.status.strip() if body.status else ""
        if status not in _TENANT_STATUS_VALUES:
            raise HTTPException(status_code=400, detail=f"Invalid status. Use: {', '.join(sorted(_TENANT_STATUS_VALUES))}")
        if len(note) < 8:
            raise HTTPException(
                status_code=400,
                detail="Admin statement required (min 8 chars) when changing tenant status.",
            )
    if body.plan is not None:
        plan = body.plan.strip()
        if plan and plan not in _TENANT_PLAN_VALUES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid plan. Use: {', '.join(sorted(_TENANT_PLAN_VALUES))}",
            )
    released: list[str] = []
    revoked_sessions = 0
    prev_status: str | None = None
    async with get_session_factory()() as db:
        tenant = await db.get(Tenant, tid)
        if tenant is None or tenant.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Not found")
        prev_status = tenant.status
        if body.name is not None:
            tenant.name = body.name.strip() or tenant.name
        if body.status is not None:
            tenant.status = body.status.strip()
        if body.plan is not None:
            tenant.plan = body.plan.strip() or tenant.plan
        if body.limits is not None:
            tenant.limits = body.limits
        if body.billingSource is not None:
            src = body.billingSource.strip()
            if src:
                tenant.billing_source = src
        if body.revokeSessions and status_changing and body.status in {"suspended", "cancelled"}:
            member_ids = (
                await db.execute(
                    select(TenantMembership.user_id).where(TenantMembership.tenant_id == tid)
                )
            ).scalars().all()
            if member_ids:
                result = await db.execute(
                    update(RefreshToken)
                    .where(
                        RefreshToken.user_id.in_(list(member_ids)),
                        RefreshToken.revoked_at.is_(None),
                    )
                    .values(revoked_at=datetime.now(timezone.utc))
                )
                revoked_sessions = int(result.rowcount or 0)
        await db.commit()

    if body.releaseNumbers and status_changing and body.status in {"suspended", "cancelled"}:
        from server.services.saas.number_inventory import move_to_inventory

        async with get_session_factory()() as db:
            nums = (
                await db.execute(
                    select(PhoneNumber).where(
                        PhoneNumber.tenant_id == tid,
                        PhoneNumber.released_at.is_(None),
                    )
                )
            ).scalars().all()
            e164s = [n.e164 for n in nums if n.e164]
        for e164 in e164s:
            try:
                await move_to_inventory(e164=e164)
                released.append(e164)
            except Exception:
                pass

    await record_admin_action(
        actor=session.subject,
        action="tenant.patch",
        resource_type="tenant",
        resource_id=tenant_id,
        tenant_id=tid,
        payload={
            **body.model_dump(exclude_none=True),
            "previousStatus": prev_status if status_changing else None,
            "releasedNumbers": released or None,
            "revokedSessions": revoked_sessions or None,
        },
    )
    return {
        "ok": True,
        "releasedNumbers": released,
        "revokedSessions": revoked_sessions,
    }


@router.post("/api/dev/admin/tenants/{tenant_id}/impersonate")
async def impersonate_tenant(
    tenant_id: str,
    body: ImpersonateBody,
    session: SessionData = Depends(require_dev_session),
):
    """Time-boxed 'Open as customer' session for support. Audited; console shows a banner."""
    require_permission(session, "dev.admin.tenants")
    _require_db()
    tid = uuid.UUID(tenant_id)
    note = body.note.strip()
    uid = uuid.UUID(body.userId) if body.userId else None
    from server.services.saas import auth_service
    from server.services.saas.google_oauth_service import create_auth_handoff

    try:
        data = await auth_service.issue_impersonation_session(
            tenant_id=tid,
            actor=session.subject,
            user_id=uid,
            ttl_seconds=int(body.ttlMinutes) * 60,
        )
    except ValueError as e:
        code = str(e)
        raise HTTPException(status_code=400, detail=code.replace("_", " "))

    settings = get_settings()
    front = (settings.voxly_frontend_url or "http://localhost:5173").rstrip("/")
    # Prefer local Vite for ops handoff so tunnel never receives the session.
    if "localhost" not in front and "127.0.0.1" not in front:
        front = "http://localhost:5173"
    hid = create_auth_handoff(data)
    url = f"{front}/#auth/callback?handoff={hid}"
    await record_admin_action(
        actor=session.subject,
        action="tenant.impersonate",
        resource_type="tenant",
        resource_id=tenant_id,
        tenant_id=tid,
        payload={
            "note": note,
            "userId": data.get("impersonation", {}).get("userId"),
            "userEmail": data.get("impersonation", {}).get("userEmail"),
            "ttlMinutes": body.ttlMinutes,
        },
    )
    return {
        "ok": True,
        "url": url,
        "expiresIn": data.get("expiresIn"),
        "impersonation": data.get("impersonation"),
    }


@router.get("/api/dev/admin/users")
async def list_users(
    tenantId: str | None = None,
    q: str = "",
    status: str | None = None,
    role: str | None = None,
    limit: int = 50,
    offset: int = 0,
    include_deleted: bool = False,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.users")
    _require_db()

    clean_tenant_id = _clean_query_str(tenantId).strip()
    clean_q = _clean_query_str(q).strip()
    clean_status = _clean_query_str(status).strip()
    clean_role = _clean_query_str(role).strip()
    eff_limit = max(1, min(int(limit or 50), 200))
    eff_offset = max(0, int(offset or 0))

    async with get_session_factory()() as db:
        stmt = select(User)
        count_stmt = select(func.count(User.user_id))

        if not include_deleted:
            stmt = stmt.where(User.deleted_at.is_(None))
            count_stmt = count_stmt.where(User.deleted_at.is_(None))

        tid: uuid.UUID | None = None
        if clean_tenant_id:
            try:
                tid = uuid.UUID(clean_tenant_id)
                subq = select(TenantMembership.user_id).where(TenantMembership.tenant_id == tid)
                stmt = stmt.where(User.user_id.in_(subq))
                count_stmt = count_stmt.where(User.user_id.in_(subq))
            except ValueError:
                return {"users": [], "total": 0, "limit": eff_limit, "offset": eff_offset}

        if clean_role and clean_role != "all":
            role_subq = select(TenantMembership.user_id).where(TenantMembership.role == clean_role)
            if tid:
                role_subq = role_subq.where(TenantMembership.tenant_id == tid)
            stmt = stmt.where(User.user_id.in_(role_subq))
            count_stmt = count_stmt.where(User.user_id.in_(role_subq))

        if clean_status and clean_status != "all":
            stmt = stmt.where(User.status == clean_status)
            count_stmt = count_stmt.where(User.status == clean_status)

        if clean_q:
            from sqlalchemy import cast, or_, String
            pattern = f"%{clean_q}%"
            filter_q = or_(
                User.email.ilike(pattern),
                User.full_name.ilike(pattern),
                cast(User.user_id, String).ilike(pattern),
            )
            stmt = stmt.where(filter_q)
            count_stmt = count_stmt.where(filter_q)

        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(desc(User.created_at)).limit(eff_limit).offset(eff_offset)
        user_rows = (await db.execute(stmt)).scalars().all()

        user_ids = [u.user_id for u in user_rows]
        memberships: dict[uuid.UUID, dict[str, Any]] = {}
        if user_ids:
            mem_stmt = (
                select(TenantMembership, Tenant.name.label("tenant_name"))
                .outerjoin(Tenant, Tenant.tenant_id == TenantMembership.tenant_id)
                .where(TenantMembership.user_id.in_(user_ids))
            )
            if tid:
                mem_stmt = mem_stmt.where(TenantMembership.tenant_id == tid)
            for m, t_name in (await db.execute(mem_stmt)).all():
                if m.user_id not in memberships or (tid and m.tenant_id == tid):
                    memberships[m.user_id] = {
                        "role": m.role,
                        "tenantId": str(m.tenant_id),
                        "tenantName": t_name or str(m.tenant_id),
                    }

        users = []
        for u in user_rows:
            mem = memberships.get(u.user_id, {})
            users.append({
                "userId": str(u.user_id),
                "email": u.email,
                "fullName": u.full_name or "",
                "status": u.status,
                "role": mem.get("role") or "—",
                "tenantId": mem.get("tenantId"),
                "tenantName": mem.get("tenantName"),
                "createdAt": u.created_at.isoformat() if u.created_at else None,
            })

    return {"users": users, "total": total, "limit": eff_limit, "offset": eff_offset}


@router.get("/api/dev/admin/users/{user_id}")
async def user_detail(user_id: str, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.users")
    _require_db()
    uid = uuid.UUID(user_id)
    async with get_session_factory()() as db:
        user = await db.get(User, uid)
        if user is None:
            raise HTTPException(status_code=404, detail="Not found")
        mems = (await db.execute(select(TenantMembership).where(TenantMembership.user_id == uid))).scalars().all()
        last_login = (
            await db.execute(
                select(AuthEvent)
                .where(AuthEvent.user_id == uid, AuthEvent.event_type == "login")
                .order_by(desc(AuthEvent.created_at))
                .limit(1)
            )
        ).scalar_one_or_none()
    return {
        "user": {
            "userId": str(user.user_id),
            "email": user.email,
            "status": user.status,
            "fullName": user.full_name,
        },
        "memberships": [{"tenantId": str(m.tenant_id), "role": m.role} for m in mems],
        "lastLoginAt": last_login.created_at.isoformat() if last_login else None,
    }


@router.post("/api/dev/admin/users")
async def admin_create_user(body: AdminCreateUserBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.users")
    _require_db()
    temp_password = secrets.token_urlsafe(12)
    async with get_session_factory()() as db:
        user = User(
            email=body.email.strip().lower(),
            password_hash=hash_portal_password(temp_password),
            full_name=body.fullName,
            status="pending_invite",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(user)
        await db.flush()
        db.add(
            TenantMembership(
                user_id=user.user_id,
                tenant_id=uuid.UUID(body.tenantId),
                role=body.role,
                created_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()
    await record_admin_action(
        actor=session.subject,
        action="user.create",
        resource_type="user",
        resource_id=str(user.user_id),
        tenant_id=uuid.UUID(body.tenantId),
        payload={"email": body.email, "role": body.role},
    )
    return {"ok": True, "userId": str(user.user_id), "devTempPassword": temp_password}


@router.patch("/api/dev/admin/users/{user_id}")
async def patch_user(user_id: str, body: UserPatchBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.users")
    _require_db()
    uid = uuid.UUID(user_id)
    async with get_session_factory()() as db:
        user = await db.get(User, uid)
        if user is None:
            raise HTTPException(status_code=404, detail="Not found")
        user.status = body.status
        await db.commit()
    await record_admin_action(
        actor=session.subject,
        action="user.patch",
        resource_type="user",
        resource_id=user_id,
        payload={"status": body.status},
    )
    return {"ok": True}


@router.post("/api/dev/admin/users/{user_id}/reset-password")
async def admin_reset_password(user_id: str, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.users")
    _require_db()
    new_pw = secrets.token_urlsafe(12)
    uid = uuid.UUID(user_id)
    async with get_session_factory()() as db:
        user = await db.get(User, uid)
        if user is None:
            raise HTTPException(status_code=404, detail="Not found")
        user.password_hash = hash_portal_password(new_pw)
        await db.commit()
    await record_admin_action(actor=session.subject, action="user.reset_password", resource_type="user", resource_id=user_id)
    return {"ok": True, "devTempPassword": new_pw}


@router.post("/api/dev/admin/users/{user_id}/delete")
async def admin_delete_user(user_id: str, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.users")
    from server.services.saas import auth_service

    uid = uuid.UUID(user_id)
    async with get_session_factory()() as db:
        user = await db.get(User, uid)
        if user is None:
            raise HTTPException(status_code=404, detail="Not found")
        user.status = "disabled"
        user.deleted_at = datetime.now(timezone.utc)
        user.email = f"deleted+{user.user_id}@invalid.local"
        await db.execute(delete(TenantMembership).where(TenantMembership.user_id == uid))
        await db.commit()
    await auth_service.logout_all(uid)
    await record_admin_action(actor=session.subject, action="user.delete", resource_type="user", resource_id=user_id)
    return {"ok": True}


@router.get("/api/dev/admin/users/{user_id}/auth-events")
async def user_auth_events(user_id: str, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.users")
    _require_db()
    uid = uuid.UUID(user_id)
    async with get_session_factory()() as db:
        rows = (
            await db.execute(
                select(AuthEvent).where(AuthEvent.user_id == uid).order_by(desc(AuthEvent.created_at)).limit(100)
            )
        ).scalars().all()
    return {
        "events": [
            {"eventType": e.event_type, "createdAt": e.created_at.isoformat(), "ip": e.ip}
            for e in rows
        ]
    }


@router.get("/api/dev/admin/access")
async def admin_access(session: SessionData = Depends(require_dev_session)):
    """Serve the RBAC matrix straight from the authorization source of truth.

    The admin UI must never carry its own copy of this table, or the permission
    screen would drift from what the API actually enforces.
    """
    require_permission(session, "dev.admin.tenants")
    from server.auth import rbac

    roles = sorted(
        {
            ROLE_ADMINISTRATOR,
            ROLE_DEVELOPER,
            ROLE_PLATFORM_ADMIN,
            ROLE_CUSTOMER_ADMIN,
            ROLE_VOICE_ENGINEER,
            ROLE_CUSTOMER_VIEWER,
        },
        key=lambda r: r,
    )
    permissions = [
        {
            "name": name,
            "roles": sorted(allowed),
            "devOnly": name.startswith("dev."),
        }
        for name, allowed in sorted(rbac._PERMISSIONS.items())
    ]
    return {
        "roles": roles,
        "permissions": permissions,
        "currentRole": session.role,
        "currentSubject": session.subject,
        "currentPermissions": sorted(
            p["name"] for p in permissions if session.role in p["roles"]
        ),
    }


@router.get("/api/dev/admin/analytics")
async def admin_analytics(days: int = Query(30, ge=1, le=365), session: SessionData = Depends(require_dev_session)):
    """Operational analytics for maintaining the SaaS product.

    Everything here is aggregated from the real tables. No metric is estimated and
    none is hard-coded, so the page cannot quietly show a stale or invented number.
    """
    require_permission(session, "dev.admin.tenants")
    _require_db()
    since = (datetime.now(timezone.utc) - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    until = since + timedelta(days=days)
    day0 = since.date().isoformat()

    async with get_session_factory()() as db:
        async def scalar(stmt):
            return (await db.execute(stmt)).scalar()

        # Count actual conversations; browser practice sessions are not usage.
        postgres = db.get_bind().dialect.name == "postgresql"
        call_day = func.date(func.timezone("UTC", Call.started_at)) if postgres else func.date(Call.started_at)
        topup_day = func.date(func.timezone("UTC", BillingWalletTransaction.created_at)) if postgres else func.date(BillingWalletTransaction.created_at)
        daily = (
            await db.execute(
                select(
                    call_day.label("d"),
                    func.count(Call.call_id),
                    func.coalesce(func.sum(Call.duration_sec), 0),
                )
                .where(Call.started_at.isnot(None), Call.started_at >= since, Call.started_at < until, Call.is_test.is_(False))
                .group_by(call_day)
                .order_by(call_day)
            )
        ).all()
        observed_days = [
            {"date": str(r[0]), "calls": int(r[1] or 0), "seconds": int(r[2] or 0)}
            for r in daily
        ]

        day_rows = {item["date"]: item for item in observed_days}
        daily_series = [day_rows.get((since.date() + timedelta(days=offset)).isoformat(), {
            "date": (since.date() + timedelta(days=offset)).isoformat(), "calls": 0, "seconds": 0,
        }) for offset in range(days)]

        by_status = (
            await db.execute(
                select(Call.status, func.count(Call.call_id))
                .where(Call.started_at >= since, Call.started_at < until, Call.is_test.is_(False))
                .group_by(Call.status)
            )
        ).all()
        by_direction = (
            await db.execute(
                select(Call.direction, func.count(Call.call_id))
                .where(Call.started_at >= since, Call.started_at < until, Call.is_test.is_(False))
                .group_by(Call.direction)
            )
        ).all()
        by_channel = (
            await db.execute(
                select(Call.channel, func.count(Call.call_id), func.coalesce(func.sum(Call.duration_sec), 0))
                .where(Call.started_at >= since, Call.started_at < until, Call.is_test.is_(False))
                .group_by(Call.channel)
            )
        ).all()

        # Missed calls are a first-class outcome now, so surface them separately.
        missed = int(
            await scalar(
                select(func.count())
                .select_from(CallAttempt)
                .where(CallAttempt.started_at >= since, CallAttempt.started_at < until, CallAttempt.status.in_(("missed", "no_answer")))
            )
            or 0
        )

        # Money in: wallet top-ups only. Debits are spend, not revenue.
        topups = (
            await db.execute(
                select(
                    topup_day.label("d"),
                    func.coalesce(func.sum(BillingWalletTransaction.amount_cents), 0),
                    func.coalesce(func.sum(BillingWalletTransaction.amount_inr_paise), 0),
                )
                .where(
                    BillingWalletTransaction.kind.in_(("topup", "top_up", "deposit")),
                    BillingWalletTransaction.created_at >= since,
                    BillingWalletTransaction.created_at < until,
                )
                .group_by(topup_day)
                .order_by(topup_day)
            )
        ).all()

        tenants_total = int(await scalar(select(func.count()).select_from(Tenant)) or 0)
        tenants_active = int(
            await scalar(
                select(func.count()).select_from(Tenant).where(Tenant.status == "active")
            )
            or 0
        )
        users_total = int(
            await scalar(
                select(func.count()).select_from(User).where(User.deleted_at.is_(None))
            )
            or 0
        )
        numbers_active = int(
            await scalar(
                select(func.count())
                .select_from(PhoneNumber)
                .where(PhoneNumber.released_at.is_(None))
            )
            or 0
        )
        purchases_failed = int(
            await scalar(
                select(func.count())
                .select_from(NumberPurchase)
                .where(NumberPurchase.status == "failed")
            )
            or 0
        )
        balance_cents = int(
            await scalar(select(func.coalesce(func.sum(BillingWallet.balance_cents), 0))) or 0
        )
        balance_inr_paise = int(
            await scalar(select(func.coalesce(func.sum(BillingWallet.balance_inr_paise), 0))) or 0
        )
        top_tenants = (
            await db.execute(
                select(Tenant.name, func.count(Call.call_id))
                .select_from(Call)
                .join(Tenant, Tenant.tenant_id == Call.tenant_id)
                .where(Call.started_at >= since, Call.started_at < until, Call.is_test.is_(False))
                .group_by(Tenant.tenant_id, Tenant.name)
                .order_by(func.count(Call.call_id).desc())
                .limit(8)
            )
        ).all()

    return {
        "windowDays": days,
        "since": since.isoformat(),
        "totals": {
            "calls": sum(d["calls"] for d in daily_series),
            "seconds": sum(d["seconds"] for d in daily_series),
            "missedCalls": missed,
            "tenants": tenants_total,
            "tenantsActive": tenants_active,
            "users": users_total,
            "activeNumbers": numbers_active,
            "failedPurchases": purchases_failed,
            "walletBalanceCents": balance_cents,
            "walletBalanceInrPaise": balance_inr_paise,
        },
        "callsByDay": daily_series,
        "callsByStatus": {str(k or "unknown"): int(v or 0) for k, v in by_status},
        "callsByDirection": {str(k or "unknown"): int(v or 0) for k, v in by_direction},
        "callsByChannel": {
            str(k or "unknown"): {"calls": int(v or 0), "seconds": int(s or 0)}
            for k, v, s in by_channel
        },
        "topUpsByDay": [
            {"date": str(r[0]), "cents": int(r[1] or 0), "inrPaise": int(r[2] or 0)}
            for r in topups
        ],
        "topTenantsByCalls": [{"name": str(r[0]), "calls": int(r[1] or 0)} for r in top_tenants],
        "emptyDay": day0,
    }


@router.post("/api/dev/admin/memberships")
async def admin_membership(body: MembershipBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.users")
    _require_db()
    async with get_session_factory()() as db:
        db.add(
            TenantMembership(
                user_id=uuid.UUID(body.userId),
                tenant_id=uuid.UUID(body.tenantId),
                role=body.role,
                created_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()
    await record_admin_action(
        actor=session.subject,
        action="membership.create",
        resource_type="membership",
        resource_id=f"{body.userId}:{body.tenantId}",
        tenant_id=uuid.UUID(body.tenantId),
        payload=body.model_dump(),
    )
    return {"ok": True}


@router.get("/api/dev/admin/phone-assignments")
async def phone_assignments(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.numbers")
    _require_db()
    from server.services.saas.number_inventory import INVENTORY_TENANT_NAME, ensure_platform_inventory_tenant
    from server.services.telephony import active_telephony_provider

    active_prov = active_telephony_provider()
    inventory_tid = await ensure_platform_inventory_tenant()
    async with get_session_factory()() as db:
        rows = (
            await db.execute(
                select(PhoneNumber, Tenant, Agent, NumberPurchase, BillingWallet)
                .join(Tenant, Tenant.tenant_id == PhoneNumber.tenant_id)
                .outerjoin(Agent, Agent.agent_id == PhoneNumber.agent_id)
                .outerjoin(NumberPurchase, NumberPurchase.id == PhoneNumber.purchase_id)
                .outerjoin(BillingWallet, BillingWallet.tenant_id == PhoneNumber.tenant_id)
                .where(
                    PhoneNumber.released_at.is_(None),
                    # Inventory pool is not a customer assignment — shown in the pool UI.
                    PhoneNumber.tenant_id != inventory_tid,
                )
                .order_by(desc(PhoneNumber.created_at))
                .limit(500)
            )
        ).all()
    assignments = []
    for pn, t, a, np, w in rows:
        prov = "telnyx" if (getattr(pn, "telnyx_number_id", None) and getattr(pn, "telnyx_number_id", None) != "carrier_platform") else "vobiz"
        if getattr(pn, "carrier_number_id", None) or str(pn.e164).startswith("+91"):
            prov = "vobiz"
        if prov != active_prov:
            continue
        assignments.append({
            "e164": pn.e164,
            "numberId": str(pn.id),
            "tenant": t.name,
            "tenantId": str(t.tenant_id),
            "tenantPlan": t.plan,
            "tenantStatus": t.status,
            "agent": a.name if a else None,
            "agentId": str(pn.agent_id) if pn.agent_id else None,
            "purchaseStatus": np.status if np else None,
            "stripeSubscriptionId": pn.stripe_subscription_id,
            "telnyxNumberId": pn.telnyx_number_id,
            "carrierNumberId": getattr(pn, "carrier_number_id", None),
            "provider": prov,
            "status": pn.status,
            "billingSource": pn.billing_source,
            "walletBalanceUsd": round((w.balance_cents or 0) / 100.0, 2) if w else 0,
            "walletBalanceInr": round((w.balance_inr_paise or 0) / 100.0, 2) if w else 0,
            "walletCurrency": ((w.currency if w else None) or "usd").upper(),
            "createdAt": pn.created_at.isoformat() if pn.created_at else None,
        })
    return {
        "assignments": assignments,
        "inventoryTenantName": INVENTORY_TENANT_NAME,
        "activeProvider": active_prov,
    }


@router.get("/api/dev/admin/numbers/pool")
async def number_pool(session: SessionData = Depends(require_dev_session)):
    """All account DIDs for the active telephony provider (carrier + DB) — pick one then assign."""
    require_permission(session, "dev.admin.numbers")
    _require_db()
    from server.services.saas.number_inventory import INVENTORY_TENANT_NAME, ensure_platform_inventory_tenant
    from server.services.telephony import active_telephony_provider

    active_prov = active_telephony_provider()
    inventory_tid = await ensure_platform_inventory_tenant()
    inventory_tid_s = str(inventory_tid)
    by_e164: dict[str, dict[str, Any]] = {}
    real_carrier_numbers: set[str] = set()

    # 1. Fetch real account numbers directly from the active carrier API
    if active_prov == "telnyx":
        try:
            from server.services.telnyx_client import TelnyxClient

            for row in await TelnyxClient().list_phone_numbers():
                phone = str(
                    row.get("phone_number")
                    or (row.get("attributes") or {}).get("phone_number")
                    or ""
                ).strip()
                if not phone:
                    continue
                real_carrier_numbers.add(phone)
                tid = str(row.get("id") or "")
                by_e164[phone] = {
                    "e164": phone,
                    "numberId": None,
                    "telnyxNumberId": tid or None,
                    "carrierNumberId": None,
                    "provider": "telnyx",
                    "tenantId": None,
                    "tenantName": None,
                    "status": "unassigned",
                    "source": "telnyx",
                    "inInventory": False,
                    "available": True,
                }
        except Exception as exc:
            logger.debug("[ADMIN] telnyx pool list skipped: %s", exc)
    elif active_prov == "vobiz":
        try:
            from server.services.vobiz_client import VobizClient

            v_nums = await VobizClient().list_account_numbers()
            for row in (v_nums or []):
                phone = str(row.get("e164") or row.get("phone_number") or "").strip()
                if not phone:
                    continue
                real_carrier_numbers.add(phone)
                by_e164[phone] = {
                    "e164": phone,
                    "numberId": None,
                    "telnyxNumberId": None,
                    "carrierNumberId": str(row.get("id") or ""),
                    "provider": "vobiz",
                    "tenantId": None,
                    "tenantName": None,
                    "status": "unassigned",
                    "source": "vobiz",
                    "inInventory": False,
                    "available": True,
                }
        except Exception as exc:
            logger.debug("[ADMIN] vobiz pool list skipped: %s", exc)

    # 2. Correlate with database records for the active provider
    async with get_session_factory()() as db:
        rows = (
            await db.execute(
                select(PhoneNumber, Tenant)
                .outerjoin(Tenant, Tenant.tenant_id == PhoneNumber.tenant_id)
                .where(PhoneNumber.released_at.is_(None))
            )
        ).all()
        for pn, t in rows:
            prov = "telnyx" if getattr(pn, "telnyx_number_id", None) and getattr(pn, "telnyx_number_id", None) != "carrier_platform" else "vobiz"
            if getattr(pn, "carrier_number_id", None) or str(pn.e164).startswith("+91"):
                prov = "vobiz"
            # Strict provider isolation: never mix carriers
            if prov != active_prov:
                continue

            tenant_gone = t is None or t.deleted_at is not None or getattr(t, "status", "active") == "cancelled"
            in_inventory = pn.tenant_id == inventory_tid or (t is not None and t.name == INVENTORY_TENANT_NAME)

            # If parked in inventory, only mark available if verified in real carrier account
            if in_inventory and real_carrier_numbers and pn.e164 not in real_carrier_numbers:
                continue

            is_avail = (tenant_gone or (in_inventory and pn.status == "available") or not pn.tenant_id)
            existing = by_e164.get(pn.e164)
            if existing:
                existing["numberId"] = str(pn.id)
                existing["status"] = pn.status
                existing["inInventory"] = in_inventory
                existing["tenantId"] = None if tenant_gone or in_inventory else (str(pn.tenant_id) if pn.tenant_id else None)
                existing["tenantName"] = INVENTORY_TENANT_NAME if in_inventory else (None if tenant_gone else (t.name if t else None))
                existing["source"] = f"{active_prov}+inventory" if in_inventory else f"{active_prov}+database"
                existing["available"] = is_avail
            elif pn.e164 in real_carrier_numbers or (pn.tenant_id and not in_inventory):
                by_e164[pn.e164] = {
                    "e164": pn.e164,
                    "numberId": str(pn.id),
                    "telnyxNumberId": pn.telnyx_number_id,
                    "carrierNumberId": getattr(pn, "carrier_number_id", None),
                    "provider": active_prov,
                    "tenantId": None if tenant_gone or in_inventory else (str(pn.tenant_id) if pn.tenant_id else None),
                    "tenantName": (INVENTORY_TENANT_NAME if in_inventory else (None if tenant_gone else (t.name if t else None))),
                    "status": pn.status,
                    "source": "inventory" if in_inventory else "database",
                    "inInventory": in_inventory,
                    "available": is_avail,
                }

            if pn.vobiz_account_scope == "tenant" and pn.e164 in by_e164:
                # Closing a tenant never returns its provider-owned resources to
                # our master pool. Keep ownership visible until real release.
                by_e164[pn.e164].update(tenantId=str(pn.tenant_id), inInventory=False, available=False)

    for item in by_e164.values():
        if item.get("inInventory"):
            item["available"] = (item.get("status") == "available")
            item["tenantId"] = None
        else:
            item["available"] = not bool(item.get("tenantId"))

    return {
        "numbers": sorted(
            [n for n in by_e164.values() if n.get("provider") == active_prov],
            key=lambda n: (0 if n.get("available") else 1, n["e164"]),
        ),
        "inventoryTenantId": inventory_tid_s,
        "activeProvider": active_prov,
    }


@router.post("/api/dev/admin/numbers/allocate")
async def allocate_number(body: AllocateNumberBody, session: SessionData = Depends(require_dev_session)):
    """Assign an existing DID (Telnyx or already in DB) to a tenant. Creates wallet if missing."""
    require_permission(session, "dev.admin.numbers")
    _require_db()
    from server.services.telephony import active_telephony_provider
    active_prov = active_telephony_provider()
    e164 = body.e164.strip()
    if not e164.startswith("+"):
        raise HTTPException(status_code=400, detail="E.164 required (e.g. +15551234567)")
    tid = uuid.UUID(body.tenantId)
    confirmed_carrier_id = None
    if active_prov == "vobiz":
        from server.services.saas.voice_kyc_service import assert_voice_kyc_approved, vobiz_client_for_tenant
        await assert_voice_kyc_approved(tid, action="assign a phone number")
        child = await vobiz_client_for_tenant(tid)
        owned = await child.list_account_numbers(search=e164, limit=100)
        confirmed_carrier_id = next((str(n["id"]) for n in owned if n.get("e164") == e164
                                    and n.get("account_id") == child.auth_id and n.get("id")
                                    and n.get("status") == "active"), None)
        if not confirmed_carrier_id:
            raise HTTPException(status_code=409, detail="number_not_owned_by_customer_account")
    async with get_session_factory()() as db:
        tenant = await db.get(Tenant, tid)
        if tenant is None or tenant.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Tenant not found")
        existing = (
            await db.execute(
                select(PhoneNumber).where(PhoneNumber.e164 == e164, PhoneNumber.released_at.is_(None))
            )
        ).scalar_one_or_none()
        if existing is not None:
            if active_prov == "vobiz" and existing.tenant_id != tid:
                raise HTTPException(status_code=409, detail="number_already_assigned")
            existing.tenant_id = tid
            if active_prov == "telnyx":
                existing.telnyx_number_id = body.telnyxNumberId or getattr(existing, "telnyx_number_id", None) or "carrier_platform"
            elif active_prov == "vobiz":
                existing.carrier_number_id = confirmed_carrier_id
                existing.vobiz_account_scope = "tenant"
                existing.vobiz_account_tenant_id = tid
                existing.telnyx_number_id = None
            existing.status = "active"
            existing.inbound_enabled = True
            existing.outbound_enabled = True
            pn = existing
        else:
            pn = PhoneNumber(
                tenant_id=tid,
                e164=e164,
                status="active",
                billing_source="manual",
                telnyx_number_id=(body.telnyxNumberId or "carrier_platform") if active_prov == "telnyx" else None,
                carrier_number_id=confirmed_carrier_id if active_prov == "vobiz" else None,
                vobiz_account_scope="tenant" if active_prov == "vobiz" else None,
                vobiz_account_tenant_id=tid if active_prov == "vobiz" else None,
                inbound_enabled=True,
                outbound_enabled=True,
                created_at=datetime.now(timezone.utc),
            )
            db.add(pn)
        wallet = await db.get(BillingWallet, tid)
        if wallet is None:
            db.add(
                BillingWallet(
                    tenant_id=tid,
                    balance_cents=0,
                    balance_inr_paise=0,
                    currency="usd",
                    updated_at=datetime.now(timezone.utc),
                )
            )
        await db.commit()
        await db.refresh(pn)
    await record_admin_action(
        actor=session.subject,
        action="number.allocate",
        resource_type="phone_number",
        resource_id=str(pn.id),
        tenant_id=tid,
        payload={"e164": e164, "provider": active_prov, "telnyxNumberId": body.telnyxNumberId},
    )
    return {"ok": True, "numberId": str(pn.id), "e164": e164, "tenantId": str(tid), "provider": active_prov}


@router.patch("/api/dev/admin/numbers/{number_id}")
async def patch_number(number_id: str, body: NumberPatchBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.numbers")
    _require_db()
    nid = uuid.UUID(number_id)
    async with get_session_factory()() as db:
        pn = await db.get(PhoneNumber, nid)
        if pn is None:
            raise HTTPException(status_code=404, detail="Not found")
        if body.tenantId is not None:
            if pn.vobiz_account_scope == "tenant" and pn.tenant_id != uuid.UUID(body.tenantId):
                raise HTTPException(status_code=409, detail="Customer-owned numbers require carrier reconciliation before reassignment")
            pn.tenant_id = uuid.UUID(body.tenantId)
            wallet = await db.get(BillingWallet, pn.tenant_id)
            if wallet is None:
                db.add(
                    BillingWallet(
                        tenant_id=pn.tenant_id,
                        balance_cents=0,
                        balance_inr_paise=0,
                        currency="usd",
                        updated_at=datetime.now(timezone.utc),
                    )
                )
        if body.agentId is not None:
            if body.agentId:
                agent = await db.get(Agent, uuid.UUID(body.agentId))
                if agent is None or agent.tenant_id != pn.tenant_id:
                    raise HTTPException(status_code=404, detail="agent_not_found")
            pn.agent_id = uuid.UUID(body.agentId) if body.agentId else None
        await db.commit()
    await record_admin_action(
        actor=session.subject,
        action="number.patch",
        resource_type="phone_number",
        resource_id=number_id,
        tenant_id=uuid.UUID(body.tenantId) if body.tenantId else None,
        payload=body.model_dump(exclude_none=True),
    )
    return {"ok": True}


class ReleaseNumberBody(BaseModel):
    note: str = Field("", max_length=500)


@router.post("/api/dev/admin/numbers/{number_id}/release")
async def release_number(
    number_id: str,
    session: SessionData = Depends(require_dev_session),
    body: ReleaseNumberBody | None = None,
):
    """Return a DID to the Platform inventory pool (admin-owned, for sale again)."""
    require_permission(session, "dev.admin.numbers")
    _require_db()
    from server.services.saas.number_inventory import move_to_inventory

    statement = ((body.note if body else "") or "").strip()
    if len(statement) < 8:
        raise HTTPException(
            status_code=400,
            detail="Admin statement required (at least 8 characters) before releasing a number.",
        )
    nid = uuid.UUID(number_id)
    async with get_session_factory()() as db:
        pn = await db.get(PhoneNumber, nid)
        if pn is None:
            raise HTTPException(status_code=404, detail="Not found")
        e164 = pn.e164
        telnyx_id = pn.telnyx_number_id
        prev_tenant = pn.tenant_id
    moved = await move_to_inventory(number_id=nid, e164=e164, telnyx_number_id=telnyx_id)
    await record_admin_action(
        actor=session.subject,
        action="number.release_to_inventory",
        resource_type="phone_number",
        resource_id=number_id,
        tenant_id=prev_tenant,
        payload={"e164": e164, "note": statement, "inventory": moved},
    )
    return {"ok": True, "inventory": moved}


class InventoryParkBody(BaseModel):
    e164: str
    telnyxNumberId: str | None = None


@router.post("/api/dev/admin/numbers/inventory")
async def park_in_inventory(body: InventoryParkBody, session: SessionData = Depends(require_dev_session)):
    """Park any DID (by E.164) in the admin inventory pool."""
    require_permission(session, "dev.admin.numbers")
    _require_db()
    from server.services.saas.number_inventory import move_to_inventory

    e164 = body.e164.strip()
    if not e164.startswith("+"):
        raise HTTPException(status_code=400, detail="E.164 required")
    moved = await move_to_inventory(e164=e164, telnyx_number_id=body.telnyxNumberId)
    await record_admin_action(
        actor=session.subject,
        action="number.park_inventory",
        resource_type="phone_number",
        resource_id=moved["numberId"],
        payload={"e164": e164},
    )
    return {"ok": True, "inventory": moved}


@router.get("/api/dev/admin/purchases")
async def list_purchases(
    status: str | None = None,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.billing")
    _require_db()
    async with get_session_factory()() as db:
        stmt = select(NumberPurchase).order_by(desc(NumberPurchase.created_at)).limit(200)
        if status:
            stmt = stmt.where(NumberPurchase.status == status)
        rows = (await db.execute(stmt)).scalars().all()
    return {
        "purchases": [
            {
                "purchaseId": str(p.id),
                "tenantId": str(p.tenant_id),
                "e164": p.e164,
                "status": p.status,
                "createdAt": p.created_at.isoformat(),
            }
            for p in rows
        ]
    }


@router.post("/api/dev/admin/purchases/{purchase_id}/retry-provision")
async def retry_provision(purchase_id: str, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.billing")
    _require_db()
    pid = uuid.UUID(purchase_id)
    async with get_session_factory()() as db:
        purchase = await db.get(NumberPurchase, pid)
        if purchase is None:
            raise HTTPException(status_code=404, detail="Not found")
        purchase.status = "paid"
        job = (await db.execute(select(ProvisionJob).where(ProvisionJob.purchase_id == pid))).scalar_one_or_none()
        if job:
            job.status = "queued"
        await db.commit()
    await enqueue_provision(pid)
    await record_admin_action(
        actor=session.subject,
        action="purchase.retry_provision",
        resource_type="purchase",
        resource_id=purchase_id,
        tenant_id=purchase.tenant_id,
    )
    return {"ok": True}


@router.post("/api/dev/admin/purchases/{purchase_id}/refund")
async def refund_purchase(purchase_id: str, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.billing")
    settings = get_settings()
    _require_db()
    pid = uuid.UUID(purchase_id)
    refund_wallet = False
    refund_tenant = None
    refund_user = None
    async with get_session_factory()() as db:
        purchase = await db.get(NumberPurchase, pid)
        if purchase is None:
            raise HTTPException(status_code=404, detail="Not found")
        refund_tenant = purchase.tenant_id
        refund_user = purchase.user_id
        refund_wallet = True
        purchase.status = "refunded"
        await db.commit()

    if refund_wallet and refund_tenant:
        from server.services.saas.billing_wallet_service import refund_did_purchase

        await refund_did_purchase(
            refund_tenant,
            user_id=refund_user,
            purchase_id=pid,
        )

    await record_admin_action(
        actor=session.subject,
        action="purchase.refund",
        resource_type="purchase",
        resource_id=purchase_id,
        tenant_id=refund_tenant,
    )
    return {"ok": True}


class WalletAdjustBody(BaseModel):
    """Adjust a wallet in USD.

    The INR field is accepted for backwards compatibility; when only it is sent
    the amount is converted at the chargeable FX rate so old clients keep working
    without the admin panel ever having to think in rupees.
    """

    tenantId: str
    amountUsdCents: int | None = Field(None, ge=-50_000_000, le=50_000_000)
    amountInrPaise: int | None = Field(None, ge=-50_000_000, le=50_000_000)
    reason: str = Field("admin_adjust", max_length=40)
    note: str = Field("", max_length=500)


@router.get("/api/dev/admin/wallets")
async def list_wallets(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.billing")
    _require_db()
    async with get_session_factory()() as db:
        rows = (
            await db.execute(
                select(Tenant, BillingWallet)
                .outerjoin(BillingWallet, BillingWallet.tenant_id == Tenant.tenant_id)
                .where(Tenant.deleted_at.is_(None))
                .order_by(desc(Tenant.created_at))
                .limit(200)
            )
        ).all()
        # Same auto-create path as list_tenants so billing/numbers stay aligned after restarts.
        created = False
        synced: list[tuple[Any, Any]] = []
        for tenant, wallet in rows:
            if wallet is None:
                wallet = BillingWallet(
                    tenant_id=tenant.tenant_id,
                    balance_cents=0,
                    balance_inr_paise=0,
                    currency="usd",
                    updated_at=datetime.now(timezone.utc),
                )
                db.add(wallet)
                created = True
            synced.append((tenant, wallet))
        if created:
            await db.commit()
            for _, wallet in synced:
                if wallet is not None:
                    await db.refresh(wallet)
        rows = synced
    from server.services.saas.billing_rates import load_current_rates

    fx = float((await load_current_rates())["fx_rate_inr"])
    wallets = []
    for tenant, wallet in rows:
        paise = int(wallet.balance_inr_paise or 0) if wallet else 0
        cents = int(wallet.balance_cents or 0) if wallet else 0
        # A Razorpay top-up credits INR only, so show the converted dollar figure
        # rather than an empty USD column next to a full rupee balance.
        balance_usd = cents / 100 if cents > 0 else round((paise / 100.0) / fx, 2)
        wallets.append(
            {
                "tenantId": str(tenant.tenant_id),
                "name": tenant.name,
                "status": getattr(tenant, "status", "active"),
                "balanceInrPaise": paise,
                "balanceInr": paise / 100,
                "balanceCents": cents,
                "balanceUsd": balance_usd,
                "currency": "USD",
                "walletCurrency": (wallet.currency if wallet else "usd") or "usd",
                "updatedAt": wallet.updated_at.isoformat() if wallet and wallet.updated_at else None,
            }
        )
    return {"wallets": wallets, "currency": "USD", "fxRateInr": fx}


@router.get("/api/dev/admin/billing/cost-insights")
async def billing_cost_insights(days: int = Query(30, ge=1, le=90), session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.billing")
    _require_db()
    from server.services.saas.cost_insights import load_cost_insights
    return await load_cost_insights(days)


@router.get("/api/dev/admin/calls")
async def list_admin_calls(
    q: Optional[str] = Query(None, description="Search short ID, full UUID, agent, or tenant"),
    tier: Optional[str] = Query(None, description="Filter tier: low, medium, premium"),
    channel: Optional[str] = Query(None, description="Filter channel: pstn, browser"),
    tenant_id: Optional[str] = Query(None),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.billing")
    _require_db()
    from server.call.call_ledger import call_ledger
    from server.db.models.entities import Agent, Call, Tenant
    from server.services.saas.billing_rates import load_current_rates
    from sqlalchemy import cast, or_, String

    rates = await load_current_rates()
    fx = float(rates.get("fx_rate_inr") or 0) or None

    factory = get_session_factory()
    async with factory() as db:
        stmt = (
            select(
                Call.call_id,
                Call.tenant_id,
                Call.agent_id,
                Call.session_id,
                Call.channel,
                Call.tier,
                Call.direction,
                Call.status,
                Call.duration_sec,
                Call.applied_rate_usd_micros_per_min,
                Call.applied_rate_inr_paise_per_min,
                Call.created_at,
                Call.ended_at,
                Call.end_reason,
                Call.status_tags,
                Tenant.name.label("tenant_name"),
                Agent.name.label("agent_name"),
            )
            .join(Tenant, Tenant.tenant_id == Call.tenant_id, isouter=True)
            .join(Agent, Agent.agent_id == Call.agent_id, isouter=True)
        )

        q_str = str(q).strip() if isinstance(q, str) and q.strip() else None
        tier_str = str(tier).strip().lower() if isinstance(tier, str) and tier.strip() else None
        channel_str = str(channel).strip().lower() if isinstance(channel, str) and channel.strip() else None
        tenant_str = str(tenant_id).strip() if isinstance(tenant_id, str) and tenant_id.strip() else None

        if q_str:
            search = f"%{q_str.lower()}%"
            stmt = stmt.where(
                or_(
                    cast(Call.call_id, String).ilike(search),
                    Call.session_id.ilike(search),
                    Tenant.name.ilike(search),
                    Agent.name.ilike(search),
                )
            )
        if tier_str and tier_str != "all":
            if tier_str == "medium":
                stmt = stmt.where(or_(Call.tier == "medium", Call.tier.ilike("medium_%"), Call.tier.ilike("%standard%")))
            elif tier_str == "low":
                stmt = stmt.where(or_(Call.tier == "low", Call.tier.ilike("low_%"), Call.tier.ilike("%economical%")))
            elif tier_str == "premium":
                stmt = stmt.where(or_(Call.tier == "premium", Call.tier.ilike("premium_%"), Call.tier.ilike("%flagship%")))
            else:
                stmt = stmt.where(Call.tier == tier_str)
        if channel_str and channel_str != "all":
            stmt = stmt.where(Call.channel == channel_str)
        if tenant_str:
            try:
                t_uuid = uuid.UUID(tenant_str)
                stmt = stmt.where(Call.tenant_id == t_uuid)
            except ValueError:
                pass

        limit_val = int(limit) if isinstance(limit, (int, str)) and str(limit).isdigit() else 30
        offset_val = int(offset) if isinstance(offset, (int, str)) and str(offset).isdigit() else 0
        limit_val = max(1, min(100, limit_val))
        offset_val = max(0, offset_val)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_res = await db.execute(count_stmt)
        total = total_res.scalar_one() or 0

        items_stmt = stmt.order_by(Call.created_at.desc()).offset(offset_val).limit(limit_val)
        res = await db.execute(items_stmt)
        rows = res.all()

        from server.services.dev_runtime import effective_app_environment
        from server.services.saas.admin_call_costs import build_call_costs
        from server.services.saas.voice_stack_profiles import _native_tier_retail_rate, load_profile_records
        tier_records = await load_profile_records(effective_app_environment(), None)

        calls_data = []
        for r in rows:
            cid_str = str(r.call_id)
            meta = call_ledger.read_meta(cid_str) or {}
            duration_sec = float(r.duration_sec or 0.0)
            channel_norm = str(r.channel or "pstn").strip().lower()
            tier_slug = str(r.tier or "medium").strip().lower()
            if channel_norm == "browser":
                catalog_rate = {
                    "inrPaisePerMin": rates.get("web_agent_rate_inr_paise_per_min"),
                    "usdMicrosPerMin": rates.get("web_agent_rate_usd_micros_per_min"),
                }
            else:
                catalog_rate = _native_tier_retail_rate(rates, tier_slug, record=tier_records.get(tier_slug))
            costs = build_call_costs(
                meta=meta,
                channel=channel_norm,
                tier=tier_slug,
                duration_sec=duration_sec,
                applied_inr_paise=r.applied_rate_inr_paise_per_min,
                applied_usd_micros=r.applied_rate_usd_micros_per_min,
                current_rates=rates,
                tier_rate=catalog_rate,
            )
            supplier = costs["supplier"]
            stages = supplier["stages"]
            failure_last = meta.get("agent_failure_last") if isinstance(meta.get("agent_failure_last"), dict) else {}

            calls_data.append({
                "callId": cid_str,
                "shortId": cid_str[:8].upper(),
                "sessionId": r.session_id,
                "tenantId": str(r.tenant_id) if r.tenant_id else None,
                "tenantName": r.tenant_name or (f"Tenant {str(r.tenant_id)[:8]}" if r.tenant_id else "Unknown Tenant"),
                "agentId": str(r.agent_id) if r.agent_id else None,
                "agentName": r.agent_name or "Agent",
                "channel": r.channel or "pstn",
                "tier": r.tier or "premium",
                "direction": r.direction or "inbound",
                "status": r.status or "completed",
                "durationSec": int(duration_sec),
                "durationFormatted": f"{int(duration_sec // 60)}m {int(duration_sec % 60)}s" if duration_sec >= 60 else f"{int(duration_sec)}s",
                "createdAt": r.created_at.isoformat() if r.created_at else None,
                "endedAt": r.ended_at.isoformat() if r.ended_at else None,
                "retailInr": costs["retail"]["totalBilledInr"],
                "retailUsd": costs["retail"]["totalBilledUsd"],
                "supplierCostInr": supplier["totalInr"],
                "supplierCostUsd": supplier["totalUsd"],
                "marginInr": costs["margin"]["inr"],
                "marginUsd": costs["margin"]["usd"],
                "marginPercent": costs["margin"]["percent"],
                "costStatus": costs["status"],
                "missingCost": costs["missing"],
                "retailRateSource": costs["retail"]["source"],
                "carrierCostStatus": supplier["carrier"]["status"],
                "fxRateInr": costs["fxRateInr"],
                "agentFailureCount": int(meta.get("agent_failure_count") or 0),
                "agentFailureLast": failure_last or None,
                "statusTags": list(r.status_tags or []),
                "breakdown": {
                    "carrierInr": supplier["carrier"]["amountInr"],
                    "sttInr": stages["stt"]["costInr"],
                    "llmInr": stages["llm"]["costInr"],
                    "ttsInr": stages["tts"]["costInr"],
                    "otherInr": supplier["other"]["costInr"],
                },
            })

        return {
            "ok": True,
            "total": total,
            "limit": limit_val,
            "offset": offset_val,
            "fxRateInr": fx,
            "calls": calls_data,
        }


@router.get("/api/dev/admin/calls/{call_id}/detail")
async def get_admin_call_detail(
    call_id: str,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.billing")
    _require_db()
    from server.call.call_ledger import call_ledger
    from server.db.models.entities import Agent, Call, Tenant
    from server.services.saas.billing_rates import load_current_rates
    from sqlalchemy import cast, or_, String

    cid_str = call_id.strip()
    rates = await load_current_rates()

    factory = get_session_factory()
    async with factory() as db:
        stmt = (
            select(
                Call,
                Tenant.name.label("tenant_name"),
                Agent.name.label("agent_name"),
            )
            .join(Tenant, Tenant.tenant_id == Call.tenant_id, isouter=True)
            .join(Agent, Agent.agent_id == Call.agent_id, isouter=True)
            .where(
                or_(
                    cast(Call.call_id, String) == cid_str,
                    cast(Call.call_id, String).ilike(f"{cid_str}%"),
                    Call.session_id == cid_str,
                )
            )
            .limit(1)
        )
        res = await db.execute(stmt)
        row = res.first()
        if not row:
            raise HTTPException(status_code=404, detail="Call record not found")

        call, tenant_name, agent_name = row
        exact_cid = str(call.call_id)
        meta = call_ledger.read_meta(exact_cid) or {}
        review = call_ledger.review_fields(exact_cid)
        failed_turns = call_ledger.read_failed_turns(exact_cid)

        duration_sec = float(call.duration_sec or 0.0)
        channel_norm = str(call.channel or "pstn").strip().lower()
        tier_slug = str(call.tier or "medium").strip().lower()

        from server.services.dev_runtime import effective_app_environment
        from server.services.saas.admin_call_costs import build_call_costs
        from server.services.saas.voice_stack_profiles import _native_tier_retail_rate, load_profile_records

        tier_records = await load_profile_records(effective_app_environment(), None)
        if channel_norm == "browser":
            catalog_rate = {
                "inrPaisePerMin": rates.get("web_agent_rate_inr_paise_per_min"),
                "usdMicrosPerMin": rates.get("web_agent_rate_usd_micros_per_min"),
            }
        else:
            catalog_rate = _native_tier_retail_rate(rates, tier_slug, record=tier_records.get(tier_slug))

        costs = build_call_costs(
            meta=meta,
            channel=channel_norm,
            tier=tier_slug,
            duration_sec=duration_sec,
            applied_inr_paise=call.applied_rate_inr_paise_per_min,
            applied_usd_micros=call.applied_rate_usd_micros_per_min,
            current_rates=rates,
            tier_rate=catalog_rate,
        )
        supplier = costs["supplier"]
        measured_stages = supplier["stages"]
        usage = meta.get("usage") if isinstance(meta.get("usage"), dict) else {}
        stage_usage = meta.get("stage_usage") if isinstance(meta.get("stage_usage"), dict) else {}
        cost_snapshot = meta.get("provider_cost_snapshot") if isinstance(meta.get("provider_cost_snapshot"), dict) else {}
        resolved_stack = meta.get("resolved_stack") if isinstance(meta.get("resolved_stack"), dict) else {}

        def stage_label(stage: str, *fallbacks: Any) -> str | None:
            stage_row = measured_stages.get(stage) or {}
            for component in stage_row.get("components") or []:
                if isinstance(component, dict) and component.get("rateId"):
                    return str(component["rateId"])
            for selection in ((cost_snapshot.get("stages") or {}).get(stage), resolved_stack.get(stage)):
                if isinstance(selection, dict) and (selection.get("provider") or selection.get("model")):
                    label = ":".join(
                        str(selection[key]) for key in ("provider", "model") if selection.get(key)
                    )
                    if label:
                        return label
            for fallback in fallbacks:
                if fallback not in (None, ""):
                    return str(fallback)
            return None

        stt_usage = stage_usage.get("stt") if isinstance(stage_usage.get("stt"), dict) else {}
        llm_usage = stage_usage.get("llm") if isinstance(stage_usage.get("llm"), dict) else {}
        tts_usage = stage_usage.get("tts") if isinstance(stage_usage.get("tts"), dict) else {}
        tts_chars = int(tts_usage.get("input_characters") or 0) + int(tts_usage.get("prewarm_input_characters") or 0)
        carrier = supplier["carrier"]
        carrier_raw = carrier.get("raw") if isinstance(carrier.get("raw"), dict) else {}
        billable_seconds = carrier_raw.get("billable_seconds")
        if billable_seconds is None:
            billable_seconds = int(duration_sec)

        return {
            "ok": True,
            "callId": exact_cid,
            "shortId": exact_cid[:8].upper(),
            "sessionId": call.session_id,
            "tenant": {
                "id": str(call.tenant_id) if call.tenant_id else None,
                "name": tenant_name or (f"Tenant {str(call.tenant_id)[:8]}" if call.tenant_id else "Unknown Tenant"),
            },
            "agent": {
                "id": str(call.agent_id) if call.agent_id else None,
                "name": agent_name or "Agent",
            },
            "tier": call.tier or "premium",
            "channel": call.channel or "pstn",
            "direction": call.direction or "inbound",
            "status": call.status or "completed",
            "endReason": call.end_reason or meta.get("end_reason"),
            "statusTags": list(call.status_tags or []),
            "agentFailureCount": len(failed_turns),
            "agentFailures": [
                {
                    key: row.get(key)
                    for key in (
                        "at",
                        "finish_reason",
                        "error_type",
                        "error",
                        "retry_used",
                        "watchdog_retry",
                        "tool_wait",
                        "delivered",
                        "partial_text",
                        "transcript",
                    )
                }
                for row in failed_turns[-10:]
            ],
            "durationSec": int(duration_sec),
            "durationFormatted": f"{int(duration_sec // 60)}m {int(duration_sec % 60)}s" if duration_sec >= 60 else f"{int(duration_sec)}s",
            "createdAt": call.created_at.isoformat() if call.created_at else None,
            "endedAt": call.ended_at.isoformat() if call.ended_at else None,
            "costStatus": costs["status"],
            "missingCost": costs["missing"],
            "fxRateInr": costs["fxRateInr"],
            "retail": {
                "source": costs["retail"]["source"],
                "rateInrPerMin": costs["retail"]["rateInrPerMin"],
                "rateUsdPerMin": costs["retail"]["rateUsdPerMin"],
                "totalBilledInr": costs["retail"]["totalBilledInr"],
                "totalBilledUsd": costs["retail"]["totalBilledUsd"],
            },
            "supplier": {
                "status": supplier["status"],
                "missing": supplier["missing"],
                "totalInr": supplier["totalInr"],
                "totalUsd": supplier["totalUsd"],
                "marginInr": costs["margin"]["inr"],
                "marginPercent": costs["margin"]["percent"],
                "carrier": {
                    "status": carrier["status"],
                    "source": carrier["source"],
                    "billableSeconds": billable_seconds,
                    "amountInr": carrier["amountInr"],
                    "amountUsd": carrier["amountUsd"],
                    "currency": carrier_raw.get("currency"),
                    "raw": carrier_raw,
                },
                "stt": {
                    "model": stage_label("stt"),
                    "status": measured_stages["stt"]["status"],
                    "audioSeconds": float(stt_usage.get("audio_seconds") or 0.0),
                    "costInr": measured_stages["stt"]["costInr"],
                    "costUsd": measured_stages["stt"]["costUsd"],
                    "components": measured_stages["stt"]["components"],
                },
                "llm": {
                    "model": stage_label("llm", usage.get("llm_model")),
                    "status": measured_stages["llm"]["status"],
                    "inputTokens": int(llm_usage.get("input_tokens") or 0),
                    "outputTokens": int(llm_usage.get("output_tokens") or 0),
                    "costInr": measured_stages["llm"]["costInr"],
                    "costUsd": measured_stages["llm"]["costUsd"],
                    "components": measured_stages["llm"]["components"],
                },
                "tts": {
                    "model": stage_label("tts"),
                    "status": measured_stages["tts"]["status"],
                    "characters": tts_chars,
                    "outputAudioSeconds": float(tts_usage.get("output_audio_seconds") or 0.0),
                    "costInr": measured_stages["tts"]["costInr"],
                    "costUsd": measured_stages["tts"]["costUsd"],
                    "components": measured_stages["tts"]["components"],
                },
                "other": supplier["other"],
            },
            "margin": costs["margin"],
            "transcriptSummary": review.get("transcript_preview") or meta.get("post_call_summary"),
        }


@router.post("/api/dev/admin/wallets/adjust")
async def adjust_wallet(body: WalletAdjustBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.billing")
    _require_db()
    from server.services.saas.billing_rates import load_current_rates, usd_to_inr_cents
    from server.services.saas.billing_wallet_service import (
        credit_wallet,
        debit_wallet,
        get_or_create_wallet,
        wallet_summary,
    )

    rates = await load_current_rates()
    fx = float(rates["fx_rate_inr"])
    if fx <= 0:
        raise HTTPException(status_code=503, detail="A positive INR per USD rate is required for wallet adjustments.")
    cents = body.amountUsdCents
    if cents is None and body.amountInrPaise is not None:
        # Legacy clients send INR; convert so the rest of the path stays USD-authored.
        cents = int(round((int(body.amountInrPaise) / 100.0) / fx * 100))
    if not cents:
        raise HTTPException(status_code=400, detail="Amount cannot be zero")
    note = (body.note or "").strip()
    if len(note) < 8:
        raise HTTPException(
            status_code=400,
            detail="Admin statement required (at least 8 characters) for wallet adjustments.",
        )
    try:
        tenant_id = uuid.UUID(body.tenantId)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid tenant")

    ref_tail = uuid.uuid4().hex[:12]
    paise = usd_to_inr_cents(abs(cents), fx=fx)
    wallet = await get_or_create_wallet(tenant_id)
    # Credit/debit ONE leg only — writing both doubles purchasing power.
    use_inr = (wallet.currency or "usd").lower() == "inr" or (
        int(wallet.balance_inr_paise or 0) > 0 and int(wallet.balance_cents or 0) <= 0
    )
    credit_cents = 0 if use_inr else abs(cents)
    credit_paise = paise if use_inr else 0
    if cents > 0:
        await credit_wallet(
            tenant_id,
            amount_cents=credit_cents,
            amount_inr_paise=credit_paise,
            kind=body.reason or "admin_grant",
            reference_id=f"agr:{tenant_id.hex}:{ref_tail}",
        )
    else:
        await debit_wallet(
            tenant_id,
            kind=body.reason or "admin_debit",
            reference_id=f"adb:{tenant_id.hex}:{ref_tail}",
            amount_cents=credit_cents,
            amount_inr_paise=credit_paise,
            allow_partial=False,
        )
    await record_admin_action(
        actor=session.subject,
        action="wallet.adjust",
        resource_type="tenant",
        resource_id=body.tenantId,
        tenant_id=tenant_id,
        payload={
            "amountUsdCents": cents,
            "leg": "inr" if use_inr else "usd",
            "reason": body.reason,
            "note": note,
        },
    )
    return {"ok": True, "wallet": await wallet_summary(tenant_id)}


class BillingRatesBody(BaseModel):
    """Prices in the selected input currency plus the chargeable FX rate."""

    rateCurrency: Literal["USD", "INR"] = "USD"
    pstnUsdPerMin: Decimal | None = Field(
        None, ge=Decimal("0.001"), le=Decimal("100"), max_digits=12, decimal_places=6
    )
    webUsdPerMin: Decimal | None = Field(
        None, ge=Decimal("0.001"), le=Decimal("100"), max_digits=12, decimal_places=6
    )
    #: Monthly rental for a bought phone number.
    numberMonthlyUsd: Decimal | None = Field(
        None, ge=0, le=100000, max_digits=12, decimal_places=6
    )
    fxRateInr: Decimal | None = Field(
        None, ge=Decimal("0.01"), le=Decimal("100000"), max_digits=10, decimal_places=4
    )
    reason: str | None = Field(None, description="Audit statement for rate change")
    # INR values are accepted alongside the older USD fields for older clients.
    pstnInrPerMin: Decimal | None = Field(
        None, ge=Decimal("0.01"), le=Decimal("100000"), max_digits=10, decimal_places=2
    )
    webInrPerMin: Decimal | None = Field(
        None, ge=Decimal("0.01"), le=Decimal("100000"), max_digits=10, decimal_places=2
    )
    didMonthlyInr: Decimal | None = Field(
        None, ge=0, le=10000000, max_digits=12, decimal_places=2
    )
    # Per-tier PSTN rates (Economical/low, Standard Regional/medium, Flagship Live/premium)
    pstnLowUsdPerMin: Decimal | None = Field(
        None, ge=Decimal("0.001"), le=Decimal("100"), max_digits=12, decimal_places=6
    )
    pstnLowInrPerMin: Decimal | None = Field(
        None, ge=Decimal("0.01"), le=Decimal("100000"), max_digits=10, decimal_places=2
    )
    pstnMediumUsdPerMin: Decimal | None = Field(
        None, ge=Decimal("0.001"), le=Decimal("100"), max_digits=12, decimal_places=6
    )
    pstnMediumInrPerMin: Decimal | None = Field(
        None, ge=Decimal("0.01"), le=Decimal("100000"), max_digits=10, decimal_places=2
    )
    pstnPremiumUsdPerMin: Decimal | None = Field(
        None, ge=Decimal("0.001"), le=Decimal("100"), max_digits=12, decimal_places=6
    )
    pstnPremiumInrPerMin: Decimal | None = Field(
        None, ge=Decimal("0.01"), le=Decimal("100000"), max_digits=10, decimal_places=2
    )


def _rates_payload(r: dict[str, int | float]) -> dict[str, float | None]:
    return {
        "pstnUsdPerMin": round(r["pstn_rate_usd_micros_per_min"] / 1_000_000.0, 6),
        "webUsdPerMin": round(r["web_agent_rate_usd_micros_per_min"] / 1_000_000.0, 6),
        "numberMonthlyUsd": round(r["did_monthly_usd_micros"] / 1_000_000.0, 6),
        "fxRateInr": round(float(r["fx_rate_inr"]), 4),
        # Both currencies are stored per rate version and used by the matching wallet leg.
        "pstnInrPerMin": round(r["pstn_rate_inr_paise_per_min"] / 100.0, 2),
        "webInrPerMin": round(r["web_agent_rate_inr_paise_per_min"] / 100.0, 2),
        "numberMonthlyInr": round(r["did_monthly_inr_paise"] / 100.0, 2),
        # Per-tier native PSTN rates
        "pstnLowUsdPerMin": round(r["pstn_low_rate_usd_micros_per_min"] / 1_000_000.0, 6) if r.get("pstn_low_rate_usd_micros_per_min") is not None else None,
        "pstnLowInrPerMin": round(r["pstn_low_rate_inr_paise_per_min"] / 100.0, 2) if r.get("pstn_low_rate_inr_paise_per_min") is not None else None,
        "pstnMediumUsdPerMin": round(r["pstn_medium_rate_usd_micros_per_min"] / 1_000_000.0, 6) if r.get("pstn_medium_rate_usd_micros_per_min") is not None else None,
        "pstnMediumInrPerMin": round(r["pstn_medium_rate_inr_paise_per_min"] / 100.0, 2) if r.get("pstn_medium_rate_inr_paise_per_min") is not None else None,
        "pstnPremiumUsdPerMin": round(r["pstn_premium_rate_usd_micros_per_min"] / 1_000_000.0, 6) if r.get("pstn_premium_rate_usd_micros_per_min") is not None else None,
        "pstnPremiumInrPerMin": round(r["pstn_premium_rate_inr_paise_per_min"] / 100.0, 2) if r.get("pstn_premium_rate_inr_paise_per_min") is not None else None,
    }


@router.get("/api/dev/admin/billing-rates")
async def get_billing_rates(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.billing")
    from server.services.saas.billing_rates import live_fx, load_current_rates

    rates = await load_current_rates()
    return {
        "currency": "USD",
        "rates": _rates_payload(rates),
        # Market rate for reference in the converter; charging uses fxRateInr.
        "fx": live_fx(),
    }


@router.put("/api/dev/admin/billing-rates")
async def put_billing_rates(body: BillingRatesBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.billing")
    from server.services.saas.billing_rates import update_rates_versioned

    reason = (body.reason or "").strip()
    if len(reason) < 8:
        reason = f"Admin rates adjustment by {session.subject}"

    rate_curr = body.rateCurrency
    if any(v is not None for v in (body.pstnInrPerMin, body.webInrPerMin, body.pstnLowInrPerMin, body.pstnMediumInrPerMin, body.pstnPremiumInrPerMin, body.didMonthlyInr)):
        rate_curr = "INR"

    pstn_inr = body.pstnInrPerMin
    if pstn_inr is None and body.pstnMediumInrPerMin is not None:
        pstn_inr = body.pstnMediumInrPerMin

    try:
        r = await update_rates_versioned(
            actor=session.subject,
            reason=reason,
            rate_currency=rate_curr,
            pstn_usd_per_min=body.pstnUsdPerMin,
            web_usd_per_min=body.webUsdPerMin,
            did_monthly_usd=body.numberMonthlyUsd,
            pstn_inr_per_min=pstn_inr,
            web_inr_per_min=body.webInrPerMin,
            did_monthly_inr=body.didMonthlyInr,
            pstn_low_usd_per_min=body.pstnLowUsdPerMin,
            pstn_low_inr_per_min=body.pstnLowInrPerMin,
            pstn_medium_usd_per_min=body.pstnMediumUsdPerMin,
            pstn_medium_inr_per_min=body.pstnMediumInrPerMin,
            pstn_premium_usd_per_min=body.pstnPremiumUsdPerMin,
            pstn_premium_inr_per_min=body.pstnPremiumInrPerMin,
            fx_rate_inr=body.fxRateInr,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await record_admin_action(
        actor=session.subject,
        action="billing.rates",
        resource_type="platform",
        resource_id="rates",
        payload=body.model_dump(exclude_none=True, mode="json"),
    )
    return {"ok": True, "currency": "USD", "rates": _rates_payload(r)}


class TierMerchandisingBody(BaseModel):
    model_config = {"extra": "forbid"}

    expectedVersion: int = Field(ge=0, strict=True)
    featuredStyle: str | None = None
    calculator: dict[str, Any] | None = None
    tiers: dict[str, Any]


def _merchandising_response(view: dict[str, Any], tiers: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    from server.services.saas.pricing_merchandising import (
        CALCULATOR_FEATURES,
        FEATURED_STYLES,
        calculator_flags,
        default_merchandising,
    )
    from server.services.saas.voice_stack_profiles import TIER_LABELS

    defaults_merchandising = default_merchandising()
    defaults = defaults_merchandising["tiers"]["low"]
    if not tiers:
        tiers = [
            {"id": tier, "label": label, "active": False}
            for tier, label in TIER_LABELS.items()
        ]
    return {
        "version": view["version"],
        "updatedAt": view["updatedAt"],
        "updatedBy": view["updatedBy"],
        "featuredStyle": view.get("featuredStyle") or defaults_merchandising["featuredStyle"],
        "featuredStyles": list(FEATURED_STYLES),
        "calculator": calculator_flags(view),
        "calculatorFeatures": list(CALCULATOR_FEATURES),
        "tiers": [
            {
                "id": row["id"],
                "label": row["label"],
                **{**defaults, **view["tiers"].get(row["id"], {})},
                "active": row["active"],
                "pstnInrPerMin": row.get("pstnInrPerMin"),
                "webInrPerMin": row.get("webInrPerMin"),
            }
            for row in tiers
        ],
    }


async def _tier_activation() -> list[dict[str, Any]]:
    """Every configured stack with its public-shelf status, in tenant-catalog order."""
    from server.services.dev_runtime import effective_app_environment
    from server.services.saas.voice_stack_profiles import (
        TIER_LABELS,
        _load_rates_without_fallback,
        _native_tier_retail_rate,
        _public_label,
        _web_tier_retail_rate,
        load_profile_records,
        ordered_stack_tier_ids,
        tier_is_public,
    )

    try:
        records = await load_profile_records(effective_app_environment(), None)
    except Exception:
        records = {}
    try:
        rates = await _load_rates_without_fallback()
    except Exception:
        rates = None
    tiers = []
    for tier in ordered_stack_tier_ids(records):
        record = records.get(tier)
        profile = record.get("profile") if isinstance(record, dict) else None
        pstn_rate = _native_tier_retail_rate(rates, tier, record=record)
        web_rate = _web_tier_retail_rate(rates, tier, record=record)
        tiers.append(
            {
                "id": tier,
                "label": _public_label(
                    profile.get("label") if isinstance(profile, dict) else None,
                    TIER_LABELS.get(tier, tier.title()),
                ),
                "active": tier_is_public(tier, record, rates),
                # Shelf prices for the admin preview; the marketing page shows the same numbers.
                "pstnInrPerMin": round(pstn_rate["inrPaisePerMin"] / 100.0, 2) if pstn_rate else None,
                "webInrPerMin": round(web_rate["inrPaisePerMin"] / 100.0, 2) if web_rate else None,
            }
        )
    return tiers


@router.get("/api/dev/admin/pricing-merchandising")
async def get_pricing_merchandising(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.billing")
    from server.services.saas.pricing_merchandising import load_tier_merchandising

    view = await load_tier_merchandising(force=True)
    return _merchandising_response(view, await _tier_activation())


@router.put("/api/dev/admin/pricing-merchandising")
async def put_pricing_merchandising(
    body: TierMerchandisingBody,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.billing")
    from server.services.saas.pricing_merchandising import (
        PUBLIC_TIERS,
        MerchandisingError,
        save_tier_merchandising,
    )

    tiers = await _tier_activation()
    try:
        view = await save_tier_merchandising(
            tiers=body.tiers,
            expected_version=body.expectedVersion,
            actor=session.subject,
            allowed_tiers=[row["id"] for row in tiers] or list(PUBLIC_TIERS),
            featured_style=body.featuredStyle,
            calculator=body.calculator,
        )
    except MerchandisingError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": {"code": exc.code, "message": str(exc)}},
        ) from exc
    await record_admin_action(
        actor=session.subject,
        action="billing.merchandising",
        resource_type="platform",
        resource_id="tier_merchandising",
        payload={
            "expectedVersion": body.expectedVersion,
            "version": view["version"],
            "featuredStyle": view["featuredStyle"],
            "calculator": view["calculator"],
            "tiers": body.tiers,
        },
    )
    return _merchandising_response(view, tiers)


class ProviderCostsBody(BaseModel):
    model_config = {"extra": "forbid"}

    expectedVersion: int = Field(ge=0, strict=True)
    reason: str = Field(min_length=8, max_length=500)
    rates: list[dict[str, Any]] = Field(min_length=1, max_length=100)


@router.get("/api/dev/admin/billing/provider-costs")
async def get_provider_costs(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.billing")
    from server.services.saas.composed_costing import ProviderCostError, load_provider_costs

    try:
        return await load_provider_costs()
    except ProviderCostError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"error": {"code": exc.code, "message": str(exc)}}) from exc


@router.put("/api/dev/admin/billing/provider-costs")
async def put_provider_costs(body: ProviderCostsBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.billing")
    from server.services.saas.composed_costing import ProviderCostError, save_provider_costs

    try:
        result = await save_provider_costs(expected_version=body.expectedVersion, rates=body.rates,
                                           actor=session.subject, reason=body.reason)
    except ProviderCostError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"error": {"code": exc.code, "message": str(exc)}}) from exc
    await record_admin_action(actor=session.subject, action="billing.provider_costs", resource_type="platform",
                              resource_id="composed_provider_costs", payload={"version": result["version"], "reason": body.reason})
    return result


class PlatformLanguagesBody(BaseModel):
    enabled: list[str] = Field(..., min_length=1, max_length=64)


class PaymentSettingsBody(BaseModel):
    internationalEnabled: bool | None = None
    currency: str | None = Field(None, max_length=8)


@router.get("/api/dev/admin/payments")
async def get_payment_settings(session: SessionData = Depends(require_dev_session)):
    """Razorpay status, including whether international cards are switched on."""
    require_permission(session, "dev.admin.billing")
    from server.services.saas.payment_settings import settings_state

    return settings_state()


@router.put("/api/dev/admin/payments")
async def put_payment_settings(
    body: PaymentSettingsBody, session: SessionData = Depends(require_dev_session)
):
    """Turn International Payments on/off and choose the currency to charge in.

    Enabling international requires the operator to have activated it in the
    Razorpay dashboard first; this records that so orders stop being created as
    INR and start being created in the chosen currency.
    """
    require_permission(session, "dev.admin.billing")
    from server.services.saas.payment_settings import update_settings

    try:
        state = update_settings(
            international_enabled=body.internationalEnabled,
            currency=body.currency,
        )
    except ValueError as exc:
        code = str(exc)
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": code,
                    "message": "Razorpay does not support that currency.",
                }
            },
        ) from None
    await record_admin_action(
        actor=session.subject,
        action="payments.settings",
        resource_type="platform",
        resource_id="payments",
        payload=body.model_dump(exclude_none=True),
    )
    return {"ok": True, **state}


class TaxSettingsBody(BaseModel):
    model_config = {"extra": "forbid"}

    enabled: bool = False
    legalName: str = Field("", max_length=255)
    tradeName: str = Field("", max_length=255)
    gstin: Optional[str] = Field(None, max_length=15)
    pan: Optional[str] = Field(None, max_length=10)
    addressLine1: str = Field("", max_length=255)
    addressLine2: str = Field("", max_length=255)
    city: str = Field("", max_length=120)
    stateCode: str = Field("", max_length=4)
    stateName: str = Field("", max_length=120)
    postalCode: str = Field("", max_length=12)
    countryCode: str = Field("IN", max_length=2)
    supportEmail: str = Field("", max_length=320)
    supportPhone: str = Field("", max_length=40)
    sacCode: str = Field("998413", max_length=12)
    defaultRateBps: int = Field(1800, ge=0, le=5000)
    priceIncludesTax: bool = False
    exportZeroRated: bool = True
    invoicePrefix: str = Field("INV", max_length=4)
    creditNotePrefix: str = Field("CN", max_length=4)
    lutNumber: Optional[str] = Field(None, max_length=32)
    invoiceTerms: str = Field("", max_length=2000)
    expectedUpdatedAt: str | None = Field(None, max_length=64)


class TaxPreviewBody(BaseModel):
    settings: TaxSettingsBody
    amount: float = Field(1000, gt=0, le=1000000)
    currency: Literal["INR", "USD"] = "INR"
    buyerCountry: str = Field("IN", min_length=2, max_length=2)
    buyerState: str = Field("", max_length=4)


class RefundBody(BaseModel):
    model_config = {"extra": "forbid"}

    amount: Optional[float] = Field(None, gt=0, le=500000)
    reason: str = Field(..., min_length=8, max_length=500)


def _parse_dt(raw: str | None, *, end: bool = False):
    """Filter dates are IST: a GST period is an Indian calendar day."""
    if not raw:
        return None
    from server.services.saas.tax_service import IST

    value = raw.strip()
    try:
        if len(value) == 10:
            parsed = datetime.fromisoformat(value)
            if end:
                return parsed.replace(hour=23, minute=59, second=59, tzinfo=IST)
            return parsed.replace(tzinfo=IST)
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=IST)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_date") from None


def _order_conditions(
    *,
    status: str | None,
    tenant_id: str | None,
    q: str | None,
    date_from: str | None,
    date_to: str | None,
):
    from server.db.models.saas_models import RazorpayOrder

    conditions = []
    if status:
        conditions.append(RazorpayOrder.status == status)
    if tenant_id:
        try:
            conditions.append(RazorpayOrder.tenant_id == uuid.UUID(tenant_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid_tenant") from None
    if q:
        needle = f"%{q.strip()[:80]}%"
        conditions.append(
            RazorpayOrder.order_id.ilike(needle)
            | RazorpayOrder.payment_id.ilike(needle)
            | Tenant.name.ilike(needle)
        )
    start = _parse_dt(date_from)
    end = _parse_dt(date_to, end=True)
    if start:
        conditions.append(RazorpayOrder.created_at >= start)
    if end:
        conditions.append(RazorpayOrder.created_at <= end)
    return conditions


def _order_payload(order, tenant, invoice=None) -> dict[str, Any]:
    from server.services.saas.razorpay_service import from_minor

    currency = order.currency or "INR"
    gross = (
        from_minor(order.gross_minor, currency)
        if getattr(order, "gross_minor", None)
        else from_minor(order.amount_minor or 0, currency)
    )
    return {
        "orderId": order.order_id,
        "tenantId": str(order.tenant_id),
        "tenantName": tenant.name if tenant else None,
        "status": order.status,
        "currency": currency,
        "amount": gross,
        "subtotal": from_minor(order.taxable_minor or 0, currency),
        "tax": from_minor(order.tax_minor or 0, currency),
        "taxRatePercent": round(int(order.tax_rate_bps or 0) / 100.0, 2),
        "taxKind": order.tax_kind or "none",
        "amountInr": (order.amount_inr_paise or 0) / 100.0,
        "grossInr": (
            (order.amount_inr_paise or 0) + (int(order.tax_minor or 0) if currency == "INR" else 0)
        )
        / 100.0,
        "baseAmountInr": (order.base_amount_inr_paise or 0) / 100.0 or None,
        "paymentId": order.payment_id,
        "paymentMethod": order.payment_method,
        "failureCode": order.failure_code,
        "failureReason": order.failure_reason,
        "fee": from_minor(order.fee_minor, currency) if order.fee_minor is not None else None,
        "taxOnFee": (
            from_minor(order.tax_on_fee_minor, currency)
            if order.tax_on_fee_minor is not None
            else None
        ),
        "settlementId": order.settlement_id,
        "settledAt": order.settled_at.isoformat() if order.settled_at else None,
        "invoiceId": str(invoice.invoice_id) if invoice else None,
        "invoiceNumber": invoice.invoice_number if invoice else None,
        "invoiceStatus": invoice.status if invoice else None,
        "createdAt": order.created_at.isoformat() if order.created_at else None,
        "paidAt": order.paid_at.isoformat() if order.paid_at else None,
        "expiresAt": order.expires_at.isoformat() if order.expires_at else None,
    }


@router.get("/api/dev/admin/payments/tax-settings")
async def get_tax_settings(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.billing")
    from server.services.saas.invoice_service import _PDF_AVAILABLE
    from server.services.saas.tax_service import financial_year, load_config, public_config

    state = public_config(await load_config())
    settings = get_settings()
    return {
        **state,
        "currentFy": financial_year(),
        "webhookConfigured": bool((settings.razorpay_webhook_secret or "").strip()),
        "razorpayConfigured": bool(
            (settings.razorpay_api_key or "").strip() and (settings.razorpay_api_secret or "").strip()
        ),
        "pdfAvailable": bool(_PDF_AVAILABLE),
    }


@router.put("/api/dev/admin/payments/tax-settings")
async def put_tax_settings(
    body: TaxSettingsBody, session: SessionData = Depends(require_dev_session)
):
    require_permission(session, "dev.admin.billing")
    from server.services.saas.tax_service import save_config

    try:
        state = await save_config(body.model_dump(), actor=session.subject)
    except ValueError as exc:
        code = str(exc)
        messages = {
            "tax_settings_conflict": "Tax settings changed in another session. Reload before saving.",
            "gstin_invalid_format": "GSTIN must be the 15-character GST format.",
            "gstin_invalid_state": "GSTIN starts with an unknown state code.",
            "gstin_invalid_checksum": "GSTIN check digit is invalid.",
            "gstin_state_mismatch": "GSTIN state does not match the supplier state.",
            "gstin_required": "A GSTIN is required before GST can be enabled.",
            "legal_name_required": "Legal name is required before GST can be enabled.",
            "address_required": "Registered address and city are required before GST can be enabled.",
            "state_required": "Supplier state is required before GST can be enabled.",
            "invalid_state_code": "Choose a valid Indian state.",
            "invalid_rate": "GST rate must be between 0% and 50%.",
        }
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": code, "message": messages.get(code, code)}},
        ) from None
    await record_admin_action(
        actor=session.subject,
        action="payments.tax_settings",
        resource_type="platform",
        resource_id="gst",
        payload={**body.model_dump(), "gstin": body.gstin},
    )
    return {"ok": True, **state}


@router.post("/api/dev/admin/payments/tax-preview")
async def preview_tax_settings(body: TaxPreviewBody, session: Annotated[SessionData, Depends(require_dev_session)]):
    """Price a draft GST configuration without saving it or contacting payments."""
    require_permission(session, "dev.admin.billing")
    from server.services.saas.billing_rates import load_current_rates
    from server.services.saas.tax_service import compute_tax, config_configured
    config = body.settings.model_dump()
    if config.get("enabled") and not config_configured(config):
        raise HTTPException(status_code=400, detail="Complete the supplier identity before previewing enabled GST")
    rates = await load_current_rates()
    return compute_tax(body.amount, body.currency, fx_rate_inr=float(rates["fx_rate_inr"]), config=config,
        buyer={"countryCode": body.buyerCountry, "stateCode": body.buyerState})


@router.get("/api/dev/admin/payments/orders")
async def list_payment_orders(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=100000),
    status: Optional[str] = Query(None, max_length=30),
    tenantId: Optional[str] = Query(None, max_length=64),
    q: Optional[str] = Query(None, max_length=120),
    dateFrom: Optional[str] = Query(None, max_length=40),
    dateTo: Optional[str] = Query(None, max_length=40),
    session: SessionData = Depends(require_dev_session),
):
    """Top-up orders with tax, settlement and failure state."""
    require_permission(session, "dev.admin.billing")
    _require_db()
    from server.db.models.saas_models import BillingInvoice, RazorpayOrder

    conditions = _order_conditions(
        status=status, tenant_id=tenantId, q=q, date_from=dateFrom, date_to=dateTo
    )
    async with get_session_factory()() as db:
        rows = (
            await db.execute(
                select(RazorpayOrder, Tenant, BillingInvoice)
                .outerjoin(Tenant, Tenant.tenant_id == RazorpayOrder.tenant_id)
                .outerjoin(BillingInvoice, BillingInvoice.razorpay_order_id == RazorpayOrder.order_id)
                .where(*conditions)
                .order_by(desc(RazorpayOrder.created_at))
                .offset(offset)
                .limit(limit)
            )
        ).all()
        collected_states = ("paid", "partially_refunded", "refunded")
        settled = RazorpayOrder.status.in_(collected_states)
        totals = (
            await db.execute(
                select(
                    func.count(RazorpayOrder.order_id),
                    func.coalesce(
                        func.sum(
                            case((settled, RazorpayOrder.amount_inr_paise), else_=0)
                        ),
                        0,
                    ),
                    func.coalesce(
                        func.sum(
                            case((settled, RazorpayOrder.base_amount_inr_paise), else_=0)
                        ),
                        0,
                    ),
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    settled & (RazorpayOrder.currency == "INR"),
                                    RazorpayOrder.amount_inr_paise + RazorpayOrder.tax_minor,
                                ),
                                (settled, RazorpayOrder.amount_inr_paise),
                                else_=0,
                            )
                        ),
                        0,
                    ),
                )
                .select_from(RazorpayOrder)
                .outerjoin(Tenant, Tenant.tenant_id == RazorpayOrder.tenant_id)
                .where(*conditions)
            )
        ).one()
        by_status = (
            await db.execute(
                select(RazorpayOrder.status, func.count(RazorpayOrder.order_id))
                .select_from(RazorpayOrder)
                .outerjoin(Tenant, Tenant.tenant_id == RazorpayOrder.tenant_id)
                .where(*conditions)
                .group_by(RazorpayOrder.status)
            )
        ).all()
        return {
            "orders": [_order_payload(order, tenant, invoice) for order, tenant, invoice in rows],
            "total": int(totals[0] or 0),
            "summary": {
                "creditedInr": int(totals[1] or 0) / 100.0,
                "settledInr": int(totals[2] or 0) / 100.0,
                "collectedInr": int(totals[3] or 0) / 100.0,
                "byStatus": {str(name): int(count) for name, count in by_status},
            },
            "limit": limit,
            "offset": offset,
        }


@router.get("/api/dev/admin/payments/orders/{order_id}")
async def payment_order_detail(order_id: str, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.billing")
    _require_db()
    from server.db.models.saas_models import BillingInvoice, RazorpayOrder, RazorpayRefund
    from server.services.saas.invoice_service import invoice_payload

    async with get_session_factory()() as db:
        order = await db.get(RazorpayOrder, order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="order_not_found")
        tenant = await db.get(Tenant, order.tenant_id)
        invoice = (
            await db.execute(
                select(BillingInvoice).where(BillingInvoice.razorpay_order_id == order_id)
            )
        ).scalar_one_or_none()
        refunds = list(
            (
                await db.execute(
                    select(RazorpayRefund)
                    .where(RazorpayRefund.order_id == order_id)
                    .order_by(RazorpayRefund.created_at.desc())
                )
            ).scalars()
        )
        return {
            "order": _order_payload(order, tenant, invoice),
            "invoice": invoice_payload(invoice) if invoice else None,
            "refunds": [
                {
                    "refundId": r.refund_id,
                    "amount": r.amount_minor / 100.0,
                    "currency": r.currency,
                    "walletReversalInr": (r.credit_inr_paise or 0) / 100.0,
                    "taxReversalInr": (r.tax_inr_paise or 0) / 100.0,
                    "status": r.status,
                    "reason": r.reason,
                    "createdBy": r.created_by,
                    "createdAt": r.created_at.isoformat() if r.created_at else None,
                }
                for r in refunds
            ],
        }


@router.post("/api/dev/admin/payments/orders/{order_id}/reconcile")
async def reconcile_payment_order(
    order_id: str, session: SessionData = Depends(require_dev_session)
):
    """Ask Razorpay for the order's real state and settle it locally."""
    require_permission(session, "dev.admin.billing")
    _require_db()
    from server.db.models.saas_models import RazorpayOrder
    from server.services.saas.razorpay_service import (
        _client,
        _run_provider_call,
        credit_provider_payment,
        mark_order_failed,
    )

    async with get_session_factory()() as db:
        order = await db.get(RazorpayOrder, order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="order_not_found")
        current = order.status
    if current in ("paid", "refunded", "partially_refunded"):
        return {"ok": True, "status": current, "message": "Already settled."}
    try:
        payments = await _run_provider_call(_client().order.payments, order_id)
    except Exception:
        raise HTTPException(status_code=502, detail="provider_unavailable") from None
    items = payments.get("items", []) if isinstance(payments, dict) else []
    captured = [item for item in items if str(item.get("status")) == "captured"]
    result: dict[str, Any] = {"ok": True, "checked": len(items)}
    if captured:
        result.update(await credit_provider_payment(captured[0], source="admin"))
        result["status"] = "paid"
    elif items:
        await mark_order_failed(items[0], source="admin")
        result["status"] = "failed"
    else:
        result["status"] = current
    await record_admin_action(
        actor=session.subject,
        action="payments.reconcile",
        resource_type="payment_order",
        resource_id=order_id,
        payload={"providerStatus": result.get("status")},
    )
    return result


@router.post("/api/dev/admin/payments/orders/{order_id}/refund")
async def refund_payment_order(
    order_id: str,
    body: RefundBody,
    session: SessionData = Depends(require_dev_session),
):
    """Refund through Razorpay, reverse the wallet and issue a GST credit note."""
    require_permission(session, "dev.admin.billing")
    _require_db()
    from server.db.models.saas_models import RazorpayOrder
    from server.services.saas.razorpay_service import from_minor, refund_order, to_minor

    async with get_session_factory()() as db:
        order = await db.get(RazorpayOrder, order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="order_not_found")
        currency = order.currency or "INR"
        gross_minor = int(order.gross_minor or order.amount_minor or 0)
    amount_minor = to_minor(body.amount, currency) if body.amount else None
    if amount_minor is not None and amount_minor > gross_minor:
        raise HTTPException(status_code=400, detail="refund_exceeds_charge")
    try:
        result = await refund_order(
            order_id,
            amount_minor=amount_minor,
            reason=body.reason,
            actor=session.subject,
        )
    except ValueError as exc:
        code = str(exc)
        messages = {
            "order_not_refundable": "Only a captured payment can be refunded.",
            "invalid_refund_amount": "Refund amount must be between zero and the captured amount.",
            "refund_failed": "Razorpay did not accept the refund. No balance was changed.",
        }
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": code, "message": messages.get(code, code)}},
        ) from None
    await record_admin_action(
        actor=session.subject,
        action="payments.refund",
        resource_type="payment_order",
        resource_id=order_id,
        payload={
            "amount": body.amount or from_minor(gross_minor, currency),
            "currency": currency,
            "reason": body.reason,
            "refundId": result.get("refundId"),
            "creditNoteNumber": result.get("creditNoteNumber"),
        },
    )
    return result


@router.get("/api/dev/admin/payments/invoices")
async def list_billing_invoices(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=100000),
    tenantId: Optional[str] = Query(None, max_length=64),
    status: Optional[str] = Query(None, max_length=30),
    q: Optional[str] = Query(None, max_length=120),
    dateFrom: Optional[str] = Query(None, max_length=40),
    dateTo: Optional[str] = Query(None, max_length=40),
    session: SessionData = Depends(require_dev_session),
):
    """Invoice register with GST totals — the report a tax filing needs."""
    require_permission(session, "dev.admin.billing")
    _require_db()
    from server.db.models.saas_models import BillingInvoice
    from server.services.saas.invoice_service import invoice_payload

    conditions = []
    if tenantId:
        try:
            conditions.append(BillingInvoice.tenant_id == uuid.UUID(tenantId))
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid_tenant") from None
    if status:
        conditions.append(BillingInvoice.status == status)
    if q:
        needle = f"%{q.strip()[:80]}%"
        conditions.append(
            BillingInvoice.invoice_number.ilike(needle)
            | BillingInvoice.razorpay_payment_id.ilike(needle)
            | BillingInvoice.customer_gstin.ilike(needle)
            | Tenant.name.ilike(needle)
        )
    start = _parse_dt(dateFrom)
    end = _parse_dt(dateTo, end=True)
    if start:
        conditions.append(BillingInvoice.created_at >= start)
    if end:
        conditions.append(BillingInvoice.created_at <= end)

    async with get_session_factory()() as db:
        rows = (
            await db.execute(
                select(BillingInvoice, Tenant)
                .outerjoin(Tenant, Tenant.tenant_id == BillingInvoice.tenant_id)
                .where(*conditions)
                .order_by(desc(BillingInvoice.created_at))
                .offset(offset)
                .limit(limit)
            )
        ).all()
        totals = (
            await db.execute(
                select(
                    func.count(BillingInvoice.invoice_id),
                    func.coalesce(
                        func.sum(BillingInvoice.amount_inr_paise + BillingInvoice.tax_inr_paise), 0
                    ),
                    func.coalesce(func.sum(BillingInvoice.taxable_inr_paise), 0),
                    func.coalesce(func.sum(BillingInvoice.tax_inr_paise), 0),
                    func.coalesce(func.sum(BillingInvoice.cgst_inr_paise), 0),
                    func.coalesce(func.sum(BillingInvoice.sgst_inr_paise), 0),
                    func.coalesce(func.sum(BillingInvoice.igst_inr_paise), 0),
                )
                .select_from(BillingInvoice)
                .outerjoin(Tenant, Tenant.tenant_id == BillingInvoice.tenant_id)
                .where(*conditions)
            )
        ).one()
        invoices = []
        for invoice, tenant in rows:
            payload = invoice_payload(invoice)
            payload["tenantName"] = tenant.name if tenant else None
            invoices.append(payload)
        return {
            "invoices": invoices,
            "total": int(totals[0] or 0),
            "summary": {
                "grossInr": int(totals[1] or 0) / 100.0,
                "taxableInr": int(totals[2] or 0) / 100.0,
                "taxInr": int(totals[3] or 0) / 100.0,
                "cgstInr": int(totals[4] or 0) / 100.0,
                "sgstInr": int(totals[5] or 0) / 100.0,
                "igstInr": int(totals[6] or 0) / 100.0,
            },
            "limit": limit,
            "offset": offset,
        }


@router.get("/api/dev/admin/payments/invoices/{invoice_id}/pdf")
async def admin_invoice_pdf(invoice_id: uuid.UUID, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.billing")
    _require_db()
    from server.services.saas.invoice_service import render_invoice_pdf
    from server.services.saas.razorpay_service import get_invoice

    invoice, notes = await get_invoice(None, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="invoice_not_found")
    try:
        pdf = render_invoice_pdf(invoice, notes)
    except RuntimeError:
        raise HTTPException(status_code=503, detail="invoice_pdf_unavailable") from None
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{invoice.invoice_number}.pdf"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/api/dev/admin/payments/invoices/export")
async def export_billing_invoices(
    tenantId: Optional[str] = Query(None, max_length=64),
    dateFrom: Optional[str] = Query(None, max_length=40),
    dateTo: Optional[str] = Query(None, max_length=40),
    session: SessionData = Depends(require_dev_session),
):
    """CSV of the invoice register for accounting / GST return preparation."""
    require_permission(session, "dev.admin.billing")
    _require_db()
    import csv
    import io

    from server.db.models.saas_models import BillingInvoice
    from server.services.saas.razorpay_service import from_minor

    conditions = []
    if tenantId:
        try:
            conditions.append(BillingInvoice.tenant_id == uuid.UUID(tenantId))
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid_tenant") from None
    start = _parse_dt(dateFrom)
    end = _parse_dt(dateTo, end=True)
    if start:
        conditions.append(BillingInvoice.created_at >= start)
    if end:
        conditions.append(BillingInvoice.created_at <= end)

    async with get_session_factory()() as db:
        rows = list(
            (
                await db.execute(
                    select(BillingInvoice)
                    .where(*conditions)
                    .order_by(BillingInvoice.created_at.asc())
                    .limit(5000)
                )
            ).scalars()
        )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "invoice_number", "invoice_date", "fy", "tenant_id", "gstin", "currency",
            "gross", "taxable_inr", "tax_inr", "cgst_inr", "sgst_inr", "igst_inr",
            "tax_kind", "sac_code", "place_of_supply", "status", "payment_id",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.invoice_number,
                row.created_at.isoformat() if row.created_at else "",
                row.fy or "",
                str(row.tenant_id),
                row.customer_gstin or "",
                row.currency,
                from_minor(int(row.amount_minor or 0), row.currency or "INR"),
                int(row.taxable_inr_paise or 0) / 100.0,
                int(row.tax_inr_paise or 0) / 100.0,
                int(row.cgst_inr_paise or 0) / 100.0,
                int(row.sgst_inr_paise or 0) / 100.0,
                int(row.igst_inr_paise or 0) / 100.0,
                row.tax_kind or "none",
                row.sac_code or "",
                row.place_of_supply or "",
                row.status,
                row.razorpay_payment_id or "",
            ]
        )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="invoices.csv"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/api/dev/admin/payments/tax-report")
async def billing_tax_report(
    dateFrom: Optional[str] = Query(None, max_length=40),
    dateTo: Optional[str] = Query(None, max_length=40),
    session: SessionData = Depends(require_dev_session),
):
    """Net GST position: issued invoices minus credit notes in the period."""
    require_permission(session, "dev.admin.billing")
    _require_db()
    from server.db.models.saas_models import BillingInvoice, CreditNote

    conditions = []
    start = _parse_dt(dateFrom)
    end = _parse_dt(dateTo, end=True)
    if start:
        conditions.append(BillingInvoice.created_at >= start)
    if end:
        conditions.append(BillingInvoice.created_at <= end)
    note_conditions = []
    if start:
        note_conditions.append(CreditNote.created_at >= start)
    if end:
        note_conditions.append(CreditNote.created_at <= end)

    async with get_session_factory()() as db:
        invoice_rows = (
            await db.execute(
                select(
                    BillingInvoice.tax_kind,
                    func.count(BillingInvoice.invoice_id),
                    func.coalesce(func.sum(BillingInvoice.taxable_inr_paise), 0),
                    func.coalesce(func.sum(BillingInvoice.tax_inr_paise), 0),
                    func.coalesce(func.sum(BillingInvoice.cgst_inr_paise), 0),
                    func.coalesce(func.sum(BillingInvoice.sgst_inr_paise), 0),
                    func.coalesce(func.sum(BillingInvoice.igst_inr_paise), 0),
                )
                .where(*conditions)
                .group_by(BillingInvoice.tax_kind)
            )
        ).all()
        note_row = (
            await db.execute(
                select(
                    func.count(CreditNote.credit_note_id),
                    func.coalesce(func.sum(CreditNote.taxable_inr_paise), 0),
                    func.coalesce(func.sum(CreditNote.tax_inr_paise), 0),
                    func.coalesce(func.sum(CreditNote.cgst_inr_paise), 0),
                    func.coalesce(func.sum(CreditNote.sgst_inr_paise), 0),
                    func.coalesce(func.sum(CreditNote.igst_inr_paise), 0),
                ).where(*note_conditions)
            )
        ).one()

    def _row(name, count, taxable, tax, cgst, sgst, igst):
        return {
            "taxKind": name,
            "count": int(count or 0),
            "taxableInr": int(taxable or 0) / 100.0,
            "taxInr": int(tax or 0) / 100.0,
            "cgstInr": int(cgst or 0) / 100.0,
            "sgstInr": int(sgst or 0) / 100.0,
            "igstInr": int(igst or 0) / 100.0,
        }

    issued = [_row(*row) for row in invoice_rows]
    notes = _row("credit_note", *note_row)
    totals = {
        "taxableInr": round(sum(item["taxableInr"] for item in issued) - notes["taxableInr"], 2),
        "taxInr": round(sum(item["taxInr"] for item in issued) - notes["taxInr"], 2),
        "cgstInr": round(sum(item["cgstInr"] for item in issued) - notes["cgstInr"], 2),
        "sgstInr": round(sum(item["sgstInr"] for item in issued) - notes["sgstInr"], 2),
        "igstInr": round(sum(item["igstInr"] for item in issued) - notes["igstInr"], 2),
    }
    return {
        "from": dateFrom,
        "to": dateTo,
        "issued": issued,
        "creditNotes": notes,
        "net": totals,
    }


@router.get("/api/dev/admin/tenants/{tenant_id}/billing-profile")
async def admin_tenant_billing_profile(
    tenant_id: uuid.UUID, session: SessionData = Depends(require_dev_session)
):
    require_permission(session, "dev.admin.billing")
    _require_db()
    from server.services.saas.billing_profile_service import get_profile

    return await get_profile(tenant_id)


@router.get("/api/dev/admin/languages")
async def get_platform_languages(session: SessionData = Depends(require_dev_session)):
    """Every language the platform can speak, and which are offered at creation."""
    require_permission(session, "dev.admin.billing")
    from server.services.saas.platform_languages import state

    return state()


@router.put("/api/dev/admin/languages")
async def put_platform_languages(
    body: PlatformLanguagesBody, session: SessionData = Depends(require_dev_session)
):
    """Enable/disable languages offered in the agent-creation UI.

    Turning a language off only removes it from the picker — agents that already
    speak it keep working, which is why this is an enablement list layered over
    the supported set rather than a deletion.
    """
    require_permission(session, "dev.admin.billing")
    from server.services.saas.platform_languages import set_enabled, state

    try:
        set_enabled(body.enabled)
    except ValueError as exc:
        code = str(exc)
        messages = {
            "unknown_language": "One or more languages are not supported by the platform.",
            "no_languages": "At least one language must stay enabled.",
        }
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": code, "message": messages.get(code, code)}},
        )
    await record_admin_action(
        actor=session.subject,
        action="platform.languages",
        resource_type="platform",
        resource_id="languages",
        payload={"enabled": body.enabled},
    )
    return {"ok": True, **state()}


@router.get("/api/dev/admin/session-failures")
async def session_failures(
    limit: int = Query(50, ge=1, le=200),
    session: SessionData = Depends(require_dev_session),
):
    """Web/phone session failure ring buffer ? admin API only (not shown in product UI)."""
    require_permission(session, "dev.admin.tenants")
    from server.services.saas.session_failure_log import list_session_failures

    return {"failures": list_session_failures(limit)}


class KycStatusBody(BaseModel):
    status: str
    reason: str = Field(..., min_length=8, max_length=500)


@router.get("/api/dev/admin/kyc")
async def list_kyc(
    status: str | None = None,
    session: SessionData = Depends(require_dev_session),
):
    """Identity verification queue for ops — Vobiz Voice KYC tenant subaccounts + Didit."""
    require_permission(session, "dev.admin.users")
    _require_db()
    from server.config.env import get_settings
    from server.services.saas import kyc_service
    from server.services.saas import voice_kyc_service
    from server.services.telephony import active_telephony_provider

    settings = get_settings()
    active_prov = active_telephony_provider()
    voice_list = await voice_kyc_service.list_voice_verifications(status=status)
    didit_list = await kyc_service.list_verifications(status=status)

    voice_rows = []
    for v in voice_list:
        voice_rows.append({
            "userId": v["tenantId"],
            "tenantId": v["tenantId"],
            "tenantName": v["tenantName"],
            "email": v["accountEmail"],
            "fullName": f"{v['legalName']} ({v['businessType'].replace('_', ' ').title()})",
            "status": v["status"],
            "approved": v["approved"],
            "callsBlocked": v["callsBlocked"],
            "updatedAt": v["updatedAt"],
            "verifiedAt": v["updatedAt"] if v["approved"] else None,
            "kycType": "voice",
            "provider": "vobiz",
            "verifications": v["verifications"],
            "sessionId": v.get("subaccountAuthId"),
            "decision": {
                "source": "vobiz_subaccount",
                "actor": "carrier_hosted_kyc",
                "reason": f"Carrier KYC {v['rawKycStatus']} (Calls blocked: {v['callsBlocked']})",
                "at": v["updatedAt"],
            },
        })

    # Prioritize active provider's voice KYC records at top of queue
    merged = voice_rows + didit_list

    return {
        "configured": kyc_service.is_configured() or voice_kyc_service._carrier_setup_configured(),
        "workflowId": settings.didit_workflow_id or None,
        "gatePurchases": bool(settings.kyc_gate_purchases),
        "activeProvider": active_prov,
        "verifications": merged,
        "voiceVerifications": voice_list,
        "diditVerifications": didit_list,
    }


@router.post("/api/dev/admin/kyc/{user_id}/status")
async def set_kyc_status(
    user_id: str,
    body: KycStatusBody,
    session: SessionData = Depends(require_dev_session),
):
    """Manual Approve / Decline / reset for Vobiz Voice KYC subaccounts and Didit."""
    require_permission(session, "dev.admin.users")
    _require_db()
    from server.services.saas import kyc_service
    from server.services.saas import voice_kyc_service

    reason = (body.reason or "").strip()
    if len(reason) < 8:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "statement_required",
                    "message": "Write a short statement (8+ chars) before changing verification status.",
                }
            },
        )

    try:
        uid = uuid.UUID(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_user_id") from exc

    # Check if this ID belongs to a tenant Voice KYC subaccount
    account = await voice_kyc_service._get_account(uid)
    if account is not None:
        try:
            state = await voice_kyc_service.admin_set_voice_kyc_status(
                tenant_id=uid,
                status=body.status,
                actor=session.subject,
                reason=reason,
            )
        except voice_kyc_service.VoiceKycError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail={"error": {"code": exc.code, "message": str(exc)}},
            ) from exc

        await record_admin_action(
            actor=session.subject,
            action="voice_kyc.status",
            resource_type="voice_kyc",
            resource_id=user_id,
            tenant_id=uid,
            payload={"status": body.status, "reason": reason, "decision": state.get("status")},
        )
        return {"ok": True, "verification": state}

    try:
        state = await kyc_service.admin_set_status(
            user_id=uid,
            status=body.status,
            actor=session.subject,
            reason=reason,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "invalid_status", "message": str(exc)}},
        ) from exc

    await record_admin_action(
        actor=session.subject,
        action="kyc.status",
        resource_type="kyc",
        resource_id=user_id,
        payload={"status": body.status, "reason": reason, "decision": state.get("decision")},
    )
    return {"ok": True, "verification": state}


class VoiceKycAdminStatusBody(BaseModel):
    status: str
    reason: str | None = None


@router.get("/api/dev/admin/kyc/voice/{tenant_id}/status")
async def get_tenant_voice_kyc(
    tenant_id: str,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.users")
    _require_db()
    from server.services.saas import voice_kyc_service

    try:
        tid = uuid.UUID(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_tenant_id") from exc
    return await voice_kyc_service.refresh_kyc_status(tid)


@router.post("/api/dev/admin/kyc/voice/{tenant_id}/status")
async def set_tenant_voice_kyc(
    tenant_id: str,
    body: VoiceKycAdminStatusBody,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.users")
    _require_db()
    from server.services.saas import voice_kyc_service

    try:
        tid = uuid.UUID(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_tenant_id") from exc
    reason = (body.reason or "").strip()
    if len(reason) < 8:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "statement_required",
                    "message": "Write a short statement (8+ chars) before changing verification status.",
                }
            },
        )
    try:
        updated = await voice_kyc_service.admin_set_voice_kyc_status(
            tenant_id=tid,
            status=body.status,
            actor=session.subject,
            reason=reason,
        )
    except voice_kyc_service.VoiceKycError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
    await record_admin_action(
        actor=session.subject,
        action="voice_kyc.status",
        resource_type="voice_kyc",
        resource_id=tenant_id,
        payload={"status": body.status, "reason": reason},
    )
    return {"ok": True, "status": updated}



@router.get("/api/dev/admin/support/config")
async def platform_support_config(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.support")
    from server.services.saas.customer_support_service import get_support_config

    return {"ok": True, "config": await get_support_config(for_admin=True)}


@router.put("/api/dev/admin/support/config")
async def update_platform_support_config(
    body: PlatformSupportConfigBody,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.support")
    from server.services.saas.customer_support_service import update_support_config

    updates = body.model_dump(exclude_unset=True)
    config = await update_support_config(updates)
    await record_admin_action(
        actor=session.subject,
        action="support.config.update",
        resource_type="support_config",
        resource_id="global",
        payload={"fields": sorted(updates.keys())},
    )
    return {"ok": True, "config": config}


@router.post("/api/dev/admin/support/smtp/test")
async def test_platform_smtp(
    body: PlatformSmtpTestBody,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.support")
    from server.services.saas.customer_support_service import test_smtp_configuration

    result = await test_smtp_configuration(body.model_dump())
    await record_admin_action(
        actor=session.subject,
        action="support.smtp.test",
        resource_type="support_config",
        resource_id="global",
        payload={"success": bool(result.get("success"))},
    )
    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "smtp_test_failed", "message": result.get("error") or "SMTP test failed"}},
        )
    return {"ok": True, "message": result.get("message")}


@router.get("/api/dev/admin/support/inquiries")
async def list_platform_support_inquiries(
    status: Optional[str] = Query(None, max_length=32),
    priority: Optional[str] = Query(None, max_length=32),
    category: Optional[str] = Query(None, max_length=64),
    search: Optional[str] = Query(None, max_length=200),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.support")
    from server.services.saas.customer_support_service import list_support_inquiries

    return {
        "ok": True,
        "inquiries": await list_support_inquiries(
            status=status,
            priority=priority,
            category=category,
            search=search,
            limit=limit,
            offset=offset,
        ),
    }


@router.get("/api/dev/admin/support/inquiries/{inquiry_id}")
async def get_platform_support_inquiry(
    inquiry_id: str,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.support")
    from server.services.saas.customer_support_service import get_support_inquiry_detail

    try:
        inquiry_uuid = uuid.UUID(inquiry_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_inquiry_id") from exc
    inquiry = await get_support_inquiry_detail(inquiry_uuid)
    if not inquiry:
        raise HTTPException(status_code=404, detail="not_found")
    return {"ok": True, "inquiry": inquiry}


@router.patch("/api/dev/admin/support/inquiries/{inquiry_id}")
async def update_platform_support_inquiry(
    inquiry_id: str,
    body: PlatformSupportInquiryPatchBody,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.support")
    from server.services.saas.customer_support_service import update_support_inquiry

    try:
        inquiry_uuid = uuid.UUID(inquiry_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_inquiry_id") from exc
    updates = body.model_dump(exclude_unset=True)
    try:
        inquiry = await update_support_inquiry(
            inquiry_id=inquiry_uuid,
            status=body.status,
            assigned_to=body.assignedTo,
            admin_notes=body.adminNotes,
            resolution_notes=body.resolutionNotes,
            reply_message=body.replyMessage,
            reply_author=session.subject,
            tags=body.tags,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="not_found") from exc
    await record_admin_action(
        actor=session.subject,
        action="support.inquiry.update",
        resource_type="support_inquiry",
        resource_id=inquiry_id,
        payload={"fields": sorted(updates.keys()), "status": body.status},
    )
    return {"ok": True, "inquiry": inquiry}


@router.get("/api/dev/admin/numbers/carrier-search")
async def search_platform_carrier_numbers(
    provider: str = Query("vobiz", pattern="^(vobiz|telnyx)$"),
    country: str = Query("US", max_length=8),
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.numbers")
    from server.services.telephony import active_telephony_provider

    provider_id = provider.lower()
    if provider_id != active_telephony_provider():
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "inactive_provider", "message": "Switch the active carrier before searching its inventory."}},
        )
    _require_db()
    from server.services.saas.billing_rates import load_current_rates
    from server.services.saas.telephony_countries import normalize_buy_country

    default_country = "IN" if provider_id == "vobiz" else "US"
    country_code = normalize_buy_country(country, default=default_country)
    try:
        if provider_id == "vobiz":
            from server.services.vobiz_client import VobizClient

            available = await VobizClient().search_available_numbers(country=country_code, limit=15)
        else:
            from server.services.telnyx_client import TelnyxClient

            available = await TelnyxClient().search_available_numbers(country=country_code, limit=15)
    except Exception as exc:
        logger.warning("Platform carrier inventory search failed (%s)", provider_id)
        raise HTTPException(status_code=502, detail="Carrier inventory is temporarily unavailable") from exc

    async with get_session_factory()() as db:
        active = (
            await db.execute(select(PhoneNumber.e164).where(PhoneNumber.released_at.is_(None)))
        ).scalars().all()
    unavailable = {str(number).strip() for number in active if number}
    seen: set[str] = set()
    rates = await load_current_rates()
    cleaned = []
    for item in available or []:
        row = dict(item) if isinstance(item, dict) else {"e164": str(item)}
        e164 = str(row.get("e164") or row.get("phone_number") or "").strip()
        if not e164 or e164 in unavailable or e164 in seen:
            continue
        seen.add(e164)
        cleaned.append({
            **row,
            "e164": e164,
            "provider": provider_id,
            "country": country_code,
            "monthlyUsd": round(rates["did_monthly_usd_cents"] / 100.0, 2),
            "monthlyInr": round(rates["did_monthly_inr_paise"] / 100.0, 2),
        })
    return {"numbers": cleaned, "provider": provider_id, "country": country_code}


@router.post("/api/dev/admin/numbers/carrier-purchase")
async def purchase_platform_carrier_number(
    body: DirectCarrierPurchaseBody,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.numbers")
    from server.services.telephony import active_telephony_provider

    if body.provider != active_telephony_provider():
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "inactive_provider", "message": "Switch the active carrier before ordering a number."}},
        )
    _require_db()
    from server.services.saas.number_purchase_service import normalize_e164

    try:
        e164 = normalize_e164(body.e164)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_e164") from exc
    try:
        tenant_uuid = uuid.UUID(body.tenantId)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_tenant_id") from exc

    factory = get_session_factory()
    from sqlalchemy.exc import IntegrityError

    async with factory() as db:
        tenant = await db.get(Tenant, tenant_uuid)
        if tenant is None:
            raise HTTPException(status_code=404, detail="tenant_not_found")
        from server.services.saas.number_inventory import is_platform_inventory_tenant
        customer_account = body.provider == "vobiz" and not is_platform_inventory_tenant(tenant)
        if customer_account:
            from server.services.saas.voice_kyc_service import assert_voice_kyc_approved
            await assert_voice_kyc_approved(tenant_uuid, action="activate a phone number")
        existing = (
            await db.execute(
                select(PhoneNumber.id).where(
                    PhoneNumber.e164 == e164,
                    PhoneNumber.released_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail="number_already_active")

        # Reserve the number before contacting the carrier. The active-number
        # partial unique index makes concurrent admin requests race-safe.
        reservation = PhoneNumber(
            tenant_id=tenant_uuid,
            e164=e164,
            status="provisioning",
            billing_source="admin",
            inbound_enabled=True,
            outbound_enabled=True,
            vobiz_account_scope="tenant" if customer_account else None,
            vobiz_account_tenant_id=tenant_uuid if customer_account else None,
        )
        db.add(reservation)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(status_code=409, detail="number_already_active") from None
        number_id = reservation.id

    try:
        if body.provider == "vobiz":
            from server.services.vobiz_client import VobizClient
            if customer_account:
                from server.services.saas.voice_kyc_service import provision_tenant_number
                carrier_result = await provision_tenant_number(tenant_uuid, e164)
            else:
                carrier_result = await VobizClient().provision_ordered_number(e164)
        else:
            from server.services.telnyx_client import TelnyxClient
            from server.services.telnyx_provisioning import provision_ordered_number

            carrier_result = await provision_ordered_number(TelnyxClient(), e164)
    except Exception:
        logger.warning("Platform carrier number purchase failed (%s)", body.provider)
        # A timeout may mean the provider accepted the order but its response was
        # lost. Keep the reservation active so a retry cannot buy the same number
        # twice; an admin can reconcile this row before releasing it.
        try:
            async with factory() as db:
                reserved = await db.get(PhoneNumber, number_id, with_for_update=True)
                if reserved is not None and reserved.status == "provisioning":
                    reserved.status = "provisioning_failed"
                    await db.commit()
        except Exception:
            logger.warning("Platform carrier reservation could not be updated after failure")
        raise HTTPException(status_code=502, detail="Carrier could not provision this number") from None

    carrier_phone_id = carrier_result.get("phone_number_id")
    telnyx_number_id = (
        str(carrier_phone_id)
        if body.provider == "telnyx" and carrier_phone_id
        else None
    )
    number_status = "active" if carrier_phone_id else "pending"
    async with factory() as db:
        number = await db.get(PhoneNumber, number_id, with_for_update=True)
        if number is None:
            raise HTTPException(status_code=500, detail="number_reservation_missing")
        number.status = number_status
        number.telnyx_number_id = telnyx_number_id
        number.carrier_number_id = (
            str(carrier_phone_id) if body.provider == "vobiz" and carrier_phone_id else None
        )
        await db.commit()
        await db.refresh(number)
        number_id = str(number.id)
    await record_admin_action(
        actor=session.subject,
        action="number.carrier_purchase",
        resource_type="phone_number",
        resource_id=number_id,
        tenant_id=tenant_uuid,
        payload={"provider": body.provider, "reason": body.reason, "status": number_status},
    )
    return {
        "ok": True,
        "id": number_id,
        "provider": body.provider,
        "tenantId": str(tenant_uuid),
        "status": number_status,
        "provisioning": number_status == "pending",
    }


# ---------------------------------------------------------------------------
# Technical-fallback (TTS outage) announcements — platform-owned configuration.
#
# Tenants never see or edit these. The live call path reads the agent row and
# the uploaded clips directly, so moving the controls to the admin portal
# changes who can configure the announcement, not how it plays.
# ---------------------------------------------------------------------------


class AgentTechnicalFallbackBody(BaseModel):
    promiseCallback: Optional[bool] = None
    transcript: Optional[str] = Field(None, max_length=255)


_VARIANT_LABELS = {
    "callback_promise": "Callback promise",
    "call_back": "Call-back request",
    "disclosure": "Recording disclosure",
}


def _admin_agent_id(agent_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(agent_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Agent not found") from exc


async def _admin_agent_tenant(agent_id: str) -> tuple[Agent, uuid.UUID]:
    _require_db()
    aid = _admin_agent_id(agent_id)
    async with get_session_factory()() as db:
        agent = await db.get(Agent, aid)
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        return agent, agent.tenant_id


def _fallback_clip_http_error(exc: Exception) -> HTTPException:
    from server.services.fallback_clip_store import FallbackClipError

    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail="Clip not found")
    if isinstance(exc, FallbackClipError):
        return HTTPException(
            status_code=exc.status_code,
            detail={"error": {"code": exc.code, "message": str(exc)}},
        )
    return HTTPException(status_code=503, detail="Fallback clips are unavailable")


def _fallback_supported_languages(agent: Agent) -> list[str]:
    from server.services.pstn_technical_fallback import CALL_BACK, FALLBACK_TEXT

    platform = list(FALLBACK_TEXT[CALL_BACK].keys())
    spoken = [str(code) for code in (agent.languages or []) if str(code).strip()]
    return list(dict.fromkeys(spoken + platform))


@router.get("/api/dev/admin/agents/{agent_id}/technical-fallback")
async def get_agent_technical_fallback(
    agent_id: str,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.tenants")
    from server.services import fallback_clip_store
    from server.services.pstn_technical_fallback import CLIP_VARIANTS, FALLBACK_TEXT

    agent, tenant_id = await _admin_agent_tenant(agent_id)
    try:
        clips = await fallback_clip_store.list_clips(tenant_id=str(tenant_id), agent_id=str(agent.agent_id))
    except Exception as exc:
        raise _fallback_clip_http_error(exc) from None
    languages = _fallback_supported_languages(agent)
    return {
        "agentId": str(agent.agent_id),
        "tenantId": str(tenant_id),
        "name": agent.name,
        "spokenLanguages": list(agent.languages or []),
        "languages": languages,
        "promiseCallback": bool(agent.technical_fallback_promise_callback),
        "transcript": agent.technical_fallback_text or "",
        "variants": [
            {
                "id": variant,
                "label": _VARIANT_LABELS.get(variant, variant.replace("_", " ").title()),
            }
            for variant in CLIP_VARIANTS
        ],
        "defaults": {
            language: {variant: FALLBACK_TEXT[variant].get(language, FALLBACK_TEXT[variant]["en-IN"]) for variant in CLIP_VARIANTS}
            for language in languages
        },
        "clips": clips,
    }


@router.patch("/api/dev/admin/agents/{agent_id}/technical-fallback")
async def patch_agent_technical_fallback(
    agent_id: str,
    body: AgentTechnicalFallbackBody,
    request: Request,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.tenants")
    _require_db()
    aid = _admin_agent_id(agent_id)
    async with get_session_factory()() as db:
        agent = await db.get(Agent, aid, with_for_update=True)
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        if body.promiseCallback is not None:
            agent.technical_fallback_promise_callback = body.promiseCallback
        if body.transcript is not None:
            agent.technical_fallback_text = body.transcript.strip()
        await db.commit()
        await db.refresh(agent)
        result = {
            "agentId": str(agent.agent_id),
            "promiseCallback": bool(agent.technical_fallback_promise_callback),
            "transcript": agent.technical_fallback_text or "",
        }
        tenant_id = agent.tenant_id
    await record_admin_action(
        actor=session.subject,
        action="agent.technical_fallback.update",
        resource_type="agent",
        resource_id=agent_id,
        tenant_id=tenant_id,
        payload=result,
        request=request,
    )
    return {"ok": True, **result}


@router.put("/api/dev/admin/agents/{agent_id}/technical-fallback/clips/{language}/{variant}")
async def upload_agent_technical_fallback_clip(
    agent_id: str,
    language: str,
    variant: str,
    request: Request,
    file: UploadFile = File(..., description="16-bit PCM WAV, mono or stereo, ≤2 MB, ≤30 s"),
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.tenants")
    from server.services import fallback_clip_store

    agent, tenant_id = await _admin_agent_tenant(agent_id)
    try:
        raw = await file.read(fallback_clip_store.MAX_UPLOAD_BYTES + 1)
        clip = await fallback_clip_store.upsert_clip(
            tenant_id=str(tenant_id),
            agent_id=str(agent.agent_id),
            language=language,
            variant=variant,
            raw=raw,
        )
    except Exception as exc:
        raise _fallback_clip_http_error(exc) from None
    await record_admin_action(
        actor=session.subject,
        action="agent.technical_fallback.clip_upload",
        resource_type="agent",
        resource_id=agent_id,
        tenant_id=tenant_id,
        payload={"language": clip["language"], "variant": clip["variant"], "durationMs": clip["durationMs"]},
        request=request,
    )
    return {"ok": True, "clip": clip}


@router.delete("/api/dev/admin/agents/{agent_id}/technical-fallback/clips/{language}/{variant}")
async def delete_agent_technical_fallback_clip(
    agent_id: str,
    language: str,
    variant: str,
    request: Request,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.tenants")
    from server.services import fallback_clip_store

    agent, tenant_id = await _admin_agent_tenant(agent_id)
    try:
        await fallback_clip_store.delete_clip(
            tenant_id=str(tenant_id),
            agent_id=str(agent.agent_id),
            language=language,
            variant=variant,
        )
    except Exception as exc:
        raise _fallback_clip_http_error(exc) from None
    await record_admin_action(
        actor=session.subject,
        action="agent.technical_fallback.clip_delete",
        resource_type="agent",
        resource_id=agent_id,
        tenant_id=tenant_id,
        payload={"language": language, "variant": variant},
        request=request,
    )
    return {"ok": True}


@router.get("/api/dev/admin/agents/{agent_id}/technical-fallback/clips/{language}/{variant}/audio")
async def get_agent_technical_fallback_clip_audio(
    agent_id: str,
    language: str,
    variant: str,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.tenants")
    from server.services.fallback_clip_store import validate_language, validate_variant

    agent, tenant_id = await _admin_agent_tenant(agent_id)
    try:
        language = validate_language(language)
        variant = validate_variant(variant)
    except ValueError as exc:
        raise _fallback_clip_http_error(exc) from None
    async with get_session_factory()() as db:
        row = (
            await db.execute(
                select(AgentFallbackClip).where(
                    AgentFallbackClip.tenant_id == tenant_id,
                    AgentFallbackClip.agent_id == agent.agent_id,
                    AgentFallbackClip.language == language,
                    AgentFallbackClip.variant == variant,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Clip not found")
        pcm = bytes(row.pcm_bytes)
        rate = int(row.sample_rate or 8000)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return Response(
        content=buffer.getvalue(),
        media_type="audio/wav",
        headers={"Cache-Control": "no-store", "Content-Disposition": "inline"},
    )


class SpeechOutageBody(BaseModel):
    enabled: Optional[bool] = None
    promiseCallback: Optional[bool] = None


@router.get("/api/dev/admin/speech-outage")
async def get_speech_outage(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.tenants")
    from server.services.pstn_technical_fallback import CLIP_VARIANTS, platform_clip_coverage
    from server.services.speech_outage_config import load_speech_outage_config

    config = await load_speech_outage_config(force=True)
    return {
        "global": config.to_api(),
        "coverage": platform_clip_coverage(),
        "variants": [{"id": variant, "label": _VARIANT_LABELS.get(variant, variant)} for variant in CLIP_VARIANTS],
    }


@router.patch("/api/dev/admin/speech-outage")
async def patch_speech_outage(
    body: SpeechOutageBody,
    request: Request,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.tenants")
    from server.services.speech_outage_config import (
        load_speech_outage_config,
        save_speech_outage_config,
    )

    current = await load_speech_outage_config(force=True)
    updated = await save_speech_outage_config(
        enabled=current.enabled if body.enabled is None else bool(body.enabled),
        promise_callback=(
            current.promise_callback if body.promiseCallback is None else bool(body.promiseCallback)
        ),
        actor=session.subject,
    )
    await record_admin_action(
        actor=session.subject,
        action="speech_outage.patch",
        resource_type="speech_outage",
        resource_id="global",
        payload={
            "enabled": updated.enabled,
            "promiseCallback": updated.promise_callback,
            "version": updated.version,
        },
        request=request,
    )
    return {"ok": True, "global": updated.to_api()}
