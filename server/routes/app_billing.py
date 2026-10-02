"""Subscriber billing — wallet, Stripe + Razorpay (INR)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from server.auth.subscriber_dependencies import require_subscriber_jwt
from server.config.env import get_settings
from server.services.saas.billing_wallet_service import (
    list_wallet_transactions,
    wallet_summary,
)
from server.services.saas.razorpay_service import confirm_wallet_payment, create_wallet_order, list_invoices
from server.services.saas.tenant_guard import SubscriberPrincipal, require_subscriber_permission
from server.utils.rate_limiter import RateLimiter, raise_rate_limited

router = APIRouter()
_billing_limiter = RateLimiter(max_requests=30, window_s=300)


class TopupBody(BaseModel):
    amountUsd: float = Field(..., ge=3, le=500)


class RazorpayOrderBody(BaseModel):
    """A top-up in the currency the customer is charged.

    Ignored when International Payments is off, in which case the account only
    accepts INR and the server charges INR regardless of what was asked for.
    """

    amount: float = Field(..., gt=0, le=1_000_000)
    currency: str | None = Field(None, max_length=8)


class RazorpayVerifyBody(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


@router.get("/api/billing/catalog")
async def billing_catalog():
    """Prices the console displays. The server is the only source of truth for these.

    Every price is USD. The INR figures are derived mirrors at the chargeable FX
    rate, exposed for admin reference only — the customer-facing surface quotes USD.
    """
    from server.services.saas.billing_rates import rates_with_derived_inr

    settings = get_settings()
    rates = rates_with_derived_inr()
    return {
        "currency": "USD",
        "plans": [
            {"id": "starter", "name": "Starter", "numbersIncluded": 0},
            {"id": "growth", "name": "Growth", "numbersIncluded": 0},
        ],
        "numberSkus": [
            {
                "country": "IN",
                "currency": "USD",
                "monthlyCents": rates["did_monthly_usd_cents"],
                "monthlyUsd": round(rates["did_monthly_usd_cents"] / 100.0, 2),
                "monthlyInr": round(rates["did_monthly_inr_paise"] / 100.0, 2),
            }
        ],
        "topupMinUsd": settings.topup_min_usd,
        "topupMaxUsd": settings.topup_max_usd,
        "topupMinInr": 100,
        "topupMaxInr": 500000,
        "paymentProvider": "razorpay",
        "rates": {
            "pstnUsdPerMin": round(rates["pstn_rate_usd_cents_per_min"] / 100.0, 3),
            "pstnInrPerMin": round(rates["pstn_rate_inr_paise_per_min"] / 100.0, 2),
            "webInrPerMin": round(rates["web_agent_rate_inr_paise_per_min"] / 100.0, 2),
            "webUsdPerMin": round(rates["web_agent_rate_usd_cents_per_min"] / 100.0, 3),
            "numberMonthlyUsd": round(rates["did_monthly_usd_cents"] / 100.0, 2),
            "numberMonthlyInr": round(rates["did_monthly_inr_paise"] / 100.0, 2),
            "minBalanceUsd": round(settings.pstn_min_balance_usd_cents / 100.0, 2),
            "minBalanceInr": round(settings.pstn_min_balance_inr_paise / 100.0, 2),
            "fxRateInr": rates["fx_rate_inr"],
        },
    }


@router.get("/api/billing/wallet")
async def billing_wallet(principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    require_subscriber_permission(principal, "app.billing.read")
    try:
        return await wallet_summary(principal.tenant_id, user_id=principal.user_id)
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Database required")


@router.post("/api/billing/topup")
async def billing_topup(body: TopupBody, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    """Legacy USD top-up → convert to INR Razorpay order (Stripe removed)."""
    require_subscriber_permission(principal, "app.billing.write")
    allowed, retry = _billing_limiter.allow(f"topup:{principal.user_id}")
    if not allowed:
        raise_rate_limited(retry, "Top-up rate limit reached.")
    from server.services.saas.billing_rates import effective_rates

    # Charge at the admin-configured rate, not the live market rate, so a
    # top-up cannot change price between quote and payment.
    fx = float(effective_rates().get("fx_rate_inr") or 95.64)
    amount_inr = max(100.0, round(float(body.amountUsd) * fx, 2))
    try:
        order = await create_wallet_order(principal.tenant_id, amount_inr)
        return {**order, "convertedFromUsd": body.amountUsd, "fxRateInr": fx}
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": {"code": str(e), "message": str(e)}})


@router.post("/api/billing/razorpay/create-order")
async def razorpay_create_order(
    body: RazorpayOrderBody,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    require_subscriber_permission(principal, "app.billing.write")
    allowed, retry = _billing_limiter.allow(f"rzp:{principal.user_id}")
    if not allowed:
        raise_rate_limited(retry, "Payment rate limit reached.")
    try:
        return await create_wallet_order(
            principal.tenant_id, body.amount, currency=body.currency
        )
    except ValueError as e:
        code = str(e)
        messages = {
            "razorpay_not_configured": "Card payments are temporarily unavailable. Please try again later or contact support.",
            "minimum_amount": "That amount is below the minimum charge.",
            "maximum_amount": "That amount is above the maximum single top-up.",
            "razorpay_auth_failed": (
                "Card payments are temporarily unavailable. Please try again later or contact support."
            ),
            "razorpay_order_failed": "Could not start payment. Please try again in a moment.",
        }
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": code, "message": messages.get(code, code)}},
        ) from None


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
    mine: bool = False,
):
    require_subscriber_permission(principal, "app.billing.read")
    return {
        "transactions": await list_wallet_transactions(
            principal.tenant_id,
            limit=limit,
            user_id=principal.user_id if mine else None,
        )
    }


@router.get("/api/billing/razorpay/config")
async def razorpay_public_config():
    """Public: key id for Checkout, plus which currencies this account accepts.

    Re-reads env so keys added after process start apply without a redeploy.
    `international` must be true before a foreign-issued card will be offered —
    it reflects the operator having enabled it in the Razorpay dashboard, and the
    client uses it to avoid showing a currency the account would reject.
    """
    from server.services.saas.razorpay_service import (
        SUPPORTED_CURRENCIES,
        normalize_currency,
    )
    from server.services.saas.payment_settings import is_international_enabled

    get_settings.cache_clear()
    settings = get_settings()
    key = (settings.razorpay_api_key or "").strip()
    secret = (settings.razorpay_api_secret or "").strip()
    enabled = bool(key and secret)
    # Read the admin's saved choice, not the env default — otherwise turning
    # international on in the panel would be silently ignored by checkout.
    international = enabled and is_international_enabled()
    return {
        "enabled": enabled,
        "keyId": key,
        "international": international,
        # What checkout will actually be created in right now.
        "currency": normalize_currency(None) if enabled else "INR",
        # What the account could accept if the operator turns international on.
        "availableCurrencies": list(SUPPORTED_CURRENCIES) if international else ["INR"],
    }
