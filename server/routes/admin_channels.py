"""Platform admin: concurrent call channel price, Vobiz capacity, and buying Vobiz bundles."""
from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from server.auth.dependencies import require_dev_session, require_permission
from server.auth.session import SessionData
from server.services.saas import concurrency_service as channels
from server.services.saas.admin_audit import record_admin_action

router = APIRouter()


class ChannelPricingBody(BaseModel):
    model_config = {"extra": "forbid"}

    #: INR per channel per 30 days. 0 means channels are free (nothing is debited).
    priceInrPerChannel: Decimal = Field(..., ge=0, le=Decimal("1000000"))
    #: Concurrent calls the platform has bought from Vobiz.
    platformCapacity: int = Field(..., ge=1, le=100000)
    #: Channels every workspace gets without paying.
    includedChannels: int = Field(..., ge=0, le=100000)
    graceDays: int = Field(3, ge=0, le=30)
    maxChannelsPerTenant: int = Field(0, ge=0, le=100000)
    #: Held channels each phone number brings (Vobiz sells none with a DID).
    channelsPerNumber: int | None = Field(None, ge=0, le=100)
    #: New outbound calls per second across all tenants (0 = server default).
    platformCps: int | None = Field(None, ge=0, le=1000)
    #: Vobiz concurrency block size, used to round the purchase estimate.
    concurrencyBlockSize: int | None = Field(None, ge=1, le=10000)
    reason: str = Field(..., min_length=8, max_length=500)


@router.get("/api/dev/admin/billing/channels")
async def get_channel_pricing(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.billing")
    return await channels.platform_overview()


@router.put("/api/dev/admin/billing/channels")
async def put_channel_pricing(body: ChannelPricingBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.billing")
    try:
        config = await channels.save_pricing(
            actor=session.subject,
            reason=body.reason,
            price_inr_per_channel=body.priceInrPerChannel,
            platform_capacity=body.platformCapacity,
            included_channels=body.includedChannels,
            grace_days=body.graceDays,
            max_channels_per_tenant=body.maxChannelsPerTenant,
            channels_per_number=body.channelsPerNumber,
            platform_cps=body.platformCps,
            concurrency_block_size=body.concurrencyBlockSize,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await record_admin_action(
        actor=session.subject,
        action="billing.channels",
        resource_type="platform",
        resource_id="channels",
        payload=body.model_dump(mode="json"),
    )
    return {"ok": True, "pricing": channels.public_pricing(config)}


@router.get("/api/dev/admin/tenants/{tenant_id}/channels")
async def get_tenant_channels(tenant_id: str, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.billing")
    try:
        tid = uuid.UUID(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Tenant not found") from exc
    return await channels.tenant_overview(tid)


# ---------------------------------------------------------------------------
# Call capacity page
# ---------------------------------------------------------------------------


class CapacityPreviewBody(BaseModel):
    model_config = {"extra": "forbid"}

    resourceType: str = Field(..., pattern="^(concurrent_calls|cps)$")
    quantity: int = Field(..., ge=1, le=10000)


class CapacityPurchaseBody(CapacityPreviewBody):
    #: The Vobiz monthly price the admin saw and confirmed (decimal string).
    expectedMonthlyCost: str = Field(..., min_length=1, max_length=32)
    #: One click buys once: a retry with the same id returns the first result.
    requestId: str = Field(..., min_length=8, max_length=64)
    #: The admin types the quantity again, so a mis-click cannot spend money.
    confirmQuantity: int = Field(..., ge=1, le=10000)
    reason: str = Field(..., min_length=8, max_length=500)


class ResolveBody(BaseModel):
    model_config = {"extra": "forbid"}

    outcome: str = Field(..., pattern="^(succeeded|failed)$")


class SyncBody(BaseModel):
    model_config = {"extra": "forbid"}

    reason: str = Field(..., min_length=8, max_length=500)


@router.get("/api/dev/admin/capacity")
async def get_capacity(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.billing")
    from server.services.saas import capacity_planner

    return await capacity_planner.overview()


@router.post("/api/dev/admin/capacity/preview")
async def preview_capacity(body: CapacityPreviewBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.billing")
    from server.services.saas import capacity_planner

    return await capacity_planner.preview(body.resourceType, body.quantity)


@router.post("/api/dev/admin/capacity/purchase")
async def purchase_capacity(body: CapacityPurchaseBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.billing")
    from server.services.saas import capacity_planner

    if body.confirmQuantity != body.quantity:
        raise HTTPException(422, detail={"error": {"code": "confirm_mismatch",
                                                   "message": "Type the same quantity to confirm. Nothing was bought."}})
    result = await capacity_planner.purchase(
        resource_type=body.resourceType, quantity=body.quantity, request_id=body.requestId,
        expected_monthly_cost=body.expectedMonthlyCost, actor=session.subject, reason=body.reason.strip(),
    )
    await record_admin_action(
        actor=session.subject, action="capacity.vobiz_purchase", resource_type="platform", resource_id="vobiz_capacity",
        payload={"resourceType": body.resourceType, "quantity": body.quantity,
                 "expectedMonthlyCost": body.expectedMonthlyCost, "status": result["purchase"]["status"],
                 "reason": body.reason.strip()},
    )
    return result


@router.post("/api/dev/admin/capacity/purchases/{purchase_id}/resolve")
async def resolve_capacity_purchase(purchase_id: str, body: ResolveBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.billing")
    from server.services.saas import capacity_planner

    try:
        pid = uuid.UUID(purchase_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Purchase not found") from exc
    result = await capacity_planner.resolve_unknown(pid, outcome=body.outcome, actor=session.subject)
    await record_admin_action(actor=session.subject, action="capacity.vobiz_purchase_resolved", resource_type="platform",
                              resource_id=str(pid), payload={"outcome": body.outcome})
    return result


@router.post("/api/dev/admin/capacity/sync")
async def sync_capacity(body: SyncBody, session: SessionData = Depends(require_dev_session)):
    """Set the platform capacity and CPS to what the Vobiz account allows now."""
    require_permission(session, "dev.admin.billing")
    from server.services.saas import capacity_planner

    try:
        result = await capacity_planner.apply_vobiz_limits(actor=session.subject, reason=body.reason.strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await record_admin_action(actor=session.subject, action="capacity.vobiz_sync", resource_type="platform",
                              resource_id="vobiz_capacity", payload={**result, "reason": body.reason.strip()})
    return result


# ---------------------------------------------------------------------------
# Number approval mode and queue
# ---------------------------------------------------------------------------


class CapacityPolicyBody(BaseModel):
    model_config = {"extra": "forbid"}

    #: auto: numbers get their channel at once (or auto-buy, or queue); manual: every purchase waits for an admin.
    approvalMode: str = Field(..., pattern="^(auto|manual)$")
    #: Buy a Vobiz concurrency block automatically when a number needs a channel and none is free.
    autoBuy: bool = False
    #: Most the platform may spend automatically on Vobiz bundles in 30 days (INR, monthly cost).
    autoBuyMonthlyBudgetInr: Decimal = Field(Decimal("0"), ge=0, le=Decimal("10000000"))
    reason: str = Field(..., min_length=8, max_length=500)


class RejectBody(BaseModel):
    model_config = {"extra": "forbid"}

    reason: str = Field(..., min_length=8, max_length=500)


@router.put("/api/dev/admin/capacity/policy")
async def put_capacity_policy(body: CapacityPolicyBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.billing")
    from server.services.saas import capacity_policy

    try:
        policy = await capacity_policy.save_policy(
            approval_mode=body.approvalMode, auto_buy=body.autoBuy,
            auto_buy_monthly_budget_inr=body.autoBuyMonthlyBudgetInr, actor=session.subject, reason=body.reason)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await record_admin_action(actor=session.subject, action="capacity.policy", resource_type="platform",
                              resource_id="capacity_policy", payload=body.model_dump(mode="json"))
    return {"ok": True, "policy": policy}


@router.post("/api/dev/admin/capacity/approvals/{purchase_id}/approve")
async def approve_number_purchase(purchase_id: str, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.billing")
    from server.services.saas import capacity_policy

    try:
        pid = uuid.UUID(purchase_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Purchase not found") from exc
    result = await capacity_policy.approve(pid, actor=session.subject)
    await record_admin_action(actor=session.subject, action="number.purchase.approve", resource_type="number_purchase",
                              resource_id=str(pid), payload={})
    return result


@router.post("/api/dev/admin/capacity/approvals/{purchase_id}/reject")
async def reject_number_purchase(purchase_id: str, body: RejectBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.billing")
    from server.services.saas import capacity_policy

    try:
        pid = uuid.UUID(purchase_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Purchase not found") from exc
    result = await capacity_policy.reject(pid, actor=session.subject, reason=body.reason.strip())
    await record_admin_action(actor=session.subject, action="number.purchase.reject", resource_type="number_purchase",
                              resource_id=str(pid), payload={"reason": body.reason.strip()})
    return result
