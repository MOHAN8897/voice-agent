"""Subscriber platform-admin API — allowlist is re-checked from env every request."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from server.auth.subscriber_dependencies import require_subscriber_jwt
from server.db.connection import get_session_factory
from server.db.models.entities import Tenant
from server.db.models.phase5_models import PhoneNumber
from server.db.models.saas_models import BillingWallet, NumberPurchase, User
from server.services.saas.billing_wallet_service import credit_wallet, wallet_summary
from server.services.saas.platform_admins import require_platform_admin_email
from server.services.saas.tenant_guard import SubscriberPrincipal

router = APIRouter()


def _require_admin(principal: SubscriberPrincipal) -> None:
    require_platform_admin_email(principal.email)


class CreditBody(BaseModel):
    tenantId: str
    amountInrPaise: int = Field(..., ge=1, le=50_000_000)
    reason: str = Field("admin_grant", max_length=80)


@router.get("/api/admin/overview")
async def admin_overview(principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    _require_admin(principal)
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail={"error": {"code": "db_unavailable", "message": "Database required"}})
    async with factory() as session:
        tenants = int((await session.execute(select(func.count()).select_from(Tenant))).scalar_one() or 0)
        users = int((await session.execute(select(func.count()).select_from(User))).scalar_one() or 0)
        numbers = int(
            (
                await session.execute(
                    select(func.count()).select_from(PhoneNumber).where(PhoneNumber.released_at.is_(None))
                )
            ).scalar_one()
            or 0
        )
        failed = int(
            (
                await session.execute(
                    select(func.count()).select_from(NumberPurchase).where(NumberPurchase.status == "failed")
                )
            ).scalar_one()
            or 0
        )
    wallet = await wallet_summary(principal.tenant_id)
    return {
        "tenants": tenants,
        "users": users,
        "activeNumbers": numbers,
        "failedPurchases": failed,
        "adminWallet": wallet,
        "adminEmail": principal.email,
    }


@router.get("/api/admin/tenants")
async def admin_tenants(principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    _require_admin(principal)
    factory = get_session_factory()
    if factory is None:
        return {"tenants": []}
    async with factory() as session:
        rows = (await session.execute(select(Tenant).order_by(Tenant.created_at.desc()).limit(100))).scalars()
        wallets = {
            w.tenant_id: w
            for w in (await session.execute(select(BillingWallet))).scalars()
        }
        out = []
        for t in rows:
            w = wallets.get(t.tenant_id)
            out.append(
                {
                    "tenantId": str(t.tenant_id),
                    "name": t.name,
                    "plan": t.plan,
                    "status": t.status,
                    "balanceInrPaise": int(getattr(w, "balance_inr_paise", 0) or 0) if w else 0,
                    "balanceCents": int(w.balance_cents) if w else 0,
                }
            )
        return {"tenants": out}


@router.post("/api/admin/credits")
async def admin_credits(body: CreditBody, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    _require_admin(principal)
    try:
        tenant_id = uuid.UUID(body.tenantId)
    except ValueError:
        raise HTTPException(status_code=400, detail={"error": {"code": "invalid_tenant", "message": "Invalid tenant"}})
    await credit_wallet(
        tenant_id,
        amount_inr_paise=body.amountInrPaise,
        kind="admin_grant",
        reference_id=f"admin_grant:{tenant_id}:{uuid.uuid4()}",
        user_id=principal.user_id,
    )
    return {"ok": True, "wallet": await wallet_summary(tenant_id)}
