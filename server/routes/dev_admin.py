"""Platform dev admin — SaaS operations (PRD-06)."""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, desc, func, select, update

from server.config.env import get_settings

from server.auth.dependencies import require_dev_session, require_permission
from server.auth.passwords import hash_portal_password
from server.auth.session import SessionData
from server.db.connection import get_session_factory
from server.db.models.entities import Agent, Call, Tenant
from server.db.models.phase5_models import PhoneNumber
from server.db.models.saas_models import (
    AuthEvent,
    NumberPurchase,
    ProvisionJob,
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
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.tenants")
    _require_db()
    async with get_session_factory()() as db:
        stmt = select(Tenant).order_by(desc(Tenant.created_at))
        if q.strip():
            stmt = stmt.where(Tenant.name.ilike(f"%{q.strip()}%"))
        rows = (await db.execute(stmt.limit(200))).scalars().all()
    return {
        "tenants": [
            {
                "tenantId": str(t.tenant_id),
                "name": t.name,
                "plan": t.plan,
                "status": getattr(t, "status", "active"),
                "createdAt": t.created_at.isoformat() if t.created_at else None,
            }
            for t in rows
        ]
    }


@router.get("/api/dev/admin/tenants/{tenant_id}")
async def tenant_detail(tenant_id: str, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.tenants")
    _require_db()
    tid = uuid.UUID(tenant_id)
    async with get_session_factory()() as db:
        tenant = await db.get(Tenant, tid)
        if tenant is None:
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
    return {
        "tenant": {
            "tenantId": str(tenant.tenant_id),
            "name": tenant.name,
            "status": tenant.status,
            "plan": tenant.plan,
            "limits": tenant.limits or {},
        },
        "agents": [{"agentId": str(a.agent_id), "name": a.name, "status": a.status} for a in agents],
        "numbers": [{"id": str(n.id), "e164": n.e164, "agentId": str(n.agent_id) if n.agent_id else None} for n in numbers],
        "users": [{"userId": str(u.user_id), "email": u.email, "role": m.role} for m, u in mems],
        "recentCalls": [{"callId": str(c.call_id), "startedAt": c.started_at.isoformat()} for c in calls],
    }


@router.patch("/api/dev/admin/tenants/{tenant_id}")
async def patch_tenant(
    tenant_id: str,
    body: TenantPatchBody,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.tenants")
    _require_db()
    tid = uuid.UUID(tenant_id)
    async with get_session_factory()() as db:
        tenant = await db.get(Tenant, tid)
        if tenant is None:
            raise HTTPException(status_code=404, detail="Not found")
        if body.status is not None:
            tenant.status = body.status
        if body.plan is not None:
            tenant.plan = body.plan
        if body.limits is not None:
            tenant.limits = body.limits
        await db.commit()
    await record_admin_action(
        actor=session.subject,
        action="tenant.patch",
        resource_type="tenant",
        resource_id=tenant_id,
        tenant_id=tid,
        payload=body.model_dump(exclude_none=True),
    )
    return {"ok": True}


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
    async with get_session_factory()() as db:
        rows = (
            await db.execute(
                select(PhoneNumber, Tenant, Agent, NumberPurchase)
                .join(Tenant, Tenant.tenant_id == PhoneNumber.tenant_id)
                .outerjoin(Agent, Agent.agent_id == PhoneNumber.agent_id)
                .outerjoin(NumberPurchase, NumberPurchase.id == PhoneNumber.purchase_id)
                .where(PhoneNumber.released_at.is_(None))
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
                "agent": a.name if a else None,
                "agentId": str(pn.agent_id) if pn.agent_id else None,
                "purchaseStatus": np.status if np else None,
                "stripeSubscriptionId": pn.stripe_subscription_id,
                "telnyxNumberId": pn.telnyx_number_id,
                "createdAt": pn.created_at.isoformat() if pn.created_at else None,
            }
            for pn, t, a, np in rows
        ]
    }


@router.post("/api/dev/admin/numbers/allocate")
async def allocate_number(body: AllocateNumberBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.numbers")
    _require_db()
    async with get_session_factory()() as db:
        pn = PhoneNumber(
            tenant_id=uuid.UUID(body.tenantId),
            e164=body.e164.strip(),
            status="active",
            billing_source="manual",
            created_at=datetime.now(timezone.utc),
        )
        db.add(pn)
        await db.commit()
        await db.refresh(pn)
    await record_admin_action(
        actor=session.subject,
        action="number.allocate",
        resource_type="phone_number",
        resource_id=str(pn.id),
        tenant_id=uuid.UUID(body.tenantId),
        payload={"e164": body.e164},
    )
    return {"ok": True, "numberId": str(pn.id)}


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
        if body.agentId is not None:
            pn.agent_id = uuid.UUID(body.agentId) if body.agentId else None
        await db.commit()
    await record_admin_action(
        actor=session.subject,
        action="number.patch",
        resource_type="phone_number",
        resource_id=number_id,
        payload=body.model_dump(exclude_none=True),
    )
    return {"ok": True}


@router.post("/api/dev/admin/numbers/{number_id}/release")
async def release_number(number_id: str, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.numbers")
    _require_db()
    nid = uuid.UUID(number_id)
    async with get_session_factory()() as db:
        pn = await db.get(PhoneNumber, nid)
        if pn is None:
            raise HTTPException(status_code=404, detail="Not found")
        pn.status = "released"
        pn.released_at = datetime.now(timezone.utc)
        pn.inbound_enabled = False
        pn.outbound_enabled = False
        await db.commit()
    await record_admin_action(
        actor=session.subject,
        action="number.release",
        resource_type="phone_number",
        resource_id=number_id,
        tenant_id=pn.tenant_id,
    )
    return {"ok": True}


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
