"""Charge customers in their own currency via Razorpay International Payments.

Razorpay accepts foreign-issued cards (180+ countries) once International
Payments is enabled on the account. The order is created in the configured
currency and Razorpay converts to INR for settlement, reporting the conversion
back on the payment entity as `base_amount` / `international`.

The wallet still credits one INR leg, because that is what the business receives.
Recording the currency actually charged matters: it is what an admin reads when
reconciling an invoice, and what proves the customer was not quietly billed in
rupees.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timezone

import razorpay
from sqlalchemy import select

from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.saas_models import (
    BillingInvoice,
    BillingWallet,
    BillingWalletTransaction,
    RazorpayOrder,
)

logger = logging.getLogger(__name__)

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
    return razorpay.Client(auth=(settings.razorpay_api_key, settings.razorpay_api_secret))


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


def inr_credit_for(currency: str, amount_minor: int) -> int:
    """INR paise to credit the wallet for a payment made in `currency`.

    Prefers the charge rate the admin configured over a live quote, so a top-up
    cannot change price between the order and the payment.
    """
    from server.services.saas.billing_rates import effective_rates

    if currency == "INR":
        return int(amount_minor)
    major = from_minor(amount_minor, currency)
    fx = float(effective_rates()["fx_rate_inr"]) or 95.64
    return int(round(major * fx * 100))


def verify_payment_signature(order_id: str, payment_id: str, signature: str) -> bool:
    settings = get_settings()
    secret = settings.razorpay_api_secret or ""
    payload = f"{order_id}|{payment_id}".encode()
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


async def create_wallet_order(
    tenant_id: uuid.UUID,
    amount: float,
    *,
    currency: str | None = None,
) -> dict:
    """Create a top-up order in `currency` (default: the configured currency)."""
    currency_code = normalize_currency(currency)
    floor = MIN_CHARGE.get(currency_code, 1.0)
    ceiling = MAX_CHARGE.get(currency_code, 5000.0)
    if amount < floor:
        raise ValueError("minimum_amount")
    if amount > ceiling:
        raise ValueError("maximum_amount")

    minor = to_minor(amount, currency_code)
    client = _client()
    try:
        order = client.order.create(
            {
                "amount": minor,
                "currency": currency_code,
                "payment_capture": 1,
                # Razorpay caps receipt at 40 chars; keep ours short and traceable.
                "receipt": f"wallet_{uuid.uuid4().hex[:16]}",
            }
        )
    except razorpay.errors.BadRequestError as exc:
        msg = str(exc)
        logger.warning("razorpay order create failed: %s", msg)
        failure = (
            "razorpay_auth_failed"
            if ("Authentication" in msg or "auth" in msg.lower())
            else "razorpay_order_failed"
        )
        # A checkout that never opens is a support case ("the Add funds button
        # does nothing"). Nothing else records it, because no order row is ever
        # created — and an auth failure is an operator problem, not the user's.
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
                "detail": msg[:200],
            },
            source="subscriber",
            outcome="error",
            severity="error",
        )
        raise ValueError(failure) from exc
    order_id = order["id"]
    paise = inr_credit_for(currency_code, minor)

    # An abandoned order is a real support case ("I paid and nothing happened"),
    # and it is only diagnosable from the log because the order never completes.
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
            "international": currency_code != "INR",
        },
        source="subscriber",
    )

    factory = get_session_factory()
    if factory:
        async with factory() as session:
            session.add(
                RazorpayOrder(
                    order_id=order_id,
                    tenant_id=tenant_id,
                    amount_inr_paise=paise,
                    currency=currency_code,
                    amount_minor=minor,
                    status="created",
                    purpose="wallet_topup",
                    created_at=_utcnow(),
                )
            )
            await session.commit()

    settings = get_settings()
    return {
        "orderId": order_id,
        "currency": currency_code,
        "amount": from_minor(minor, currency_code),
        "amountMinor": minor,
        # What the wallet will be credited, for transparency before paying.
        "creditedInr": paise / 100,
        "international": currency_code != "INR",
        "keyId": settings.razorpay_api_key,
    }


def _fetch_payment(payment_id: str) -> dict | None:
    """Razorpay's own view of the payment, when the API is reachable.

    Used for the settled INR figure and the international flag. A failure here is
    not fatal: we fall back to our own charge rate rather than refuse to credit a
    payment the customer already completed. Note that read endpoints can return a
    throttling "Authentication failed" even on a healthy key, so this is treated
    as best-effort enrichment and never as the basis for accepting a payment.
    """
    try:
        return _client().payment.fetch(payment_id)
    except Exception as exc:
        logger.warning("razorpay payment fetch failed payment=%s err=%s", payment_id, exc)
        return None


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

    async with factory() as session:
        row = await session.get(RazorpayOrder, order_id)
        if row is None or row.tenant_id != tenant_id:
            raise ValueError("order_not_found")
        if row.status == "paid":
            inv = (
                await session.execute(
                    select(BillingInvoice).where(BillingInvoice.razorpay_order_id == order_id)
                )
            ).scalar_one_or_none()
            return {"ok": True, "invoiceId": str(inv.invoice_id) if inv else None, "duplicate": True}

        currency = getattr(row, "currency", None) or "INR"
        amount_minor = int(getattr(row, "amount_minor", None) or 0)
        paise = int(row.amount_inr_paise)

        payment = _fetch_payment(payment_id)
        settled_inr = None
        international = False
        if payment:
            settled_inr = payment.get("base_amount")
            international = bool(payment.get("international"))
            if settled_inr:
                # Razorpay's own conversion is authoritative for what we receive;
                # it is the rate actually applied on the payment date.
                paise = int(settled_inr)

        wallet = await session.get(BillingWallet, tenant_id)
        if wallet is None:
            wallet = BillingWallet(tenant_id=tenant_id, updated_at=_utcnow())
            session.add(wallet)
            await session.flush()
        wallet.balance_inr_paise += paise
        wallet.currency = "inr"
        wallet.updated_at = _utcnow()
        row.status = "paid"
        row.amount_inr_paise = paise

        inv_num = f"INV-{_utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        charged = from_minor(amount_minor, currency) if amount_minor else paise / 100
        invoice = BillingInvoice(
            tenant_id=tenant_id,
            invoice_number=inv_num,
            amount_inr_paise=paise,
            currency=currency,
            amount_minor=amount_minor,
            status="paid",
            razorpay_order_id=order_id,
            razorpay_payment_id=payment_id,
            line_items=[
                {
                    "description": "Wallet top-up",
                    "currency": currency,
                    "amount": charged,
                    "amountInr": paise / 100,
                    "international": international or currency != "INR",
                }
            ],
            created_at=_utcnow(),
        )
        session.add(invoice)
        session.add(
            BillingWalletTransaction(
                tenant_id=tenant_id,
                amount_cents=0,
                amount_inr_paise=paise,
                kind="razorpay_topup_inr",
                stripe_session_id=payment_id,
                created_at=_utcnow(),
            )
        )
        await session.commit()

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
                "charged": charged,
                "creditedInr": paise / 100,
                "international": international or currency != "INR",
                "duplicate": False,
            },
            source="webhook",
        )
        return {
            "ok": True,
            "invoiceId": str(invoice.invoice_id),
            "invoiceNumber": inv_num,
            "currency": currency,
            "charged": charged,
            "international": international or currency != "INR",
            "balanceInr": wallet.balance_inr_paise / 100,
        }


async def list_invoices(tenant_id: uuid.UUID, limit: int = 50) -> list[dict]:
    factory = get_session_factory()
    if factory is None:
        return []
    async with factory() as session:
        result = await session.execute(
            select(BillingInvoice)
            .where(BillingInvoice.tenant_id == tenant_id)
            .order_by(BillingInvoice.created_at.desc())
            .limit(limit)
        )
        return [
            {
                "invoiceId": str(r.invoice_id),
                "invoiceNumber": r.invoice_number,
                "currency": getattr(r, "currency", None) or "INR",
                "amount": from_minor(r.amount_minor, getattr(r, "currency", None) or "INR")
                if getattr(r, "amount_minor", None)
                else r.amount_inr_paise / 100,
                "amountInr": r.amount_inr_paise / 100,
                "status": r.status,
                "createdAt": r.created_at.isoformat(),
                "paymentId": r.razorpay_payment_id,
            }
            for r in result.scalars()
        ]