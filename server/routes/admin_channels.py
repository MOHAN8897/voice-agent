"""Platform admin: concurrent call channel price and Vobiz capacity."""
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
