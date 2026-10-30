"""Razorpay orders, GST-aware crediting, webhooks, refunds and reconciliation.

The wallet is money, so every path that can move it obeys the same rules:

* A credit is only applied from a provider-verified captured payment whose
  order, currency and amount match the local snapshot exactly.
* The credit itself is integer INR paise and idempotent on the payment id, both
  checked in code and enforced by a unique ledger reference.
* GST is quoted and snapshotted at checkout. Payment confirmation never
  recomputes tax from a rate that may have changed in between.

Checkout verification, the webhook, and the reconciliation worker all funnel
into `_credit_order_payment`, so there is exactly one way balance is added.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timedelta, timezone

import razorpay
import requests
import sqlalchemy as sa
from sqlalchemy import func, select

from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.entities import Tenant
from server.db.models.saas_models import (
    BillingInvoice,
    BillingWallet,
    BillingWalletTransaction,
    CreditNote,
    RazorpayOrder,
    RazorpayRefund,
    TenantBillingProfile,
)

logger = logging.getLogger(__name__)

RAZORPAY_CONNECT_TIMEOUT_SECONDS = 3.05
RAZORPAY_READ_TIMEOUT_SECONDS = 8.0
RAZORPAY_CALL_TIMEOUT_SECONDS = 12.0

#: Orders older than this are expired if still unpaid. An expired order can
#: still be credited by a late capture; it just leaves the fast lane.
ORDER_EXPIRY = timedelta(hours=24)
#: Do not call the provider for orders younger than this; checkout is in flight.
RECONCILE_AFTER = timedelta(minutes=10)
#: Banks can confirm a payment days after checkout (UPI/netbanking delays,
#: late authorisation). Expired orders are re-checked on a slow lane this long.
LATE_CAPTURE_WINDOW = timedelta(days=7)
#: How often one expired order is re-checked on the slow lane.
SLOW_LANE_INTERVAL = timedelta(hours=1)
#: Order states that are still waiting for money.
OPEN_ORDER_STATUSES = ("created", "attempted", "failed")
#: States in which the order's money has already been credited once.
SETTLED_ORDER_STATUSES = ("paid", "refunded", "partially_refunded")

#: `last_reconciled_at` (migration 048) is read and written through Core so the
#: round-robin scheduler does not depend on the ORM mapping of the order row.
_ORDERS = sa.table(
    "razorpay_orders",
    sa.column("order_id", sa.String(64)),
    sa.column("status", sa.String(30)),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("expires_at", sa.DateTime(timezone=True)),
    sa.column("last_reconciled_at", sa.DateTime(timezone=True)),
)


class _RazorpayTimeoutSession(requests.Session):
    """Give each synchronous SDK request a bounded connect/read timeout."""

    def request(self, method, url, **kwargs):
        kwargs.setdefault(
            "timeout",
            (RAZORPAY_CONNECT_TIMEOUT_SECONDS, RAZORPAY_READ_TIMEOUT_SECONDS),
        )
        return super().request(method, url, **kwargs)


async def _run_provider_call(method, *args, **kwargs):
    """Run the blocking Razorpay SDK off-loop with an overall deadline."""
    return await asyncio.wait_for(
        asyncio.to_thread(method, *args, **kwargs),
        timeout=RAZORPAY_CALL_TIMEOUT_SECONDS,
    )


#: Currencies Razorpay International Payments accepts, and their subunits.
#: A zero-decimal currency (JPY, KRW) would otherwise be charged 100x too much.
CURRENCY_SUBUNITS: dict[str, int] = {
    "INR": 100,
    "USD": 100,
    "EUR": 100,
    "GBP": 100,
    "SGD": 100,
    "AED": 100,
    "AUD": 100,
    "CAD": 100,
    "JPY": 1,
    "KRW": 1,
}
SUPPORTED_CURRENCIES = tuple(CURRENCY_SUBUNITS)

#: Smallest charge per currency, in major units. Razorpay rejects tiny orders.
MIN_CHARGE: dict[str, float] = {
    "INR": 100.0,
    "USD": 1.0,
    "EUR": 1.0,
    "GBP": 1.0,
    "SGD": 1.0,
    "AED": 5.0,
    "AUD": 1.5,
    "CAD": 1.5,
    "JPY": 100.0,
    "KRW": 1000.0,
}
MAX_CHARGE: dict[str, float] = {
    "INR": 500000.0,
    "USD": 5000.0,
    "EUR": 5000.0,
    "GBP": 4000.0,
    "SGD": 6000.0,
    "AED": 20000.0,
    "AUD": 7500.0,
    "CAD": 6500.0,
    "JPY": 700000.0,
    "KRW": 7000000.0,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _client() -> razorpay.Client:
    settings = get_settings()
    if not settings.razorpay_api_key or not settings.razorpay_api_secret:
        raise ValueError("razorpay_not_configured")
    from server.config.env import razorpay_refused

    if razorpay_refused(settings):
        # Test keys or a reused webhook secret in production: refuse to move
        # money rather than take live payments that can never be verified.
        raise ValueError("razorpay_not_configured")
    return razorpay.Client(
        auth=(settings.razorpay_api_key, settings.razorpay_api_secret),
        session=_RazorpayTimeoutSession(),
    )


def normalize_currency(raw: str | None) -> str:
    """The currency actually charged, honouring the admin's international toggle."""
    from server.services.saas import payment_settings

    if not payment_settings.is_international_enabled():
        # International is off, so INR is the only thing the account will accept.
        return "INR"
    code = (raw or payment_settings.charge_currency() or "INR").strip().upper()
    return code if code in CURRENCY_SUBUNITS else "INR"


def to_minor(amount: float, currency: str) -> int:
    return int(round(float(amount) * CURRENCY_SUBUNITS[currency]))


def from_minor(amount_minor: int, currency: str) -> float:
    return round(int(amount_minor) / CURRENCY_SUBUNITS[currency], 2)


def inr_credit_for(
    currency: str,
    amount_minor: int,
    *,
    fx_rate_inr: float | None = None,
) -> int:
    """INR paise for a pre-tax amount made in `currency`.

    Prefers the charge rate the admin configured over a live quote, so a top-up
    cannot change price between the order and the payment.
    """
    from server.services.saas.billing_rates import effective_rates

    if currency == "INR":
        return int(amount_minor)
    major = from_minor(amount_minor, currency)
    fx = float(fx_rate_inr or effective_rates()["fx_rate_inr"]) or 95.64
    return int(round(major * fx * 100))


def verify_payment_signature(order_id: str, payment_id: str, signature: str) -> bool:
    settings = get_settings()
    secret = settings.razorpay_api_secret or ""
    if not secret or not signature:
        return False
    payload = f"{order_id}|{payment_id}".encode()
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_webhook_signature(raw_body: bytes, signature: str | None) -> bool:
    """Fail closed when no endpoint secret is configured.

    Accepting an unverified webhook would let anyone credit any wallet, so a
    missing secret disables the route rather than downgrading verification.
    """
    secret = (get_settings().razorpay_webhook_secret or "").strip()
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


async def _tenant_buyer(tenant_id: uuid.UUID, buyer_email: str | None = None) -> dict:
    from server.services.saas.tax_service import buyer_snapshot

    factory = get_session_factory()
    profile = None
    tenant = None
    if factory is not None:
        async with factory() as session:
            profile = await session.get(TenantBillingProfile, tenant_id)
            tenant = await session.get(Tenant, tenant_id)
    profile_dict = {}
    if profile is not None:
        profile_dict = {
            "legal_name": profile.legal_name,
            "gstin": profile.gstin,
            "billing_email": profile.billing_email,
            "address_line1": profile.address_line1,
            "address_line2": profile.address_line2,
            "city": profile.city,
            "state_name": profile.state_name,
            "state_code": profile.state_code,
            "postal_code": profile.postal_code,
            "country_code": profile.country_code,
            "customer_type": profile.customer_type,
        }
    return buyer_snapshot(
        profile_dict,
        fallback_name=getattr(tenant, "name", "") if tenant else "",
        fallback_email=buyer_email or "",
    )


async def quote_wallet_topup(
    tenant_id: uuid.UUID,
    amount: float,
    *,
    currency: str | None = None,
    buyer_email: str | None = None,
) -> dict:
    """Price a top-up without touching Razorpay, for the checkout breakdown."""
    from server.services.saas.billing_rates import load_current_rates
    from server.services.saas.tax_service import compute_tax, load_config

    from server.services.saas import payment_settings

    # Settings live in the database and may have been changed on another
    # instance; read them fresh before choosing the charge currency.
    await payment_settings.refresh()
    currency_code = normalize_currency(currency)
    floor = MIN_CHARGE.get(currency_code, 1.0)
    ceiling = MAX_CHARGE.get(currency_code, 5000.0)
    if amount < floor:
        raise ValueError("minimum_amount")
    if amount > ceiling:
        raise ValueError("maximum_amount")

    rates = await load_current_rates()
    tax_config = await load_config(strict=True)
    from server.services.saas.tax_service import config_configured
    if tax_config.get("enabled") and not config_configured(tax_config):
        raise ValueError("tax_configuration_incomplete")
    buyer = await _tenant_buyer(tenant_id, buyer_email)
    quote = compute_tax(
        amount,
        currency_code,
        fx_rate_inr=float(rates["fx_rate_inr"]),
        config=tax_config,
        buyer=buyer,
    )
    min_credit = int(quote["creditInrPaise"])
    return {
        "quote": quote,
        "buyer": buyer,
        "taxConfig": tax_config,
        "currency": currency_code,
        "floor": floor,
        "ceiling": ceiling,
        "fxRateInr": float(rates["fx_rate_inr"]),
        "minCreditInr": min_credit / 100.0,
    }


async def create_wallet_order(
    tenant_id: uuid.UUID,
    amount: float,
    *,
    currency: str | None = None,
    buyer_email: str | None = None,
    expected_total_minor: int | None = None,
) -> dict:
    """Quote a top-up, persist the tax snapshot, then create the provider order.

    `amount` is the listed price. When prices are GST-exclusive the provider
    order is for `amount + GST`; the wallet is credited the taxable value only.
    """
    from server.services.saas.tax_service import config_configured, supplier_snapshot

    priced = await quote_wallet_topup(
        tenant_id, amount, currency=currency, buyer_email=buyer_email
    )
    quote = priced["quote"]
    tax_config = priced["taxConfig"]
    buyer = priced["buyer"]
    currency_code = priced["currency"]
    ceiling = priced["ceiling"]
    minor = int(quote["totalMinor"])
    if expected_total_minor is not None and minor != expected_total_minor:
        raise ValueError("quote_changed")
    if minor <= 0:
        raise ValueError("minimum_amount")
    if from_minor(minor, currency_code) > ceiling:
        raise ValueError("maximum_amount")

    client = _client()
    receipt = f"wallet_{uuid.uuid4().hex[:16]}"
    try:
        order = await _run_provider_call(
            client.order.create,
            {
                "amount": minor,
                "currency": currency_code,
                "payment_capture": 1,
                # Razorpay caps receipt at 40 chars; keep ours short and traceable.
                "receipt": receipt,
                "notes": {
                    "tenant_id": str(tenant_id),
                    "purpose": "wallet_topup",
                    "taxable_minor": str(quote["subtotalMinor"]),
                    "tax_minor": str(quote["taxMinor"]),
                },
            },
        )
    except (
        razorpay.errors.BadRequestError,
        razorpay.errors.GatewayError,
        razorpay.errors.ServerError,
        requests.exceptions.RequestException,
        TimeoutError,
    ) as exc:
        detail = str(exc).lower()
        failure = (
            "razorpay_auth_failed"
            if isinstance(exc, razorpay.errors.BadRequestError)
            and ("authentication" in detail or "auth" in detail)
            else "razorpay_order_failed"
        )
        logger.warning("razorpay order create failed error_type=%s", type(exc).__name__)
        from server.services.saas.activity_log import record_event

        await record_event(
            action="wallet.topup.order_failed",
            resource_type="payment_order",
            resource_id="",
            actor=str(tenant_id),
            tenant_id=tenant_id,
            payload={
                "error": failure,
                "currency": currency_code,
                "amount": from_minor(minor, currency_code),
            },
            source="subscriber",
            outcome="error",
            severity="error",
        )
        raise ValueError(failure) from exc
    order_id = order["id"]

    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    try:
        async with factory() as session:
            session.add(
                RazorpayOrder(
                    order_id=order_id,
                    tenant_id=tenant_id,
                    amount_inr_paise=int(quote["creditInrPaise"]),
                    currency=currency_code,
                    amount_minor=minor,
                    gross_minor=minor,
                    taxable_minor=int(quote["subtotalMinor"]),
                    tax_minor=int(quote["taxMinor"]),
                    tax_rate_bps=int(quote["rateBps"]),
                    tax_kind=str(quote["taxKind"]),
                    place_of_supply=quote["placeOfSupply"] or None,
                    place_of_supply_code=quote["placeOfSupplyCode"] or None,
                    sac_code=quote["sacCode"],
                    buyer_snapshot=buyer,
                    supplier_snapshot=supplier_snapshot(tax_config),
                    status="created",
                    purpose="wallet_topup",
                    expires_at=_utcnow() + ORDER_EXPIRY,
                    created_at=_utcnow(),
                )
            )
            await session.commit()
    except Exception as exc:
        # No local row means no path can credit this order. Returning checkout
        # here would take money we could not attribute, so fail the request.
        logger.error("razorpay order persistence failed error_type=%s", type(exc).__name__)
        raise ValueError("razorpay_order_failed") from None

    from server.services.saas.activity_log import record_event

    await record_event(
        action="wallet.topup.order_created",
        resource_type="payment_order",
        resource_id=order_id,
        actor=str(tenant_id),
        tenant_id=tenant_id,
        payload={
            "currency": currency_code,
            "amount": from_minor(minor, currency_code),
            "taxable": quote["subtotal"],
            "tax": quote["tax"],
            "international": currency_code != "INR",
            "taxKind": quote["taxKind"],
        },
        source="subscriber",
    )

    settings = get_settings()
    return {
        "orderId": order_id,
        "currency": currency_code,
        "amount": quote["total"],
        "amountMinor": minor,
        "subtotal": quote["subtotal"],
        "subtotalMinor": quote["subtotalMinor"],
        "tax": quote["tax"],
        "taxMinor": quote["taxMinor"],
        "taxRatePercent": quote["ratePercent"],
        "taxKind": quote["taxKind"],
        "taxLabel": {
            "cgst_sgst": "CGST + SGST",
            "igst": "IGST",
            "export": "Zero-rated export",
            "none": "Tax",
        }.get(quote["taxKind"], "Tax"),
        "cgst": quote["cgst"],
        "sgst": quote["sgst"],
        "igst": quote["igst"],
        "placeOfSupply": quote["placeOfSupply"],
        "taxConfigured": config_configured(tax_config),
        "priceIncludesTax": quote["priceIncludesTax"],
        # What the wallet will be credited, for transparency before paying.
        "creditedInr": quote["creditInr"],
        "creditedInrPaise": quote["creditInrPaise"],
        "international": currency_code != "INR",
        "keyId": settings.razorpay_api_key,
        "receipt": receipt,
    }


def _fetch_payment(payment_id: str) -> dict | None:
    """Fetch the provider's payment record before any wallet credit is applied."""
    try:
        return _client().payment.fetch(payment_id)
    except (
        razorpay.errors.BadRequestError,
        razorpay.errors.GatewayError,
        razorpay.errors.ServerError,
        requests.exceptions.RequestException,
    ) as exc:
        logger.warning("razorpay payment fetch failed error_type=%s", type(exc).__name__)
        raise ValueError("payment_verification_unavailable") from None


def _validate_payment_details(
    payment: dict,
    *,
    payment_id: str,
    order_id: str,
    currency: str,
    amount_minor: int,
    expected_status: str = "captured",
) -> None:
    """Fail closed unless Razorpay confirms the exact signed payment and order."""
    provider_payment_id = payment.get("id")
    if not provider_payment_id or str(provider_payment_id) != payment_id:
        raise ValueError("payment_id_mismatch")

    provider_order = payment.get("order_id")
    if not provider_order or str(provider_order) != order_id:
        raise ValueError("payment_order_mismatch")

    status = str(payment.get("status") or "").strip().lower()
    if status != expected_status:
        raise ValueError(
            "payment_not_captured" if expected_status == "captured" else "payment_not_authorized"
        )

    provider_currency = str(payment.get("currency") or "").strip().upper()
    if not provider_currency or provider_currency != currency:
        raise ValueError("payment_currency_mismatch")

    provider_amount = payment.get("amount")
    if (
        isinstance(provider_amount, bool)
        or not isinstance(provider_amount, int)
        or amount_minor <= 0
        or provider_amount != amount_minor
    ):
        raise ValueError("payment_amount_mismatch")


async def _existing_invoice(session, *, tenant_id: uuid.UUID | None, order_id: str, payment_id: str | None):
    stmt = select(BillingInvoice).where(BillingInvoice.razorpay_order_id == order_id)
    if tenant_id is not None:
        stmt = stmt.where(BillingInvoice.tenant_id == tenant_id)
    invoice = (await session.execute(stmt)).scalar_one_or_none()
    if invoice is None and payment_id:
        stmt = select(BillingInvoice).where(BillingInvoice.razorpay_payment_id == payment_id)
        if tenant_id is not None:
            stmt = stmt.where(BillingInvoice.tenant_id == tenant_id)
        invoice = (await session.execute(stmt)).scalar_one_or_none()
    return invoice


async def _locked_wallet(session, tenant_id: uuid.UUID) -> BillingWallet:
    """Lock the tenant wallet, creating it if this is its first money movement."""
    wallet = await session.get(BillingWallet, tenant_id, with_for_update=True)
    if wallet is None:
        wallet = BillingWallet(
            tenant_id=tenant_id, balance_cents=0, balance_inr_paise=0, updated_at=_utcnow()
        )
        session.add(wallet)
        await session.flush()
    return wallet


async def _credit_order_payment(order_id: str, payment_id: str, payment: dict, *, source: str) -> dict:
    """The single writer of a top-up credit, used by verify, webhook and recovery."""
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")

    ref_id = f"razorpay:{payment_id}"
    async with factory() as session:
        row = await session.get(RazorpayOrder, order_id, with_for_update=True)
        if row is None:
            raise ValueError("order_not_found")
        tenant_id = row.tenant_id

        currency = getattr(row, "currency", None) or "INR"
        gross_minor = int(getattr(row, "gross_minor", None) or row.amount_minor or 0)
        _validate_payment_details(payment, payment_id=payment_id, order_id=order_id,
            currency=currency, amount_minor=gross_minor)
        existing_tx = (
            await session.execute(
                select(BillingWalletTransaction).where(
                    BillingWalletTransaction.reference_id == ref_id,
                    BillingWalletTransaction.tenant_id == tenant_id
                )
            )
        ).scalar_one_or_none()
        if existing_tx:
            inv = await _existing_invoice(
                session, tenant_id=existing_tx.tenant_id, order_id=order_id, payment_id=payment_id
            )
            return {
                "ok": True,
                "invoiceId": str(inv.invoice_id) if inv else None,
                "invoiceNumber": inv.invoice_number if inv else None,
                "creditedInr": int(existing_tx.amount_inr_paise or 0) / 100.0,
                "duplicate": True,
            }

        # Any settled state, not only "paid": a second captured payment on a
        # refunded order must never be credited again. "expired" is not here on
        # purpose, so a late capture is still credited once.
        if row.status in SETTLED_ORDER_STATUSES:
            inv = await _existing_invoice(
                session, tenant_id=tenant_id, order_id=order_id, payment_id=row.payment_id
            )
            if row.payment_id and payment_id and row.payment_id != payment_id:
                # Two captured payments against one order. Credit stays with the
                # first; the second needs a human refund, never a second credit.
                from server.services.saas.activity_log import record_event

                await record_event(
                    action="wallet.topup.duplicate_payment",
                    resource_type="payment_order",
                    resource_id=order_id,
                    actor=str(tenant_id),
                    tenant_id=tenant_id,
                    payload={
                        "creditedPaymentId": row.payment_id,
                        "extraPaymentId": payment_id,
                        "requiresRefund": True,
                    },
                    source=source,
                    outcome="error",
                    severity="error",
                )
                return {
                    "ok": True,
                    "invoiceId": str(inv.invoice_id) if inv else None,
                    "invoiceNumber": inv.invoice_number if inv else None,
                    "duplicate": True,
                    "requiresRefund": True,
                }
            return {
                "ok": True,
                "invoiceId": str(inv.invoice_id) if inv else None,
                "invoiceNumber": inv.invoice_number if inv else None,
                "duplicate": True,
            }

        base_amount = payment.get("base_amount")
        international = bool(payment.get("international")) or currency != "INR"
        taxable_minor = int(getattr(row, "taxable_minor", None) or 0)
        tax_minor = int(getattr(row, "tax_minor", None) or 0)
        credit_paise = int(row.amount_inr_paise or 0)
        tax_paise = tax_minor if currency == "INR" else 0
        if currency == "INR":
            # International cards can pay INR. Their gross settlement still
            # includes GST; only the snapshotted taxable value is spendable.
            credit_paise = taxable_minor or credit_paise
        elif isinstance(base_amount, int) and not isinstance(base_amount, bool) and base_amount > 0:
            from decimal import ROUND_HALF_UP, Decimal
            taxable_share = Decimal(taxable_minor or gross_minor - tax_minor) / gross_minor
            credit_paise = int((Decimal(base_amount) * taxable_share).quantize(Decimal(1), rounding=ROUND_HALF_UP))
            tax_paise = base_amount - credit_paise
        elif tax_minor:
            # Convert the persisted taxable/tax split using its quoted FX.
            from decimal import ROUND_HALF_UP, Decimal
            tax_paise = int((Decimal(credit_paise) * tax_minor / taxable_minor).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        taxable_paise = credit_paise

        tax_kind = str(getattr(row, "tax_kind", None) or "none")
        if tax_kind == "cgst_sgst":
            from server.services.saas.tax_service import _split_cgst_sgst

            # Same split as the quote, so the invoice matches what was shown.
            cgst, sgst = _split_cgst_sgst(tax_paise, int(getattr(row, "tax_rate_bps", 0) or 0))
            igst = 0
        elif tax_kind == "igst":
            cgst = sgst = 0
            igst = tax_paise
        else:
            cgst = sgst = igst = 0

        prior_status = str(row.status or "")
        wallet = await _locked_wallet(session, tenant_id)
        wallet.balance_inr_paise = int(wallet.balance_inr_paise or 0) + credit_paise
        wallet.currency = "inr"
        wallet.updated_at = _utcnow()

        now = _utcnow()
        row.status = "paid"
        row.payment_id = payment_id
        row.payment_method = payment.get("method")
        row.paid_at = now
        row.base_amount_inr_paise = int(base_amount) if base_amount else None
        fee = payment.get("fee")
        tax_on_fee = payment.get("tax")
        row.fee_minor = int(fee) if isinstance(fee, int) else None
        row.tax_on_fee_minor = int(tax_on_fee) if isinstance(tax_on_fee, int) else None
        row.settlement_id = payment.get("settlement_id") or None
        if payment.get("settled"):
            row.settled_at = now

        from server.services.saas.invoice_service import allocate_number
        from server.services.saas.tax_service import load_config

        tax_config = await load_config()
        prefix = str(tax_config.get("invoicePrefix") or "INV")
        inv_num, fy, sequence = await allocate_number(session, "INV", prefix)

        buyer = getattr(row, "buyer_snapshot", None) or {}
        supplier = getattr(row, "supplier_snapshot", None) or {}
        invoice = BillingInvoice(
            tenant_id=tenant_id,
            invoice_number=inv_num,
            amount_inr_paise=credit_paise,
            taxable_inr_paise=taxable_paise,
            tax_inr_paise=tax_paise,
            cgst_inr_paise=cgst,
            sgst_inr_paise=sgst,
            igst_inr_paise=igst,
            tax_rate_bps=int(getattr(row, "tax_rate_bps", 0) or 0),
            tax_kind=tax_kind,
            currency=currency,
            amount_minor=gross_minor,
            taxable_minor=taxable_minor,
            tax_minor=tax_minor,
            sac_code=getattr(row, "sac_code", None) or supplier.get("sacCode"),
            place_of_supply=getattr(row, "place_of_supply", None),
            place_of_supply_code=getattr(row, "place_of_supply_code", None),
            customer_gstin=buyer.get("gstin") or None,
            supplier_snapshot=supplier,
            buyer_snapshot=buyer,
            fy=fy,
            sequence=sequence,
            status="paid",
            razorpay_order_id=order_id,
            razorpay_payment_id=payment_id,
            payment_method=payment.get("method"),
            paid_at=now,
            line_items=[
                {
                    "description": "Prepaid voice services — wallet top-up",
                    "sacCode": getattr(row, "sac_code", None) or supplier.get("sacCode"),
                    "currency": currency,
                    "taxable": taxable_minor / CURRENCY_SUBUNITS[currency],
                    "tax": tax_minor / CURRENCY_SUBUNITS[currency],
                    "total": gross_minor / CURRENCY_SUBUNITS[currency],
                    "taxKind": tax_kind,
                    "taxRateBps": int(getattr(row, "tax_rate_bps", 0) or 0),
                    "international": international,
                }
            ],
            created_at=now,
        )
        session.add(invoice)
        session.add(
            BillingWalletTransaction(
                tenant_id=tenant_id,
                amount_cents=0,
                amount_inr_paise=credit_paise,
                kind="razorpay_topup_inr" if currency == "INR" else "razorpay_topup",
                reference_id=ref_id,
                created_at=now,
            )
        )
        try:
            await session.commit()
        except Exception as exc:
            from sqlalchemy.exc import IntegrityError

            await session.rollback()
            if isinstance(exc, IntegrityError):
                inv = await _existing_invoice(
                    session, tenant_id=tenant_id, order_id=order_id, payment_id=payment_id
                )
                if inv is not None:
                    return {
                        "ok": True,
                        "invoiceId": str(inv.invoice_id),
                        "invoiceNumber": inv.invoice_number,
                        "duplicate": True,
                    }
            logger.error("wallet credit commit failed error_type=%s", type(exc).__name__)
            raise

        from server.services.saas.activity_log import record_event

        if prior_status == "expired":
            # Money arrived after we gave up on the order. It is credited (the
            # customer paid), but someone should know the expiry window missed it.
            logger.error(
                "razorpay late capture credited on expired order order=%s payment=%s source=%s",
                order_id,
                payment_id,
                source,
            )
            await record_event(
                action="wallet.topup.late_capture",
                resource_type="payment_order",
                resource_id=order_id,
                actor=str(tenant_id),
                tenant_id=tenant_id,
                payload={"paymentId": payment_id, "source": source, "creditedInr": credit_paise / 100.0},
                source="webhook" if source == "webhook" else "system",
                outcome="error",
                severity="error",
            )

        await record_event(
            action="wallet.topup.paid",
            resource_type="invoice",
            resource_id=str(invoice.invoice_id),
            actor=str(tenant_id),
            tenant_id=tenant_id,
            payload={
                "orderId": order_id,
                "paymentId": payment_id,
                "currency": currency,
                "charged": gross_minor / CURRENCY_SUBUNITS[currency],
                "taxable": taxable_minor / CURRENCY_SUBUNITS[currency],
                "tax": tax_minor / CURRENCY_SUBUNITS[currency],
                "creditedInr": credit_paise / 100.0,
                "international": international,
                "taxKind": tax_kind,
                "source": source,
                "duplicate": False,
            },
            source="webhook" if source == "webhook" else source,
        )
        return {
            "ok": True,
            "invoiceId": str(invoice.invoice_id),
            "invoiceNumber": inv_num,
            "currency": currency,
            "charged": gross_minor / CURRENCY_SUBUNITS[currency],
            "subtotal": taxable_minor / CURRENCY_SUBUNITS[currency],
            "tax": tax_minor / CURRENCY_SUBUNITS[currency],
            "creditedInr": credit_paise / 100.0,
            "international": international,
            "taxKind": tax_kind,
            "balanceInr": wallet.balance_inr_paise / 100.0,
            "duplicate": False,
        }


async def credit_provider_payment(payment: dict, *, source: str) -> dict:
    """Credit from a provider payment entity (webhook / reconciliation)."""
    payment_id = str(payment.get("id") or "")
    order_id = str(payment.get("order_id") or "")
    if not payment_id or not order_id:
        raise ValueError("payment_order_mismatch")
    return await _credit_order_payment(order_id, payment_id, payment, source=source)


async def capture_authorized_payment(payment: dict, *, source: str) -> dict:
    """Capture an authorised-but-uncaptured payment, then credit it normally.

    Orders are created with auto-capture, but Razorpay leaves a payment in
    `authorized` when auto-capture times out (late bank confirmation). Unless it
    is captured it is refunded to the customer after a few days and the wallet
    is never credited, so the webhook and reconciliation capture it for the
    exact amount and currency snapshotted on the order.
    """
    payment_id = str(payment.get("id") or "")
    order_id = str(payment.get("order_id") or "")
    if not payment_id or not order_id:
        raise ValueError("payment_order_mismatch")
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    async with factory() as session:
        row = await session.get(RazorpayOrder, order_id)
        if row is None:
            raise ValueError("order_not_found")
        tenant_id = row.tenant_id
        status = str(row.status or "")
        current_payment = row.payment_id
        currency = getattr(row, "currency", None) or "INR"
        gross_minor = int(getattr(row, "gross_minor", None) or row.amount_minor or 0)

    if status in SETTLED_ORDER_STATUSES and current_payment and current_payment != payment_id:
        # The order was already paid by another payment. Capturing this one
        # would charge the customer twice; an uncaptured authorisation is
        # released automatically, so leave it alone and tell an operator.
        from server.services.saas.activity_log import record_event

        await record_event(
            action="wallet.topup.duplicate_authorization",
            resource_type="payment_order",
            resource_id=order_id,
            actor=str(tenant_id),
            tenant_id=tenant_id,
            payload={"creditedPaymentId": current_payment, "authorizedPaymentId": payment_id},
            source="webhook" if source == "webhook" else "system",
            outcome="error",
            severity="warning",
        )
        return {"ok": True, "captured": False, "skipped": "order_already_settled"}

    # Re-read the payment: Razorpay's own auto-capture may already have run.
    fresh = await _run_provider_call(_fetch_payment, payment_id)
    if not isinstance(fresh, dict) or not fresh:
        raise ValueError("payment_verification_unavailable")
    fresh_status = str(fresh.get("status") or "").strip().lower()
    if fresh_status == "captured":
        return await credit_provider_payment(fresh, source=source)
    if fresh_status != "authorized":
        # failed / refunded: nothing to capture and nothing to credit.
        return {"ok": True, "captured": False, "providerStatus": fresh_status}

    _validate_payment_details(
        fresh,
        payment_id=payment_id,
        order_id=order_id,
        currency=currency,
        amount_minor=gross_minor,
        expected_status="authorized",
    )
    try:
        captured = await _run_provider_call(
            _client().payment.capture, payment_id, gross_minor, {"currency": currency}
        )
    except razorpay.errors.BadRequestError:
        # Usually "already captured" when auto-capture raced us. Ask again.
        captured = await _run_provider_call(_fetch_payment, payment_id)
    except (
        razorpay.errors.GatewayError,
        razorpay.errors.ServerError,
        requests.exceptions.RequestException,
        TimeoutError,
    ) as exc:
        logger.warning("razorpay capture failed error_type=%s", type(exc).__name__)
        raise ValueError("payment_capture_unavailable") from None
    if not isinstance(captured, dict) or str(captured.get("status") or "").lower() != "captured":
        raise ValueError("payment_capture_unavailable")
    logger.info("razorpay authorized payment captured order=%s payment=%s source=%s", order_id, payment_id, source)
    return await credit_provider_payment(captured, source=source)


async def confirm_wallet_payment(
    tenant_id: uuid.UUID,
    order_id: str,
    payment_id: str,
    signature: str,
) -> dict:
    if not verify_payment_signature(order_id, payment_id, signature):
        raise ValueError("invalid_signature")
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")

    # Check tenant ownership before asking Razorpay about a caller-supplied ID.
    async with factory() as session:
        row = await session.get(RazorpayOrder, order_id)
        if row is None or row.tenant_id != tenant_id:
            raise ValueError("order_not_found")
        if row.status == "paid":
            inv = await _existing_invoice(
                session, tenant_id=tenant_id, order_id=order_id, payment_id=row.payment_id
            )
            return {
                "ok": True,
                "invoiceId": str(inv.invoice_id) if inv else None,
                "invoiceNumber": inv.invoice_number if inv else None,
                "duplicate": True,
            }

    try:
        payment = await _run_provider_call(_fetch_payment, payment_id)
    except TimeoutError:
        logger.warning("razorpay payment fetch timed out")
        # A signed checkout callback is not enough to credit the wallet when we
        # cannot confirm capture. The client retries with the same IDs.
        raise ValueError("payment_verification_unavailable") from None
    if not isinstance(payment, dict) or not payment:
        logger.warning("razorpay payment fetch returned no details")
        raise ValueError("payment_verification_unavailable")

    if (
        str(payment.get("status") or "").strip().lower() == "authorized"
        and str(payment.get("id") or "") == payment_id
        and str(payment.get("order_id") or "") == order_id
    ):
        # Signed by checkout but auto-capture has not run: capture it now
        # rather than telling a customer who has paid to wait.
        result = await capture_authorized_payment(payment, source="checkout")
        if result.get("captured") is False:
            raise ValueError("payment_not_captured")
        return result

    return await _credit_order_payment(order_id, payment_id, payment, source="checkout")


async def mark_order_failed(payment: dict, *, source: str = "webhook") -> None:
    """Record a failed attempt without touching the wallet.

    A failed payment is not terminal: the customer can retry the same order or a
    new one, so the row stays reconcilable until it expires.
    """
    order_id = str(payment.get("order_id") or "")
    payment_id = str(payment.get("id") or "")
    if not order_id:
        return
    factory = get_session_factory()
    if factory is None:
        return
    error = payment.get("error") if isinstance(payment.get("error"), dict) else {}
    code = str(error.get("code") or payment.get("status") or "payment_failed")[:80]
    reason = str(error.get("description") or error.get("reason") or "")[:1000] or None

    async with factory() as session:
        row = await session.get(RazorpayOrder, order_id, with_for_update=True)
        # "expired" stays expired: flipping it back to failed would take it out
        # of both reconciliation lanes and hide a late capture.
        if row is None or row.status in (*SETTLED_ORDER_STATUSES, "expired"):
            return
        row.status = "failed"
        row.failure_code = code
        row.failure_reason = reason
        if payment_id and not row.payment_id:
            row.payment_id = payment_id
        await session.commit()
        tenant_id = row.tenant_id

    from server.services.saas.activity_log import record_event

    await record_event(
        action="wallet.topup.failed",
        resource_type="payment_order",
        resource_id=order_id,
        actor=str(tenant_id),
        tenant_id=tenant_id,
        payload={"paymentId": payment_id, "code": code, "reason": reason},
        source=source,
        outcome="error",
        severity="warning",
    )


async def list_invoices(tenant_id: uuid.UUID, limit: int = 50) -> list[dict]:
    factory = get_session_factory()
    if factory is None:
        return []
    from server.services.saas.invoice_service import invoice_payload

    async with factory() as session:
        result = await session.execute(
            select(BillingInvoice)
            .where(BillingInvoice.tenant_id == tenant_id)
            .order_by(BillingInvoice.created_at.desc())
            .limit(max(1, min(limit, 200)))
        )
        return [invoice_payload(r) for r in result.scalars()]


async def get_invoice(
    tenant_id: uuid.UUID | None, invoice_id: uuid.UUID
) -> tuple[BillingInvoice | None, list[CreditNote]]:
    factory = get_session_factory()
    if factory is None:
        return None, []
    async with factory() as session:
        invoice = await session.get(BillingInvoice, invoice_id)
        if invoice is None:
            return None, []
        if tenant_id is not None and invoice.tenant_id != tenant_id:
            return None, []
        notes = list(
            (
                await session.execute(
                    select(CreditNote)
                    .where(CreditNote.invoice_id == invoice_id)
                    .order_by(CreditNote.created_at.asc())
                )
            ).scalars()
        )
        return invoice, notes


async def get_invoice_by_number(invoice_number: str) -> BillingInvoice | None:
    factory = get_session_factory()
    if factory is None:
        return None
    async with factory() as session:
        return (
            await session.execute(
                select(BillingInvoice).where(BillingInvoice.invoice_number == invoice_number)
            )
        ).scalar_one_or_none()


async def _allocate_credit_note(session, prefix: str) -> tuple[str, str, int]:
    from server.services.saas.invoice_service import allocate_number

    return await allocate_number(session, "CN", prefix)


async def apply_refund(
    *,
    refund_id: str,
    payment_id: str,
    amount_minor: int,
    currency: str,
    reason: str | None,
    created_by: str | None,
    status: str = "processed",
    cap_to_remaining: bool = False,
    ledger_kind: str = "razorpay_refund",
    event_action: str = "wallet.topup.refunded",
) -> dict:
    """Reverse the wallet and issue a GST credit note for a provider refund.

    A refund that the provider has not finished processing is recorded but moves
    no money: reversing the wallet on a pending refund would take balance for a
    refund that can still fail. The `refund.processed` webhook (or the pending
    reconciliation loop) completes it exactly once.

    `processed` is terminal. Events arrive out of order (a delayed
    `refund.failed` or a pending sync after `refund.processed`), and downgrading
    a processed row would let the next processed event reverse the wallet again.

    The wallet may go negative: the customer is entitled to the refund even if
    they have already spent the credits, and a negative balance is the honest
    representation of that debt.

    Lost chargebacks reuse this path with `refund_id="dispute:<id>"`, so they
    get the same exactly-once ledger, credit note and cumulative cap.
    """
    from sqlalchemy.exc import IntegrityError

    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    if not refund_id or not payment_id:
        logger.warning("refund event without refund or payment id ignored")
        return {"ok": True, "ignored": True, "refundId": refund_id}

    refund_status = str(status or "processed").strip().lower()
    async with factory() as session:
        # Lock the invoice first: every refund of one payment serialises on it,
        # so the cumulative totals below cannot race a concurrent refund.
        invoice = (
            await session.execute(
                select(BillingInvoice)
                .where(BillingInvoice.razorpay_payment_id == payment_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if invoice is None:
            logger.warning("refund for unknown payment ignored refund_id=%s", refund_id)
            return {"ok": True, "ignored": True, "refundId": refund_id}

        existing = await session.get(
            RazorpayRefund, refund_id, with_for_update=True, populate_existing=True
        )
        if existing is not None and existing.status == "processed":
            return {
                "ok": True,
                "duplicate": True,
                "refundId": refund_id,
                "refundStatus": "processed",
            }

        refund_minor = max(0, int(amount_minor or 0))
        if refund_status != "processed":
            # Pending/failed: keep the provider's state for support, change nothing else.
            if existing is None:
                session.add(
                    RazorpayRefund(
                        refund_id=refund_id,
                        tenant_id=invoice.tenant_id,
                        payment_id=payment_id,
                        order_id=invoice.razorpay_order_id,
                        amount_minor=refund_minor,
                        currency=currency or invoice.currency or "INR",
                        credit_inr_paise=0,
                        tax_inr_paise=0,
                        status=refund_status,
                        reason=(reason or "")[:2000] or None,
                        created_by=created_by,
                        created_at=_utcnow(),
                    )
                )
            else:
                existing.status = refund_status
                existing.reason = (reason or existing.reason or "")[:2000] or None
            await session.commit()
            return {
                "ok": True,
                "pending": refund_status != "failed",
                "refundId": refund_id,
                "refundStatus": refund_status,
                "invoiceStatus": invoice.status,
                "walletReversalInr": 0.0,
                "taxReversalInr": 0.0,
            }

        gross_minor = int(invoice.amount_minor or 0) or int(invoice.amount_inr_paise or 0)
        if str(currency or invoice.currency).upper() != str(invoice.currency or "INR").upper():
            raise ValueError("refund_currency_mismatch")
        # Allocate the cumulative refund, then subtract what was already reversed.
        # Independent rounding of small partial refunds can otherwise debit more
        # wallet credit or GST than the invoice ever contained.
        previous = (await session.execute(select(
            func.coalesce(func.sum(RazorpayRefund.amount_minor), 0),
            func.coalesce(func.sum(RazorpayRefund.credit_inr_paise), 0),
            func.coalesce(func.sum(RazorpayRefund.tax_inr_paise), 0),
            select(func.coalesce(func.sum(CreditNote.cgst_inr_paise), 0)).where(
                CreditNote.tenant_id == invoice.tenant_id, CreditNote.invoice_id == invoice.invoice_id,
            ).scalar_subquery(),
            select(func.coalesce(func.sum(CreditNote.sgst_inr_paise), 0)).where(
                CreditNote.tenant_id == invoice.tenant_id, CreditNote.invoice_id == invoice.invoice_id,
            ).scalar_subquery(),
        ).where(RazorpayRefund.tenant_id == invoice.tenant_id, RazorpayRefund.payment_id == payment_id,
                RazorpayRefund.status == "processed", RazorpayRefund.refund_id != refund_id))).one()
        prior_refunded, prior_credit, prior_tax, prior_cgst, _prior_sgst = (int(value or 0) for value in previous)
        if cap_to_remaining and gross_minor > 0:
            refund_minor = min(refund_minor, gross_minor - prior_refunded)
            if refund_minor <= 0:
                return {"ok": True, "ignored": True, "nothingRemaining": True, "refundId": refund_id}
        if refund_minor <= 0 or gross_minor <= 0 or prior_refunded + refund_minor > gross_minor:
            raise ValueError("invalid_refund_amount")
        from decimal import ROUND_HALF_UP, Decimal
        ratio = Decimal(prior_refunded + refund_minor) / gross_minor
        def remaining_share(total, reversed_amount):
            target = int((Decimal(int(total or 0)) * ratio).quantize(Decimal(1), rounding=ROUND_HALF_UP))
            return max(0, min(int(total or 0) - reversed_amount, target - reversed_amount))
        credit_reversal = remaining_share(invoice.amount_inr_paise, prior_credit)
        tax_reversal = remaining_share(invoice.tax_inr_paise, prior_tax)
        if invoice.tax_kind == "cgst_sgst":
            cgst_reversal = min(tax_reversal, remaining_share(invoice.cgst_inr_paise, prior_cgst))
            sgst_reversal = tax_reversal - cgst_reversal
            igst_reversal = 0
        elif invoice.tax_kind == "igst":
            igst_reversal = tax_reversal
            cgst_reversal = sgst_reversal = 0
        else:
            cgst_reversal = sgst_reversal = igst_reversal = 0
            tax_reversal = 0

        # Same as the credit path: a ledger row must always have a wallet row.
        wallet = await _locked_wallet(session, invoice.tenant_id)
        wallet.balance_inr_paise = int(wallet.balance_inr_paise or 0) - credit_reversal
        wallet.updated_at = _utcnow()

        from server.services.saas.tax_service import load_config

        tax_config = await load_config()
        cn_number, fy, sequence = await _allocate_credit_note(
            session, str(tax_config.get("creditNotePrefix") or "CN")
        )
        note = CreditNote(
            tenant_id=invoice.tenant_id,
            invoice_id=invoice.invoice_id,
            invoice_number=invoice.invoice_number,
            credit_note_number=cn_number,
            razorpay_refund_id=refund_id,
            reason=(reason or "Payment refunded")[:2000],
            currency=currency or invoice.currency or "INR",
            gross_inr_paise=credit_reversal + tax_reversal,
            taxable_inr_paise=credit_reversal,
            tax_inr_paise=tax_reversal,
            cgst_inr_paise=cgst_reversal,
            sgst_inr_paise=sgst_reversal,
            igst_inr_paise=igst_reversal,
            tax_rate_bps=int(invoice.tax_rate_bps or 0),
            tax_kind=invoice.tax_kind or "none",
            fy=fy,
            sequence=sequence,
            supplier_snapshot=invoice.supplier_snapshot or {},
            buyer_snapshot=invoice.buyer_snapshot or {},
            status="issued",
            created_by=created_by,
            created_at=_utcnow(),
        )
        session.add(note)
        if existing is not None:
            existing.status = "processed"
            existing.amount_minor = refund_minor
            existing.currency = currency or invoice.currency or "INR"
            existing.credit_inr_paise = credit_reversal
            existing.tax_inr_paise = tax_reversal
            existing.processed_at = _utcnow()
        else:
            session.add(
                RazorpayRefund(
                    refund_id=refund_id,
                    tenant_id=invoice.tenant_id,
                    payment_id=payment_id,
                    order_id=invoice.razorpay_order_id,
                    amount_minor=refund_minor,
                    currency=currency or invoice.currency or "INR",
                    credit_inr_paise=credit_reversal,
                    tax_inr_paise=tax_reversal,
                    status="processed",
                    reason=(reason or "")[:2000] or None,
                    created_by=created_by,
                    created_at=_utcnow(),
                    processed_at=_utcnow(),
                )
            )
        session.add(
            BillingWalletTransaction(
                tenant_id=invoice.tenant_id,
                amount_cents=0,
                amount_inr_paise=-credit_reversal,
                kind=ledger_kind,
                reference_id=f"razorpay_refund:{refund_id}",
                created_at=_utcnow(),
            )
        )
        full = int(prior_refunded) + refund_minor >= gross_minor
        invoice.status = "refunded" if full else "partially_refunded"
        if invoice.razorpay_order_id:
            order = await session.get(RazorpayOrder, invoice.razorpay_order_id, with_for_update=True)
            if order is not None:
                order.status = "refunded" if full else "partially_refunded"
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return {"ok": True, "duplicate": True, "refundId": refund_id}

        from server.services.saas.activity_log import record_event

        await record_event(
            action=event_action,
            resource_type="credit_note",
            resource_id=str(note.credit_note_id),
            actor=created_by or "provider",
            tenant_id=invoice.tenant_id,
            payload={
                "refundId": refund_id,
                "paymentId": payment_id,
                "invoiceNumber": invoice.invoice_number,
                "creditNoteNumber": cn_number,
                "amountMinor": refund_minor,
                "currency": currency,
                "walletReversalInr": credit_reversal / 100.0,
                "taxReversalInr": tax_reversal / 100.0,
            },
            source="admin" if created_by else "webhook",
        )
        return {
            "ok": True,
            "refundId": refund_id,
            "creditNoteId": str(note.credit_note_id),
            "creditNoteNumber": cn_number,
            "walletReversalInr": credit_reversal / 100.0,
            "taxReversalInr": tax_reversal / 100.0,
            "invoiceStatus": invoice.status,
            "duplicate": False,
        }


_REFUND_PROVIDER_ERRORS = (
    razorpay.errors.BadRequestError,
    razorpay.errors.GatewayError,
    razorpay.errors.ServerError,
    requests.exceptions.RequestException,
    TimeoutError,
)


async def refund_order(
    order_id: str,
    *,
    amount_minor: int | None,
    reason: str,
    actor: str,
) -> dict:
    """Refund a captured top-up through Razorpay, then reverse the ledger.

    Exactly-once rules, because a second click or a retried request after a
    timeout must never refund twice:

    * The order row is locked for the whole decision, so two admins refunding
      the same order run one after the other.
    * A local pending refund blocks another until it settles.
    * Razorpay's own list of refunds for the payment is read first. A refund
      it has that we do not (an earlier call timed out after Razorpay accepted
      it) is recorded and the new request is refused.
    * The amount is capped at what is still refundable (gross minus processed
      and pending refunds), and "full refund" means that remainder.
    """
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")

    drift: list[dict] = []
    refund_id = ""
    refund_amount = 0
    refund_currency = "INR"
    entity_status = "pending"
    async with factory() as session:
        order = await session.get(RazorpayOrder, order_id, with_for_update=True)
        if order is None:
            raise ValueError("order_not_found")
        if order.status not in ("paid", "partially_refunded"):
            raise ValueError("order_not_refundable")
        payment_id = order.payment_id
        tenant_id = order.tenant_id
        currency = order.currency or "INR"
        gross_minor = int(order.gross_minor or order.amount_minor or 0)
        if not payment_id:
            raise ValueError("order_not_refundable")

        local = list(
            (
                await session.execute(
                    select(RazorpayRefund).where(RazorpayRefund.payment_id == payment_id)
                )
            ).scalars()
        )
        if any(str(r.status) == "pending" for r in local):
            raise ValueError("refund_in_progress")

        try:
            listed = await _run_provider_call(
                _client().payment.fetch_multiple_refund, payment_id, {"count": 100}
            )
        except _REFUND_PROVIDER_ERRORS as exc:
            logger.warning("razorpay refund list failed error_type=%s", type(exc).__name__)
            raise ValueError("refund_check_unavailable") from None
        items = listed.get("items") if isinstance(listed, dict) else None
        if not isinstance(items, list):
            raise ValueError("refund_check_unavailable")
        provider_refunds = [
            item for item in items
            if isinstance(item, dict) and item.get("id")
            and str(item.get("status") or "").lower() != "failed"
        ]
        known = {r.refund_id for r in local}
        drift = [item for item in provider_refunds if str(item["id"]) not in known]

        if not drift:
            provider_used = sum(int(item.get("amount") or 0) for item in provider_refunds)
            local_used = sum(
                int(r.amount_minor or 0) for r in local if str(r.status) in ("processed", "pending")
            )
            remaining = gross_minor - max(provider_used, local_used)
            if remaining <= 0:
                raise ValueError("order_not_refundable")
            refund_minor = int(amount_minor) if amount_minor else remaining
            if refund_minor <= 0 or refund_minor > remaining:
                raise ValueError("invalid_refund_amount")

            try:
                entity = await _run_provider_call(
                    _client().payment.refund,
                    payment_id,
                    {
                        "amount": refund_minor,
                        # Unique per attempt; makes the refund traceable in the
                        # dashboard if this request dies before we record it.
                        "receipt": f"rf_{uuid.uuid4().hex[:20]}",
                        "notes": {"reason": reason[:200], "order_id": order_id},
                    },
                )
            except _REFUND_PROVIDER_ERRORS as exc:
                logger.warning("razorpay refund failed error_type=%s", type(exc).__name__)
                raise ValueError("refund_failed") from None

            refund_id = str((entity or {}).get("id") or "") if isinstance(entity, dict) else ""
            if not refund_id:
                raise ValueError("refund_failed")
            refund_amount = int(entity.get("amount") or refund_minor)
            refund_currency = str(entity.get("currency") or currency)
            entity_status = str(entity.get("status") or "pending").strip().lower()
            # Record the refund before the lock is released, as pending: it has
            # moved no wallet balance yet, and it blocks a concurrent refund.
            session.add(
                RazorpayRefund(
                    refund_id=refund_id,
                    tenant_id=tenant_id,
                    payment_id=payment_id,
                    order_id=order_id,
                    amount_minor=refund_amount,
                    currency=refund_currency,
                    credit_inr_paise=0,
                    tax_inr_paise=0,
                    status="pending",
                    reason=(reason or "")[:2000] or None,
                    created_by=actor,
                    created_at=_utcnow(),
                )
            )
            await session.commit()

    if drift:
        for item in drift:
            try:
                await apply_refund(
                    refund_id=str(item["id"]),
                    payment_id=payment_id,
                    amount_minor=int(item.get("amount") or 0),
                    currency=str(item.get("currency") or currency),
                    reason="Refund found at Razorpay and recorded",
                    created_by=None,
                    status=str(item.get("status") or "pending"),
                )
            except Exception as exc:
                logger.error("refund drift record failed error_type=%s", type(exc).__name__)
        logger.error(
            "razorpay refund drift order=%s unknown_refunds=%s",
            order_id,
            [str(item["id"]) for item in drift],
        )
        raise ValueError("refund_already_exists")

    if entity_status == "pending":
        return {
            "ok": True,
            "pending": True,
            "refundId": refund_id,
            "refundStatus": "pending",
            "walletReversalInr": 0.0,
            "taxReversalInr": 0.0,
        }
    return await apply_refund(
        refund_id=refund_id,
        payment_id=payment_id,
        amount_minor=refund_amount,
        currency=refund_currency,
        reason=reason,
        created_by=actor,
        status=entity_status,
    )


#: Dispute phases that need an operator now (evidence deadline or money lost).
_URGENT_DISPUTE_EVENTS = (
    "payment.dispute.created",
    "payment.dispute.action_required",
    "payment.dispute.lost",
)


async def handle_dispute_event(event_type: str, dispute: dict, payment: dict) -> str:
    """Record a chargeback and alert; reverse the wallet once if it is lost.

    Each phase is written to the activity log (the operator's alert feed) with
    the dispute id as the resource, at error severity when it needs action. A
    lost dispute means the bank took the money back: the wallet credit and GST
    are reversed through `apply_refund` keyed on `dispute:<id>`, which makes the
    reversal exactly-once across webhook retries and issues a credit note.
    """
    dispute_id = str(dispute.get("id") or "")
    payment_id = str(dispute.get("payment_id") or payment.get("id") or "")
    if not dispute_id or not payment_id:
        return "ignored"
    order_id = str(payment.get("order_id") or "") or None
    amount_minor = dispute.get("amount")
    currency = str(dispute.get("currency") or payment.get("currency") or "INR").upper()

    tenant_id = None
    factory = get_session_factory()
    if factory is not None:
        async with factory() as session:
            invoice = (
                await session.execute(
                    select(BillingInvoice).where(BillingInvoice.razorpay_payment_id == payment_id)
                )
            ).scalar_one_or_none()
            if invoice is not None:
                tenant_id = invoice.tenant_id
                order_id = order_id or invoice.razorpay_order_id
            elif order_id:
                order = await session.get(RazorpayOrder, order_id)
                tenant_id = order.tenant_id if order is not None else None

    phase = event_type.rsplit(".", 1)[-1]
    urgent = event_type in _URGENT_DISPUTE_EVENTS
    (logger.error if urgent else logger.warning)(
        "razorpay dispute event=%s dispute=%s payment=%s status=%s",
        event_type,
        dispute_id,
        payment_id,
        dispute.get("status"),
    )
    from server.services.saas.activity_log import record_event

    await record_event(
        action=f"payment.dispute.{phase}",
        resource_type="payment_dispute",
        resource_id=dispute_id,
        actor="razorpay",
        tenant_id=tenant_id,
        payload={
            "disputeId": dispute_id,
            "paymentId": payment_id,
            "orderId": order_id,
            "amountMinor": amount_minor,
            "currency": currency,
            "status": dispute.get("status"),
            "phase": dispute.get("phase"),
            "reasonCode": dispute.get("reason_code"),
            "respondBy": dispute.get("respond_by"),
            "knownPayment": tenant_id is not None,
        },
        source="webhook",
        outcome="error" if urgent else "ok",
        severity="error" if urgent else "warning",
    )

    if event_type != "payment.dispute.lost":
        return "handled" if tenant_id is not None else "ignored"
    if isinstance(amount_minor, bool) or not isinstance(amount_minor, int) or amount_minor <= 0:
        raise ValueError("invalid_refund_amount")
    result = await apply_refund(
        refund_id=f"dispute:{dispute_id}",
        payment_id=payment_id,
        amount_minor=amount_minor,
        currency=currency,
        reason=f"Chargeback lost ({dispute.get('reason_code') or 'dispute'})",
        created_by=None,
        status="processed",
        # Earlier refunds may already have returned part of the money; reverse
        # only what is left rather than refusing the chargeback.
        cap_to_remaining=True,
        ledger_kind="razorpay_chargeback",
        event_action="wallet.topup.chargeback",
    )
    return "ignored" if result.get("ignored") else "handled"


async def reconcile_order(order_id: str, *, source: str) -> dict:
    """Ask Razorpay for one order's payments and settle the local row.

    Captured payments are all passed to the credit path (a second capture is
    flagged for refund there, never credited). An authorised payment is
    captured and credited. Only a latest payment that actually *failed* marks
    the order failed; created/pending payments are left to be checked again.
    """
    payments = await _run_provider_call(_client().order.payments, order_id)
    items = payments.get("items", []) if isinstance(payments, dict) else []
    items = [item for item in items if isinstance(item, dict)]
    captured = [p for p in items if str(p.get("status")) == "captured"]
    if captured:
        first: dict = {}
        for payment in captured:
            outcome = await credit_provider_payment(payment, source=source)
            first = first or outcome
        return {**first, "outcome": "credited", "checked": len(items)}
    authorized = [p for p in items if str(p.get("status")) == "authorized"]
    if authorized:
        outcome = await capture_authorized_payment(authorized[0], source=source)
        state = "authorized" if outcome.get("captured") is False else "credited"
        return {**outcome, "outcome": state, "checked": len(items)}
    if items and str(items[0].get("status")) == "failed":
        await mark_order_failed(items[0], source=source)
        return {"outcome": "failed", "checked": len(items)}
    return {"outcome": "pending", "checked": len(items)}


async def _claim_for_reconciliation(session, now: datetime, *, slow: bool, limit: int) -> list[str]:
    """Pick the orders least recently checked and stamp them as checked now.

    Ordering by `last_reconciled_at NULLS FIRST` makes each lane round robin:
    a never-checked order goes first, and an abandoned order that keeps coming
    back pending moves to the back instead of starving newer ones.
    """
    if slow:
        condition = sa.and_(
            _ORDERS.c.status == "expired",
            _ORDERS.c.created_at >= now - LATE_CAPTURE_WINDOW,
            sa.or_(
                _ORDERS.c.last_reconciled_at.is_(None),
                _ORDERS.c.last_reconciled_at <= now - SLOW_LANE_INTERVAL,
            ),
        )
    else:
        condition = sa.and_(
            _ORDERS.c.status.in_(OPEN_ORDER_STATUSES),
            _ORDERS.c.created_at > now - ORDER_EXPIRY,
            _ORDERS.c.created_at <= now - RECONCILE_AFTER,
        )
    ids = list(
        (
            await session.execute(
                sa.select(_ORDERS.c.order_id)
                .where(condition)
                .order_by(
                    _ORDERS.c.last_reconciled_at.asc().nulls_first(),
                    _ORDERS.c.created_at.asc(),
                )
                .limit(max(1, min(limit, 50)))
            )
        ).scalars()
    )
    if ids:
        await session.execute(
            sa.update(_ORDERS).where(_ORDERS.c.order_id.in_(ids)).values(last_reconciled_at=now)
        )
    return ids


async def expire_stale_orders(now: datetime | None = None) -> int:
    """Expire every unpaid order past its expiry in one statement.

    Separate from the provider checks so expiry happens even while the fast
    lane is saturated. Expired orders stay creditable and move to the slow lane.
    """
    factory = get_session_factory()
    if factory is None:
        return 0
    now = now or _utcnow()
    async with factory() as session:
        result = await session.execute(
            sa.update(_ORDERS)
            .where(
                _ORDERS.c.status.in_(OPEN_ORDER_STATUSES),
                sa.or_(
                    _ORDERS.c.expires_at <= now,
                    sa.and_(
                        _ORDERS.c.expires_at.is_(None),
                        _ORDERS.c.created_at <= now - ORDER_EXPIRY,
                    ),
                ),
            )
            .values(status="expired")
        )
        await session.commit()
        return int(result.rowcount or 0)


async def reconcile_pending_orders(limit: int = 10, *, include_slow_lane: bool = True) -> dict:
    """Compare local orders with the provider and settle any drift.

    Covers the failure modes checkout cannot: the browser closed after paying,
    the verify call timed out, or a webhook was never delivered.

    * Expiry: open orders past their expiry become `expired` in bulk.
    * Fast lane: open orders 10 minutes to 24 hours old, round robin.
    * Slow lane: expired orders up to 7 days old, each at most once per
      SLOW_LANE_INTERVAL, for late captures. A capture found there is credited
      and raised as an error-level alert by the credit path.
    """
    factory = get_session_factory()
    if factory is None:
        return {"checked": 0, "lateChecked": 0, "credited": 0, "failed": 0, "expired": 0}
    now = _utcnow()
    # Expire first, so an order that just crossed the line is late-checked in
    # this same pass instead of waiting for the next one.
    expired = await expire_stale_orders(now)
    async with factory() as session:
        fast_ids = await _claim_for_reconciliation(session, now, slow=False, limit=limit)
        slow_ids: list[str] = []
        if include_slow_lane:
            slow_ids = await _claim_for_reconciliation(
                session, now, slow=True, limit=max(1, limit // 2)
            )
        await session.commit()

    credited = failed = 0
    for order_id in [*fast_ids, *slow_ids]:
        try:
            outcome = await reconcile_order(order_id, source="reconciliation")
        except Exception as exc:  # provider outage must not kill the loop
            logger.warning("reconcile order failed error_type=%s", type(exc).__name__)
            continue
        if outcome.get("outcome") == "credited" and not outcome.get("duplicate"):
            credited += 1
        elif outcome.get("outcome") == "failed":
            failed += 1

    return {
        "checked": len(fast_ids),
        "lateChecked": len(slow_ids),
        "credited": credited,
        "failed": failed,
        "expired": expired,
    }


async def reconcile_pending_refunds(limit: int = 10) -> dict:
    """Settle refunds the provider accepted but has not finished.

    A pending refund has moved no wallet balance, so it must not be forgotten if
    the `refund.processed` webhook is never delivered.
    """
    factory = get_session_factory()
    if factory is None:
        return {"checked": 0, "processed": 0, "failed": 0}
    async with factory() as session:
        rows = list(
            (
                await session.execute(
                    select(RazorpayRefund)
                    .where(RazorpayRefund.status == "pending")
                    .order_by(RazorpayRefund.created_at.asc())
                    .limit(max(1, min(limit, 50)))
                )
            ).scalars()
        )
        pending = [(r.refund_id, r.payment_id, int(r.amount_minor or 0), r.currency) for r in rows]

    processed = failed = 0
    for refund_id, payment_id, amount_minor, currency in pending:
        if str(refund_id).startswith("dispute:"):
            continue  # chargebacks are not provider refunds
        try:
            entity = await _run_provider_call(_client().refund.fetch, refund_id)
        except Exception as exc:
            logger.warning("reconcile refund fetch failed error_type=%s", type(exc).__name__)
            continue
        if not isinstance(entity, dict):
            continue
        status = str(entity.get("status") or "").strip().lower()
        if status not in ("processed", "failed"):
            continue
        try:
            await apply_refund(
                refund_id=refund_id,
                payment_id=payment_id,
                amount_minor=int(entity.get("amount") or amount_minor),
                currency=str(entity.get("currency") or currency),
                reason="Refund reconciled from Razorpay",
                created_by=None,
                status=status,
            )
        except Exception as exc:
            logger.error("reconcile refund apply failed error_type=%s", type(exc).__name__)
            continue
        if status == "processed":
            processed += 1
        else:
            failed += 1
    return {"checked": len(pending), "processed": processed, "failed": failed}
