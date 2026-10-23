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

#: Orders older than this are reconciled and then expired if still unpaid.
ORDER_EXPIRY = timedelta(hours=24)
#: Do not call the provider for orders younger than this; checkout is in flight.
RECONCILE_AFTER = timedelta(minutes=10)


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

    currency_code = normalize_currency(currency)
    floor = MIN_CHARGE.get(currency_code, 1.0)
    ceiling = MAX_CHARGE.get(currency_code, 5000.0)
    if amount < floor:
        raise ValueError("minimum_amount")
    if amount > ceiling:
        raise ValueError("maximum_amount")

    rates = await load_current_rates()
    tax_config = await load_config()
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
) -> None:
    """Fail closed unless Razorpay confirms the exact signed payment and order."""
    provider_payment_id = payment.get("id")
    if not provider_payment_id or str(provider_payment_id) != payment_id:
        raise ValueError("payment_id_mismatch")

    provider_order = payment.get("order_id")
    if not provider_order or str(provider_order) != order_id:
        raise ValueError("payment_order_mismatch")

    status = str(payment.get("status") or "").strip().lower()
    if status != "captured":
        raise ValueError("payment_not_captured")

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


async def _credit_order_payment(order_id: str, payment_id: str, payment: dict, *, source: str) -> dict:
    """The single writer of a top-up credit, used by verify, webhook and recovery."""
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")

    ref_id = f"razorpay:{payment_id}"
    async with factory() as session:
        existing_tx = (
            await session.execute(
                select(BillingWalletTransaction).where(
                    BillingWalletTransaction.reference_id == ref_id
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
                "duplicate": True,
            }

        row = await session.get(RazorpayOrder, order_id, with_for_update=True)
        if row is None:
            raise ValueError("order_not_found")
        tenant_id = row.tenant_id

        if row.status == "paid":
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

        currency = getattr(row, "currency", None) or "INR"
        gross_minor = int(getattr(row, "gross_minor", None) or row.amount_minor or 0)
        _validate_payment_details(
            payment,
            payment_id=payment_id,
            order_id=order_id,
            currency=currency,
            amount_minor=gross_minor,
        )

        base_amount = payment.get("base_amount")
        international = bool(payment.get("international")) or currency != "INR"
        credit_paise = int(row.amount_inr_paise or 0)
        if international:
            # Razorpay's own conversion is authoritative for the INR proceeds.
            if base_amount:
                credit_paise = int(base_amount)
        elif currency == "INR":
            credit_paise = int(getattr(row, "taxable_minor", None) or 0) or int(
                row.amount_inr_paise or 0
            )

        gross_minor = int(payment.get("amount") or gross_minor)
        taxable_minor = int(getattr(row, "taxable_minor", None) or 0)
        tax_minor = int(getattr(row, "tax_minor", None) or 0)
        if currency == "INR":
            taxable_paise = credit_paise
            tax_paise = tax_minor
        else:
            taxable_paise = credit_paise
            tax_paise = 0

        tax_kind = str(getattr(row, "tax_kind", None) or "none")
        if tax_kind == "cgst_sgst":
            cgst = tax_paise // 2
            sgst = tax_paise - cgst
            igst = 0
        elif tax_kind == "igst":
            cgst = sgst = 0
            igst = tax_paise
        else:
            cgst = sgst = igst = 0

        wallet = await session.get(BillingWallet, tenant_id, with_for_update=True)
        if wallet is None:
            wallet = BillingWallet(
                tenant_id=tenant_id, balance_cents=0, balance_inr_paise=0, updated_at=_utcnow()
            )
            session.add(wallet)
            await session.flush()
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
        if row is None or row.status in ("paid", "refunded", "partially_refunded"):
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
) -> dict:
    """Reverse the wallet and issue a GST credit note for a provider refund.

    A refund that the provider has not finished processing is recorded but moves
    no money: reversing the wallet on a pending refund would take balance for a
    refund that can still fail. The `refund.processed` webhook (or the pending
    reconciliation loop) completes it exactly once.

    The wallet may go negative: the customer is entitled to the refund even if
    they have already spent the credits, and a negative balance is the honest
    representation of that debt.
    """
    from sqlalchemy.exc import IntegrityError

    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")

    refund_status = str(status or "processed").strip().lower()
    async with factory() as session:
        existing = await session.get(RazorpayRefund, refund_id)
        if existing is not None and existing.status == "processed" and refund_status == "processed":
            return {"ok": True, "duplicate": True, "refundId": refund_id}

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
        if gross_minor > 0:
            ratio = min(1.0, refund_minor / gross_minor)
        else:
            ratio = 1.0
        credit_reversal = int(round(int(invoice.amount_inr_paise or 0) * ratio))
        tax_reversal = int(round(int(invoice.tax_inr_paise or 0) * ratio))
        cgst_reversal = int(round(int(invoice.cgst_inr_paise or 0) * ratio))
        sgst_reversal = int(round(int(invoice.sgst_inr_paise or 0) * ratio))
        igst_reversal = int(round(int(invoice.igst_inr_paise or 0) * ratio))
        if invoice.tax_kind == "cgst_sgst":
            # Keep the two halves summing to the full reversal.
            cgst_reversal = min(cgst_reversal, tax_reversal)
            sgst_reversal = tax_reversal - cgst_reversal
            igst_reversal = 0
        elif invoice.tax_kind == "igst":
            igst_reversal = tax_reversal
            cgst_reversal = sgst_reversal = 0
        else:
            cgst_reversal = sgst_reversal = igst_reversal = 0
            tax_reversal = 0

        wallet = await session.get(BillingWallet, invoice.tenant_id, with_for_update=True)
        if wallet is not None:
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
                kind="razorpay_refund",
                reference_id=f"razorpay_refund:{refund_id}",
                created_at=_utcnow(),
            )
        )
        # A second partial refund must count the first before deciding whether
        # the payment is now fully refunded.
        prior_refunded = (
            await session.execute(
                select(func.coalesce(func.sum(RazorpayRefund.amount_minor), 0)).where(
                    RazorpayRefund.payment_id == payment_id,
                    RazorpayRefund.status == "processed",
                    RazorpayRefund.refund_id != refund_id,
                )
            )
        ).scalar_one() or 0
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
            action="wallet.topup.refunded",
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


async def refund_order(
    order_id: str,
    *,
    amount_minor: int | None,
    reason: str,
    actor: str,
) -> dict:
    """Refund a captured top-up through Razorpay, then reverse the ledger."""
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    async with factory() as session:
        order = await session.get(RazorpayOrder, order_id)
        if order is None:
            raise ValueError("order_not_found")
        if order.status not in ("paid", "partially_refunded"):
            raise ValueError("order_not_refundable")
        payment_id = order.payment_id
        currency = order.currency or "INR"
        gross_minor = int(order.gross_minor or order.amount_minor or 0)
        if not payment_id:
            raise ValueError("order_not_refundable")

    refund_minor = int(amount_minor) if amount_minor else gross_minor
    if refund_minor <= 0 or refund_minor > gross_minor:
        raise ValueError("invalid_refund_amount")

    try:
        entity = await _run_provider_call(
            _client().payment.refund,
            payment_id,
            {"amount": refund_minor, "notes": {"reason": reason[:200], "order_id": order_id}},
        )
    except (
        razorpay.errors.BadRequestError,
        razorpay.errors.GatewayError,
        razorpay.errors.ServerError,
        requests.exceptions.RequestException,
        TimeoutError,
    ) as exc:
        logger.warning("razorpay refund failed error_type=%s", type(exc).__name__)
        raise ValueError("refund_failed") from None

    refund_id = str(entity.get("id") or "")
    if not refund_id:
        raise ValueError("refund_failed")
    return await apply_refund(
        refund_id=refund_id,
        payment_id=str(entity.get("payment_id") or payment_id),
        amount_minor=int(entity.get("amount") or refund_minor),
        currency=str(entity.get("currency") or currency),
        reason=reason,
        created_by=actor,
        status=str(entity.get("status") or "processed"),
    )


async def reconcile_pending_orders(limit: int = 10) -> dict:
    """Compare recent local orders with the provider and settle any drift.

    Covers the failure modes checkout cannot: the browser closed after paying,
    the verify call timed out, or a webhook was never delivered.
    """
    factory = get_session_factory()
    if factory is None:
        return {"checked": 0, "credited": 0, "failed": 0, "expired": 0}
    now = _utcnow()
    async with factory() as session:
        rows = list(
            (
                await session.execute(
                    select(RazorpayOrder)
                    .where(
                        RazorpayOrder.status.in_(("created", "attempted", "failed")),
                        RazorpayOrder.created_at >= now - ORDER_EXPIRY,
                        RazorpayOrder.created_at <= now - RECONCILE_AFTER,
                    )
                    .order_by(RazorpayOrder.created_at.asc())
                    .limit(max(1, min(limit, 50)))
                )
            ).scalars()
        )
        order_ids = [r.order_id for r in rows]

    credited = failed = expired = 0
    for order_id in order_ids:
        try:
            payments = await _run_provider_call(_client().order.payments, order_id)
        except Exception as exc:  # provider outage must not kill the loop
            logger.warning("reconcile order fetch failed error_type=%s", type(exc).__name__)
            continue
        items = payments.get("items", []) if isinstance(payments, dict) else []
        captured = [p for p in items if str(p.get("status")) == "captured"]
        if captured:
            try:
                await credit_provider_payment(captured[0], source="reconciliation")
                credited += 1
                continue
            except Exception as exc:
                logger.error("reconcile credit failed error_type=%s", type(exc).__name__)
        elif items:
            latest = items[0]
            if str(latest.get("status")) in ("failed", "cancelled"):
                await mark_order_failed(latest, source="reconciliation")
                failed += 1
                continue

        async with factory() as session:
            row = await session.get(RazorpayOrder, order_id, with_for_update=True)
            if row is None or row.status == "paid":
                continue
            created = row.created_at
            if created and created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            expiry = row.expires_at or ((created or now) + ORDER_EXPIRY)
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry <= now:
                row.status = "expired"
                await session.commit()
                expired += 1
    return {"checked": len(order_ids), "credited": credited, "failed": failed, "expired": expired}


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
