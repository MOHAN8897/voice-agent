"""Platform dev admin ? SaaS operations (PRD-06)."""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, desc, func, select, update

from server.config.env import get_settings

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
from server.db.models.entities import Agent, Call, CallAttempt, Tenant
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


_TENANT_STATUS_VALUES = frozenset({"active", "suspended", "past_due", "cancelled"})
_TENANT_PLAN_VALUES = frozenset({"starter", "growth", "enterprise", "default", "platform", "dev"})


class TenantDeleteBody(BaseModel):
    force: bool = False
    note: Optional[str] = Field(None, max_length=500)


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
        stmt = select(Tenant).where(Tenant.deleted_at.is_(None))
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

        from server.services.saas.billing_rates import effective_rates

        fx = float(effective_rates()["fx_rate_inr"]) or 95.64

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
        "verifications": verifications,
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


@router.delete("/api/dev/admin/tenants/{tenant_id}")
async def delete_tenant(
    tenant_id: str,
    force: bool = Query(False),
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.tenants")
    _require_db()
    tid = uuid.UUID(tenant_id)
    async with get_session_factory()() as db:
        tenant = await db.get(Tenant, tid)
        if tenant is None or tenant.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Not found")
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
        if active_numbers and not force:
            raise HTTPException(
                status_code=400,
                detail=f"Tenant still has {active_numbers} active number(s). Release them or pass force=true.",
            )
        tenant.status = "cancelled"
        tenant.deleted_at = datetime.now(timezone.utc)
        await db.commit()
    await record_admin_action(
        actor=session.subject,
        action="tenant.delete",
        resource_type="tenant",
        resource_id=tenant_id,
        tenant_id=tid,
        payload={"force": force},
    )
    return {"ok": True}


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
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.users")
    _require_db()
    async with get_session_factory()() as db:
        if tenantId:
            tid = uuid.UUID(tenantId)
            rows = (
                await db.execute(
                    select(User, TenantMembership)
                    .join(TenantMembership, TenantMembership.user_id == User.user_id)
                    .where(TenantMembership.tenant_id == tid)
                )
            ).all()
            users = [
                {"userId": str(u.user_id), "email": u.email, "status": u.status, "role": m.role}
                for u, m in rows
            ]
        else:
            users = [
                {"userId": str(u.user_id), "email": u.email, "status": u.status, "fullName": u.full_name}
                for u in (await db.execute(select(User).where(User.deleted_at.is_(None)).limit(500))).scalars()
            ]
    return {"users": users}


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
    since = datetime.now(timezone.utc) - timedelta(days=days)
    day0 = since.date().isoformat()

    async with get_session_factory()() as db:
        async def scalar(stmt):
            return (await db.execute(stmt)).scalar()

        # Call volume and talk time per day, PSTN only (a browser test is not usage).
        daily = (
            await db.execute(
                select(
                    func.date(Call.started_at).label("d"),
                    func.count(Call.call_id),
                    func.coalesce(func.sum(Call.duration_sec), 0),
                )
                .where(Call.started_at.isnot(None), Call.started_at >= since)
                .group_by(func.date(Call.started_at))
                .order_by(func.date(Call.started_at))
            )
        ).all()
        daily_series = [
            {"date": str(r[0]), "calls": int(r[1] or 0), "seconds": int(r[2] or 0)}
            for r in daily
        ]

        by_status = (
            await db.execute(
                select(Call.status, func.count(Call.call_id))
                .where(Call.started_at >= since)
                .group_by(Call.status)
            )
        ).all()
        by_direction = (
            await db.execute(
                select(Call.direction, func.count(Call.call_id))
                .where(Call.started_at >= since)
                .group_by(Call.direction)
            )
        ).all()
        by_channel = (
            await db.execute(
                select(Call.channel, func.count(Call.call_id), func.coalesce(func.sum(Call.duration_sec), 0))
                .where(Call.started_at >= since)
                .group_by(Call.channel)
            )
        ).all()

        # Missed calls are a first-class outcome now, so surface them separately.
        missed = int(
            await scalar(
                select(func.count())
                .select_from(CallAttempt)
                .where(CallAttempt.started_at >= since, CallAttempt.status.in_(("missed", "no_answer")))
            )
            or 0
        )

        # Money in: wallet top-ups only. Debits are spend, not revenue.
        topups = (
            await db.execute(
                select(
                    func.date(BillingWalletTransaction.created_at).label("d"),
                    func.coalesce(func.sum(BillingWalletTransaction.amount_cents), 0),
                    func.coalesce(func.sum(BillingWalletTransaction.amount_inr_paise), 0),
                )
                .where(
                    BillingWalletTransaction.kind.in_(("topup", "top_up", "deposit")),
                    BillingWalletTransaction.created_at >= since,
                )
                .group_by(func.date(BillingWalletTransaction.created_at))
                .order_by(func.date(BillingWalletTransaction.created_at))
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
        top_tenants = (
            await db.execute(
                select(Tenant.name, func.count(Call.call_id))
                .select_from(Call)
                .join(Tenant, Tenant.tenant_id == Call.tenant_id)
                .where(Call.started_at >= since)
                .group_by(Tenant.name)
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
    return {
        "assignments": [
            {
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
                "status": pn.status,
                "billingSource": pn.billing_source,
                "walletBalanceUsd": round((w.balance_cents or 0) / 100.0, 2) if w else 0,
                "walletBalanceInr": round((w.balance_inr_paise or 0) / 100.0, 2) if w else 0,
                "walletCurrency": ((w.currency if w else None) or "usd").upper(),
                "createdAt": pn.created_at.isoformat() if pn.created_at else None,
            }
            for pn, t, a, np, w in rows
        ],
        "inventoryTenantName": INVENTORY_TENANT_NAME,
    }


@router.get("/api/dev/admin/numbers/pool")
async def number_pool(session: SessionData = Depends(require_dev_session)):
    """All account DIDs (Telnyx + DB) with tenant assignment — pick one then assign."""
    require_permission(session, "dev.admin.numbers")
    _require_db()
    from server.services.saas.number_inventory import INVENTORY_TENANT_NAME, ensure_platform_inventory_tenant

    inventory_tid = await ensure_platform_inventory_tenant()
    inventory_tid_s = str(inventory_tid)
    by_e164: dict[str, dict[str, Any]] = {}

    async with get_session_factory()() as db:
        rows = (
            await db.execute(
                select(PhoneNumber, Tenant)
                .outerjoin(Tenant, Tenant.tenant_id == PhoneNumber.tenant_id)
                .where(PhoneNumber.released_at.is_(None))
            )
        ).all()
        for pn, t in rows:
            tenant_gone = t is None or t.deleted_at is not None or getattr(t, "status", "active") == "cancelled"
            in_inventory = pn.tenant_id == inventory_tid or (t is not None and t.name == INVENTORY_TENANT_NAME)
            by_e164[pn.e164] = {
                "e164": pn.e164,
                "numberId": str(pn.id),
                "telnyxNumberId": pn.telnyx_number_id,
                "tenantId": None
                if tenant_gone or in_inventory
                else (str(pn.tenant_id) if pn.tenant_id else None),
                "tenantName": (
                    INVENTORY_TENANT_NAME
                    if in_inventory
                    else (None if tenant_gone else (t.name if t else None))
                ),
                "status": pn.status,
                "source": "inventory" if in_inventory else "database",
                "inInventory": in_inventory,
                # Platform inventory + unassigned + cancelled tenants are allocatable.
                "available": tenant_gone or in_inventory or not pn.tenant_id,
            }

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
            tid = str(row.get("id") or "")
            existing = by_e164.get(phone)
            if existing:
                if tid and not existing.get("telnyxNumberId"):
                    existing["telnyxNumberId"] = tid
                existing["source"] = (
                    "telnyx+inventory" if existing.get("inInventory") else "telnyx+database"
                )
            else:
                by_e164[phone] = {
                    "e164": phone,
                    "numberId": None,
                    "telnyxNumberId": tid or None,
                    "tenantId": None,
                    "tenantName": None,
                    "status": "unassigned",
                    "source": "telnyx",
                    "inInventory": False,
                    "available": True,
                }
    except Exception as exc:
        return {
            "numbers": sorted(by_e164.values(), key=lambda n: n["e164"]),
            "inventoryTenantId": inventory_tid_s,
            "telnyxError": str(exc)[:300],
        }

    for item in by_e164.values():
        # Never wipe inventory availability — only customer tenantIds block the pool.
        if item.get("inInventory"):
            item["available"] = True
            item["tenantId"] = None
        else:
            item["available"] = not bool(item.get("tenantId"))
    return {
        "numbers": sorted(
            by_e164.values(),
            key=lambda n: (0 if n.get("available") else 1, n["e164"]),
        ),
        "inventoryTenantId": inventory_tid_s,
    }


@router.post("/api/dev/admin/numbers/allocate")
async def allocate_number(body: AllocateNumberBody, session: SessionData = Depends(require_dev_session)):
    """Assign an existing DID (Telnyx or already in DB) to a tenant. Creates wallet if missing."""
    require_permission(session, "dev.admin.numbers")
    _require_db()
    e164 = body.e164.strip()
    if not e164.startswith("+"):
        raise HTTPException(status_code=400, detail="E.164 required (e.g. +15551234567)")
    tid = uuid.UUID(body.tenantId)
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
            existing.tenant_id = tid
            if body.telnyxNumberId:
                existing.telnyx_number_id = body.telnyxNumberId
            existing.status = "active"
            pn = existing
        else:
            pn = PhoneNumber(
                tenant_id=tid,
                e164=e164,
                status="active",
                billing_source="manual",
                telnyx_number_id=body.telnyxNumberId,
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
        payload={"e164": e164, "telnyxNumberId": body.telnyxNumberId},
    )
    return {"ok": True, "numberId": str(pn.id), "e164": e164, "tenantId": str(tid)}


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
    async with get_session_factory()() as db:
        purchase = await db.get(NumberPurchase, pid)
        if purchase is None:
            raise HTTPException(status_code=404, detail="Not found")
        if settings.stripe_secret_key and purchase.stripe_payment_intent_id:
            import stripe

            stripe.api_key = settings.stripe_secret_key
            stripe.Refund.create(payment_intent=purchase.stripe_payment_intent_id)
        purchase.status = "refunded"
        await db.commit()
    await record_admin_action(
        actor=session.subject,
        action="purchase.refund",
        resource_type="purchase",
        resource_id=purchase_id,
        tenant_id=purchase.tenant_id,
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
    from server.services.saas.billing_rates import effective_rates

    fx = float(effective_rates()["fx_rate_inr"]) or 95.64
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


@router.post("/api/dev/admin/wallets/adjust")
async def adjust_wallet(body: WalletAdjustBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.billing")
    _require_db()
    from server.services.saas.billing_rates import usd_to_inr_cents
    from server.services.saas.billing_wallet_service import (
        credit_wallet,
        debit_wallet,
        get_or_create_wallet,
        wallet_summary,
    )

    cents = body.amountUsdCents
    if cents is None and body.amountInrPaise is not None:
        # Legacy clients send INR; convert so the rest of the path stays USD-authored.
        from server.services.saas.billing_rates import effective_rates

        fx = float(effective_rates()["fx_rate_inr"]) or 95.64
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
    paise = usd_to_inr_cents(abs(cents))
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
    """USD prices plus the chargeable FX rate.

    INR fields are accepted for backwards compatibility but ignored: prices are
    authored in USD and the INR figure is derived, so a stored rupee price could
    drift away from the dollar price it is supposed to mirror.
    """

    pstnUsdPerMin: float | None = Field(None, ge=0.001, le=100)
    webUsdPerMin: float | None = Field(None, ge=0.001, le=100)
    #: Monthly rental for a bought phone number.
    numberMonthlyUsd: float | None = Field(None, ge=0, le=100000)
    fxRateInr: float | None = Field(None, ge=0.01, le=100000)
    # Deprecated, ignored. Kept so an old admin client does not 422.
    pstnInrPerMin: float | None = None
    webInrPerMin: float | None = None
    didMonthlyInr: float | None = None


def _rates_payload(r: dict[str, int | float]) -> dict[str, float]:
    return {
        "pstnUsdPerMin": round(r["pstn_rate_usd_cents_per_min"] / 100.0, 3),
        "webUsdPerMin": round(r["web_agent_rate_usd_cents_per_min"] / 100.0, 3),
        "numberMonthlyUsd": round(r["did_monthly_usd_cents"] / 100.0, 2),
        "fxRateInr": round(float(r["fx_rate_inr"]), 4),
        # Derived mirrors — display only, never charged.
        "pstnInrPerMin": round(r["pstn_rate_inr_paise_per_min"] / 100.0, 2),
        "webInrPerMin": round(r["web_agent_rate_inr_paise_per_min"] / 100.0, 2),
        "numberMonthlyInr": round(r["did_monthly_inr_paise"] / 100.0, 2),
    }


@router.get("/api/dev/admin/billing-rates")
async def get_billing_rates(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.billing")
    from server.services.saas.billing_rates import live_fx, rates_with_derived_inr

    return {
        "currency": "USD",
        "rates": _rates_payload(rates_with_derived_inr()),
        # Market rate for reference in the converter; charging uses fxRateInr.
        "fx": live_fx(),
    }


@router.put("/api/dev/admin/billing-rates")
async def put_billing_rates(body: BillingRatesBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.billing")
    from server.services.saas.billing_rates import rates_with_derived_inr, update_rates

    r = update_rates(
        pstn_usd_per_min=body.pstnUsdPerMin,
        web_usd_per_min=body.webUsdPerMin,
        did_monthly_usd=body.numberMonthlyUsd,
        fx_rate_inr=body.fxRateInr,
    )
    await record_admin_action(
        actor=session.subject,
        action="billing.rates",
        resource_type="platform",
        resource_id="rates",
        payload=body.model_dump(exclude_none=True),
    )
    return {"ok": True, "currency": "USD", "rates": _rates_payload(r)}

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
    from server.services.saas.payment_settings import settings_state, update_settings

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


@router.get("/api/dev/admin/payments/orders")
async def list_payment_orders(
    limit: int = Query(50, ge=1, le=200),
    session: SessionData = Depends(require_dev_session),
):
    """Recent top-up orders with the currency each was charged in."""
    require_permission(session, "dev.admin.billing")
    _require_db()
    from server.db.models.saas_models import RazorpayOrder
    from server.services.saas.razorpay_service import from_minor

    async with get_session_factory()() as db:
        rows = (
            await db.execute(
                select(RazorpayOrder, Tenant)
                .outerjoin(Tenant, Tenant.tenant_id == RazorpayOrder.tenant_id)
                .order_by(desc(RazorpayOrder.created_at))
                .limit(limit)
            )
        ).all()
        return {
            "orders": [
                {
                    "orderId": order.order_id,
                    "tenantId": str(order.tenant_id),
                    "tenantName": tenant.name if tenant else None,
                    "status": order.status,
                    "currency": getattr(order, "currency", None) or "INR",
                    "amount": from_minor(order.amount_minor, getattr(order, "currency", None) or "INR")
                    if getattr(order, "amount_minor", None)
                    else order.amount_inr_paise / 100,
                    "amountInr": order.amount_inr_paise / 100,
                    "createdAt": order.created_at.isoformat() if order.created_at else None,
                }
                for order, tenant in rows
            ]
        }


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
    """Identity verification queue for ops — Didit webhook state + manual overrides."""
    require_permission(session, "dev.admin.users")
    _require_db()
    from server.config.env import get_settings
    from server.services.saas import kyc_service

    settings = get_settings()
    return {
        "configured": kyc_service.is_configured(),
        "workflowId": settings.didit_workflow_id or None,
        "gatePurchases": bool(settings.kyc_gate_purchases),
        "verifications": await kyc_service.list_verifications(status=status),
    }


@router.post("/api/dev/admin/kyc/{user_id}/status")
async def set_kyc_status(
    user_id: str,
    body: KycStatusBody,
    session: SessionData = Depends(require_dev_session),
):
    """Manual Approve / Decline / reset when Didit stalls or a webhook is missed."""
    require_permission(session, "dev.admin.users")
    _require_db()
    from server.services.saas import kyc_service

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
