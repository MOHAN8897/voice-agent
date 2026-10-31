"""Subscriber concurrent call channels: status, quote, buy/adjust, and usage analytics."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from server.auth.subscriber_dependencies import require_subscriber_jwt
from server.services.saas import concurrency_service as channels
from server.services.saas.tenant_guard import SubscriberPrincipal, require_subscriber_permission
from server.utils.rate_limiter import RateLimiter, raise_rate_limited

router = APIRouter()
_change_limiter = RateLimiter(max_requests=20, window_s=300)


class ChannelQuoteBody(BaseModel):
    model_config = {"extra": "forbid"}

    paidChannels: int = Field(..., ge=0, le=10000)


class ChannelChangeBody(BaseModel):
    model_config = {"extra": "forbid"}

    paidChannels: int = Field(..., ge=0, le=10000)
    #: Client-generated id; retrying the same id never charges twice.
    requestId: str = Field(..., min_length=8, max_length=64)
    #: The charge the tenant saw and confirmed, in paise. A different server
    #: total (price changed meanwhile) is refused with `quote_changed`.
    expectedChargeInrPaise: int | None = Field(default=None, ge=0)


@router.get("/api/billing/channels")
async def get_channels(principal: SubscriberPrincipal = Depends(require_subscriber_jwt), days: int = 30):
    require_subscriber_permission(principal, "app.billing.read")
    return await channels.tenant_overview(principal.tenant_id, days=days)


@router.post("/api/billing/channels/quote")
async def quote_channels(body: ChannelQuoteBody, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    require_subscriber_permission(principal, "app.billing.read")
    return await channels.quote_change(principal.tenant_id, body.paidChannels)


@router.post("/api/billing/channels")
async def change_channels(body: ChannelChangeBody, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    require_subscriber_permission(principal, "app.billing.write")
    allowed, retry = _change_limiter.allow(f"channels:{principal.tenant_id}")
    if not allowed:
        raise_rate_limited(retry)
    return await channels.apply_change(
        principal.tenant_id,
        body.paidChannels,
        request_id=body.requestId,
        expected_charge_inr_paise=body.expectedChargeInrPaise,
        user_id=principal.user_id,
        actor=str(principal.user_id),
    )
