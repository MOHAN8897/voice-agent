"""Subscriber billing — wallet and Razorpay (INR)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from server.auth.subscriber_dependencies import require_subscriber_jwt
from server.config.env import get_settings
from server.services.saas.billing_wallet_service import (
    list_wallet_transactions,
    wallet_summary,
)
from server.services.saas.razorpay_service import (
    confirm_wallet_payment,
    create_wallet_order,
    get_invoice,
    list_invoices,
    quote_wallet_topup,
)
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
    razorpay_order_id: str = Field(..., min_length=4, max_length=128)
    razorpay_payment_id: str = Field(..., min_length=4, max_length=128)
    razorpay_signature: str = Field(..., min_length=16, max_length=256)


class QuoteBody(BaseModel):
    amount: float = Field(..., gt=0, le=1_000_000)
    currency: str | None = Field(None, max_length=8)


class BillingProfileBody(BaseModel):
    model_config = {"extra": "forbid"}

    legalName: str = Field("", max_length=255)
    gstin: str | None = Field(None, max_length=15)
    billingEmail: str = Field("", max_length=320)
    addressLine1: str = Field("", max_length=255)
    addressLine2: str = Field("", max_length=255)
    city: str = Field("", max_length=120)
    stateCode: str = Field("", max_length=4)
    stateName: str = Field("", max_length=120)
    postalCode: str = Field("", max_length=12)
    countryCode: str = Field("IN", max_length=2)
    customerType: str = Field("individual", max_length=20)


def _topup_message(code: str) -> str:
    return {
        "razorpay_not_configured": "Card payments are temporarily unavailable. Please try again later or contact support.",
        "minimum_amount": "That amount is below the minimum charge.",
        "maximum_amount": "That amount is above the maximum single top-up.",
        "razorpay_auth_failed": "Card payments are temporarily unavailable. Please try again later or contact support.",
        "razorpay_order_failed": "Could not start payment. Please try again in a moment.",
    }.get(code, code)


async def _public_tax_summary() -> dict:
    from server.services.saas.tax_service import config_configured, load_config

    config = await load_config()
    return {
        "enabled": bool(config.get("enabled")) and config_configured(config),
        "ratePercent": round(int(config.get("defaultRateBps") or 0) / 100.0, 2),
        "priceIncludesTax": bool(config.get("priceIncludesTax")),
        "countryCode": config.get("countryCode") or "IN",
    }


@router.get("/api/billing/catalog")
async def billing_catalog():
    """Prices the console displays. The server is the only source of truth for these.

    USD and INR values come from the same versioned price configuration. The
    configured INR rate is preserved when it was entered directly in rupees.
    """
    from server.services.saas.billing_rates import load_current_rates

    settings = get_settings()
    rates = await load_current_rates()
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
            "pstnUsdPerMin": round(rates["pstn_rate_usd_micros_per_min"] / 1_000_000.0, 6),
            "pstnInrPerMin": round(rates["pstn_rate_inr_paise_per_min"] / 100.0, 2),
            "webInrPerMin": round(rates["web_agent_rate_inr_paise_per_min"] / 100.0, 2),
            "webUsdPerMin": round(rates["web_agent_rate_usd_micros_per_min"] / 1_000_000.0, 6),
            "numberMonthlyUsd": round(rates["did_monthly_usd_micros"] / 1_000_000.0, 6),
            "numberMonthlyInr": round(rates["did_monthly_inr_paise"] / 100.0, 2),
            "minBalanceUsd": round(settings.pstn_min_balance_usd_cents / 100.0, 2),
            "minBalanceInr": round(settings.pstn_min_balance_inr_paise / 100.0, 2),
            "fxRateInr": rates["fx_rate_inr"],
        },
        # GST applies to INR supplies to Indian recipients. The exact split is
        # quoted per account in POST /api/billing/quote.
        "tax": await _public_tax_summary(),
    }


@router.post("/api/billing/quote")
async def billing_quote(
    body: QuoteBody,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    """Price a top-up with its GST split before checkout opens."""
    require_subscriber_permission(principal, "app.billing.read")
    allowed, retry = _billing_limiter.allow(f"quote:{principal.user_id}")
    if not allowed:
        raise_rate_limited(retry, "Quote rate limit reached.")
    try:
        priced = await quote_wallet_topup(
            principal.tenant_id,
            body.amount,
            currency=body.currency,
            buyer_email=principal.email,
        )
    except ValueError as e:
        code = str(e)
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": code, "message": _topup_message(code)}},
        ) from None
    quote = priced["quote"]
    return {
        **quote,
        "minAmount": priced["floor"],
        "maxAmount": priced["ceiling"],
        "fxRateInr": priced["fxRateInr"],
        "buyer": priced["buyer"],
        "paymentProvider": "razorpay",
    }


@router.get("/api/billing/wallet")
async def billing_wallet(principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    require_subscriber_permission(principal, "app.billing.read")
    try:
        return await wallet_summary(principal.tenant_id, user_id=principal.user_id)
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Database required")


@router.get("/api/billing/last-session")
async def billing_last_session(principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    """Return the latest call and its actual tenant wallet charge."""
    require_subscriber_permission(principal, "app.billing.read")
    from server.db.connection import get_session_factory
    from server.db.models.entities import Call
    from server.db.models.saas_models import BillingWallet, BillingWalletTransaction
    from server.services.saas.billing_wallet_service import wallet_debit_display
    from sqlalchemy import select

    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database required")

    async with factory() as session:
        result = await session.execute(
            select(Call)
            .where(Call.tenant_id == principal.tenant_id)
            .order_by(Call.started_at.desc())
            .limit(1)
        )
        c = result.scalars().first()
        if not c:
            return {"has_call": False, "message": "No calls found for this workspace."}

        cid = str(c.call_id)
        tx_res = await session.execute(
            select(BillingWalletTransaction).where(
                BillingWalletTransaction.tenant_id == principal.tenant_id,
                BillingWalletTransaction.reference_id == f"call:{cid}"
            )
        )
        tx = tx_res.scalars().first()
        wallet = await session.get(BillingWallet, principal.tenant_id)

        dur_sec = float(c.duration_sec or 0)
        dur_min = dur_sec / 60.0 if dur_sec > 0 else 0.0
        charge = (
            wallet_debit_display(
                amount_cents=tx.amount_cents,
                amount_inr_paise=tx.amount_inr_paise,
                wallet_currency=getattr(wallet, "currency", "usd"),
                fx_rate_inr=getattr(c, "applied_fx_rate_inr", None) or get_settings().fx_rate_inr,
            )
            if tx
            else {"amount": None, "currency": None}
        )

        return {
            "has_call": True,
            "call_id": cid,
            "channel": c.channel,
            "direction": c.direction,
            "started_at": c.started_at.isoformat() if c.started_at else None,
            "ended_at": c.ended_at.isoformat() if c.ended_at else None,
            "duration_sec": dur_sec,
            "duration_minutes": round(dur_min, 2),
            "duration_formatted": f"{int(dur_sec // 60)}m {int(dur_sec % 60)}s",
            "tenant_wallet_deduction": {
                "amount": round(charge["amount"], 2) if charge["amount"] is not None else None,
                "currency": charge["currency"],
            },
        }


@router.post("/api/billing/topup")
async def billing_topup(body: TopupBody, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    """Legacy USD top-up → convert to INR Razorpay order (Stripe removed)."""
    require_subscriber_permission(principal, "app.billing.write")
    allowed, retry = _billing_limiter.allow(f"topup:{principal.user_id}")
    if not allowed:
        raise_rate_limited(retry, "Top-up rate limit reached.")
    from server.services.saas.billing_rates import load_current_rates

    # Charge at the admin-configured rate, not the live market rate, so a
    # top-up cannot change price between quote and payment.
    rates = await load_current_rates()
    fx = float(rates.get("fx_rate_inr") or 0)
    if fx <= 0:
        raise HTTPException(status_code=503, detail={"error": {"code": "fx_unavailable", "message": "A positive INR per USD rate is required for top-ups."}})
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
            principal.tenant_id,
            body.amount,
            currency=body.currency,
            buyer_email=principal.email,
        )
    except ValueError as e:
        code = str(e)
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": code, "message": _topup_message(code)}},
        ) from None


@router.post("/api/billing/razorpay/verify")
async def razorpay_verify(body: RazorpayVerifyBody, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    require_subscriber_permission(principal, "app.billing.write")
    allowed, retry = _billing_limiter.allow(f"rzp_verify:{principal.user_id}")
    if not allowed:
        raise_rate_limited(retry, "Payment verification rate limit reached.")
    try:
        return await confirm_wallet_payment(
            principal.tenant_id,
            body.razorpay_order_id,
            body.razorpay_payment_id,
            body.razorpay_signature,
        )
    except RuntimeError:
        raise HTTPException(status_code=503, detail={"error": {"code": "database_unavailable", "message": "Database required"}})
    except ValueError as e:
        code = str(e)
        status_code = 400
        if code == "order_not_found":
            status_code = 404
        elif code == "payment_verification_unavailable":
            status_code = 503
        elif code in ("payment_not_captured", "payment_amount_mismatch", "payment_currency_mismatch"):
            status_code = 409
        messages = {
            "payment_verification_unavailable": "Payment status could not be confirmed. Please retry.",
            "payment_not_captured": "The bank has not captured this payment yet. It will be credited automatically once it is.",
            "invalid_signature": "This payment could not be verified. Please contact support if money was deducted.",
        }
        raise HTTPException(
            status_code=status_code,
            detail={"error": {"code": code, "message": messages.get(code, code)}},
        )


@router.get("/api/billing/invoices")
async def billing_invoices(principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    require_subscriber_permission(principal, "app.billing.read")
    return {"invoices": await list_invoices(principal.tenant_id)}


@router.get("/api/billing/invoices/{invoice_id}")
async def billing_invoice_detail(
    invoice_id: uuid.UUID, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)
):
    require_subscriber_permission(principal, "app.billing.read")
    from server.services.saas.invoice_service import invoice_payload

    invoice, notes = await get_invoice(principal.tenant_id, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="invoice_not_found")
    return invoice_payload(invoice, credit_notes=notes)


@router.get("/api/billing/invoices/{invoice_id}/pdf")
async def billing_invoice_pdf(
    invoice_id: uuid.UUID, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)
):
    require_subscriber_permission(principal, "app.billing.read")
    allowed, retry = _billing_limiter.allow(f"invoice_pdf:{principal.user_id}")
    if not allowed:
        raise_rate_limited(retry, "Invoice download rate limit reached.")
    from server.services.saas.invoice_service import render_invoice_pdf

    invoice, notes = await get_invoice(principal.tenant_id, invoice_id)
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


@router.get("/api/billing/profile")
async def billing_profile(principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    require_subscriber_permission(principal, "app.billing.read")
    from server.services.saas.billing_profile_service import get_profile
    from server.services.saas.tax_service import INDIAN_STATES

    profile = await get_profile(principal.tenant_id)
    # The console renders a state picker from the same table the tax engine
    # validates against, so the two can never drift on GST state codes.
    return {
        **profile,
        "stateOptions": [{"code": code, "name": name} for code, name in INDIAN_STATES.items()],
    }


@router.put("/api/billing/profile")
async def update_billing_profile(
    body: BillingProfileBody, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)
):
    require_subscriber_permission(principal, "app.billing.write")
    from server.services.saas.billing_profile_service import update_profile

    try:
        return await update_profile(principal.tenant_id, body.model_dump())
    except ValueError as exc:
        code = str(exc)
        messages = {
            "gstin_invalid_format": "That GSTIN is not in the 15-character GST format.",
            "gstin_invalid_state": "That GSTIN does not start with a valid state code.",
            "gstin_invalid_checksum": "That GSTIN's check digit is invalid. Please re-check it.",
            "gstin_state_mismatch": "The GSTIN state does not match the billing address state.",
            "invalid_state_code": "Choose a valid Indian state.",
            "legal_name_required": "A business invoice needs the registered legal name.",
            "invalid_customer_type": "Choose individual or business.",
        }
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": code, "message": messages.get(code, code)}},
        ) from None


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

    Only the publishable key id is returned; the secret never leaves the server.
    `international` must be true before a foreign-issued card will be offered —
    it reflects the operator having enabled it in the Razorpay dashboard, and the
    client uses it to avoid showing a currency the account would reject.
    """
    from server.services.saas.razorpay_service import (
        SUPPORTED_CURRENCIES,
        normalize_currency,
    )
    from server.services.saas.payment_settings import is_international_enabled

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
