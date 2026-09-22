"""Subscriber billing — wallet, Stripe + Razorpay (INR)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from server.auth.subscriber_dependencies import require_subscriber_jwt
from server.config.env import get_settings
from server.services.saas.billing_wallet_service import (
    create_topup_checkout,
    list_wallet_transactions,
    wallet_summary,
)
from server.services.saas.razorpay_service import confirm_wallet_payment, create_wallet_order, list_invoices
from server.services.saas.tenant_guard import SubscriberPrincipal, require_subscriber_permission
from server.utils.rate_limiter import RateLimiter

router = APIRouter()
_billing_limiter = RateLimiter(max_requests=30, window_s=300)


class TopupBody(BaseModel):
    amountUsd: float = Field(..., ge=5, le=500)


class RazorpayOrderBody(BaseModel):
    amountInr: float = Field(..., ge=100, le=500000)


class RazorpayVerifyBody(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


@router.get("/api/billing/catalog")
async def billing_catalog():
    return {
        "plans": [
            {"id": "starter", "name": "Starter", "numbersIncluded": 0},
            {"id": "growth", "name": "Growth", "numbersIncluded": 0},
        ],
        "numberSkus": [{"country": "IN", "currency": "USD", "monthlyCents": 500}],
        "topupMinUsd": 5,
        "topupMaxUsd": 500,
    }


@router.get("/api/billing/wallet")
async def billing_wallet(principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    require_subscriber_permission(principal, "app.billing.read")
    try:
        return await wallet_summary(principal.tenant_id)
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Database required")


@router.post("/api/billing/topup")
async def billing_topup(body: TopupBody, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    require_subscriber_permission(principal, "app.billing.write")
    allowed, retry = _billing_limiter.allow(f"topup:{principal.user_id}")
    if not allowed:
        raise HTTPException(status_code=429, detail={"error": {"code": "rate_limit", "retry_after": retry}})
    try:
        return await create_topup_checkout(principal.tenant_id, body.amountUsd, principal.email)
    except ValueError as e:
        code = str(e)
        status = 503 if code == "stripe_not_configured" else 400
        raise HTTPException(status_code=status, detail={"error": {"code": code, "message": code}})


@router.post("/api/billing/razorpay/create-order")
async def razorpay_create_order(
    body: RazorpayOrderBody,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    require_subscriber_permission(principal, "app.billing.write")
    allowed, retry = _billing_limiter.allow(f"rzp:{principal.user_id}")
    if not allowed:
        raise HTTPException(status_code=429, detail={"error": {"code": "rate_limit", "retry_after": retry}})
    try:
        return await create_wallet_order(principal.tenant_id, body.amountInr)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": {"code": str(e), "message": str(e)}})


@router.post("/api/billing/razorpay/verify")
async def razorpay_verify(body: RazorpayVerifyBody, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    require_subscriber_permission(principal, "app.billing.write")
    try:
        return await confirm_wallet_payment(
            principal.tenant_id,
            body.razorpay_order_id,
            body.razorpay_payment_id,
            body.razorpay_signature,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": {"code": str(e), "message": str(e)}})


@router.get("/api/billing/invoices")
async def billing_invoices(principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    require_subscriber_permission(principal, "app.billing.read")
    return {"invoices": await list_invoices(principal.tenant_id)}


@router.get("/api/billing/transactions")
async def billing_transactions(
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
    limit: int = 50,
):
    require_subscriber_permission(principal, "app.billing.read")
    return {"transactions": await list_wallet_transactions(principal.tenant_id, limit=limit)}


@router.get("/api/billing/razorpay/config")
async def razorpay_public_config():
    settings = get_settings()
    return {
        "enabled": bool(settings.razorpay_api_key and settings.razorpay_api_secret),
        "keyId": settings.razorpay_api_key or "",
        "currency": "INR",
    }
