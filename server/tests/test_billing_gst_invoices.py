"""GST, invoice issuance and refund invariants.

These are the rules money depends on: tax is computed once at checkout and
snapshotted, the wallet is credited the taxable value only, invoice serials are
consecutive per financial year, and a refund reverses exactly its share.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.db.models.saas_models import (
    BillingInvoice,
    BillingWallet,
    BillingWalletTransaction,
    CreditNote,
    InvoiceSequence,
    RazorpayOrder,
    RazorpayRefund,
)
from server.services.saas import billing_profile_service, invoice_service, razorpay_service, tax_service
from server.services.saas.tax_service import (
    compute_tax,
    financial_year,
    financial_year_compact,
    gstin_checksum,
    validate_gstin,
)

TELANGANA = "36"
MAHARASHTRA = "27"
VALID_TELANGANA_GSTIN = "36AABCU9603R1ZO"
VALID_MAHARASHTRA_GSTIN = "27AAPFU0939F1ZV"


def _config(**overrides):
    config = {
        "enabled": True,
        "legalName": "Dialtact Technologies Pvt Ltd",
        "tradeName": "Dialtact",
        "gstin": VALID_TELANGANA_GSTIN,
        "addressLine1": "Plot 12, Hitech City",
        "addressLine2": "",
        "city": "Hyderabad",
        "stateName": "Telangana",
        "stateCode": TELANGANA,
        "postalCode": "500081",
        "countryCode": "IN",
        "supportEmail": "billing@dialtact.com",
        "supportPhone": "",
        "sacCode": "998413",
        "defaultRateBps": 1800,
        "priceIncludesTax": False,
        "exportZeroRated": True,
        "invoicePrefix": "INV",
        "creditNotePrefix": "CN",
        "lutNumber": "",
        "invoiceTerms": "",
    }
    config.update(overrides)
    return config


def _buyer(state_code=TELANGANA, country="IN", gstin=None):
    return {
        "legalName": "Acme Callers",
        "gstin": gstin,
        "email": "billing@acme.test",
        "addressLine1": "1 MG Road",
        "city": "Hyderabad",
        "stateCode": state_code,
        "stateName": tax_service.state_name_for(state_code),
        "countryCode": country,
    }


# ---------------------------------------------------------------------------
# GSTIN and supplier configuration
# ---------------------------------------------------------------------------


def test_gstin_checksum_accepts_known_valid_numbers():
    assert gstin_checksum(VALID_MAHARASHTRA_GSTIN) == "V"
    assert validate_gstin(VALID_MAHARASHTRA_GSTIN) is None
    assert validate_gstin(VALID_TELANGANA_GSTIN) is None
    assert validate_gstin(VALID_MAHARASHTRA_GSTIN.lower()) is None


def test_gstin_validation_rejects_format_state_and_checksum():
    assert validate_gstin("") == "gstin_required"
    assert validate_gstin("27AAPFU0939F1Z") == "gstin_invalid_format"
    assert validate_gstin("99AAPFU0939F1ZV") == "gstin_invalid_state"
    assert validate_gstin("27AAPFU0939F1ZX") == "gstin_invalid_checksum"


def test_config_is_not_compliant_without_identity_or_check_digit():
    assert tax_service.config_configured(_config()) is True
    assert tax_service.config_configured(_config(city="")) is False
    assert tax_service.config_configured(_config(gstin="27AAPFU0939F1ZX")) is False
    assert tax_service.config_configured(_config(stateCode="")) is False


# ---------------------------------------------------------------------------
# Place of supply and tax arithmetic
# ---------------------------------------------------------------------------


def test_same_state_charges_cgst_and_sgst_and_credits_only_taxable_value():
    quote = compute_tax(
        1000.0,
        "INR",
        fx_rate_inr=95.64,
        config=_config(),
        buyer=_buyer(),
    )

    assert quote["taxableInrPaise"] == 100_000
    assert quote["taxInrPaise"] == 18_000
    assert quote["grossInrPaise"] == 118_000
    assert quote["creditInrPaise"] == 100_000  # GST is a liability, never wallet balance
    assert quote["taxKind"] == "cgst_sgst"
    assert quote["cgstInrPaise"] == 9_000
    assert quote["sgstInrPaise"] == 9_000
    assert quote["igstInrPaise"] == 0
    assert quote["placeOfSupply"] == "Telangana"
    assert quote["ratePercent"] == 18.0


def test_different_state_charges_igst():
    quote = compute_tax(
        2500.0,
        "INR",
        fx_rate_inr=95.64,
        config=_config(),
        buyer=_buyer(state_code=MAHARASHTRA),
    )

    assert quote["taxKind"] == "igst"
    assert quote["igstInrPaise"] == 45_000
    assert quote["cgstInrPaise"] == 0
    assert quote["sgstInrPaise"] == 0
    assert quote["grossInrPaise"] == 295_000
    assert quote["placeOfSupply"] == "Maharashtra"


def test_buyer_gstin_state_overrides_the_free_text_state():
    buyer = _buyer(state_code=TELANGANA, gstin=VALID_MAHARASHTRA_GSTIN)
    quote = compute_tax(1000.0, "INR", fx_rate_inr=95.64, config=_config(), buyer=buyer)

    assert quote["taxKind"] == "igst"
    assert quote["placeOfSupplyCode"] == MAHARASHTRA


def test_inclusive_pricing_derives_taxable_value_from_the_gross():
    quote = compute_tax(
        1180.0,
        "INR",
        fx_rate_inr=95.64,
        config=_config(priceIncludesTax=True),
        buyer=_buyer(),
    )

    assert quote["taxableInrPaise"] == 100_000
    assert quote["taxInrPaise"] == 18_000
    assert quote["grossInrPaise"] == 118_000
    assert quote["creditInrPaise"] == 100_000
    assert quote["total"] == 1180.0


def test_foreign_currency_is_a_zero_rated_export():
    quote = compute_tax(
        10.0,
        "USD",
        fx_rate_inr=100.0,
        config=_config(),
        buyer=_buyer(state_code="", country="US"),
    )

    assert quote["export"] is True
    assert quote["taxKind"] == "export"
    assert quote["taxInrPaise"] == 0
    assert quote["taxableInrPaise"] == 100_000
    assert quote["grossInrPaise"] == 100_000
    assert quote["creditInrPaise"] == 100_000


def test_unconfigured_supplier_charges_no_tax():
    quote = compute_tax(
        1000.0,
        "INR",
        fx_rate_inr=95.64,
        config=_config(enabled=False),
        buyer=_buyer(),
    )

    assert quote["taxEnabled"] is False
    assert quote["taxInrPaise"] == 0
    assert quote["taxKind"] == "none"
    assert quote["creditInrPaise"] == 100_000


def test_odd_paise_tax_is_split_without_losing_a_paise():
    quote = compute_tax(
        999.99,
        "INR",
        fx_rate_inr=95.64,
        config=_config(),
        buyer=_buyer(),
    )

    assert quote["taxInrPaise"] == 18_000
    assert quote["cgstInrPaise"] + quote["sgstInrPaise"] == quote["taxInrPaise"]
    assert quote["taxableInrPaise"] + quote["taxInrPaise"] == quote["grossInrPaise"]


# ---------------------------------------------------------------------------
# Financial year and invoice numbering
# ---------------------------------------------------------------------------


def test_financial_year_switches_at_midnight_ist_on_first_april():
    before = datetime(2026, 3, 31, 18, 29, tzinfo=timezone.utc)  # 23:59 IST
    after = datetime(2026, 3, 31, 18, 30, tzinfo=timezone.utc)  # 00:00 IST, 1 April

    assert financial_year(before) == "2025-26"
    assert financial_year(after) == "2026-27"
    assert financial_year_compact("2026-27") == "2627"


@pytest.mark.asyncio
async def test_invoice_numbers_are_consecutive_and_within_sixteen_characters():
    class FakeSession:
        def __init__(self):
            self.rows = {}

        async def get(self, model, ident, **_kwargs):
            if model is InvoiceSequence:
                return self.rows.setdefault(
                    ident, InvoiceSequence(kind=ident[0], fy=ident[1], last_number=0)
                )
            return None

        async def begin_nested(self):  # pragma: no cover - rows always pre-exist here
            raise AssertionError("unexpected sequence insert")

        def add(self, _obj):
            raise AssertionError("unexpected sequence insert")

        async def flush(self):
            pass

    session = FakeSession()
    moment = datetime(2026, 5, 10, tzinfo=timezone.utc)

    first = await invoice_service.allocate_number(session, "INV", "INV", moment=moment)
    second = await invoice_service.allocate_number(session, "INV", "INV", moment=moment)

    assert first == ("INV-2627-000001", "2026-27", 1)
    assert second == ("INV-2627-000002", "2026-27", 2)
    assert len(second[0]) <= 16


# ---------------------------------------------------------------------------
# Invoice payload and PDF
# ---------------------------------------------------------------------------

def _invoice(**overrides):
    values = {
        "invoice_id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "invoice_number": "INV-2627-000007",
        "status": "paid",
        "currency": "INR",
        "amount_minor": 118_000,
        "amount_inr_paise": 100_000,
        "taxable_minor": 100_000,
        "tax_minor": 18_000,
        "taxable_inr_paise": 100_000,
        "tax_inr_paise": 18_000,
        "cgst_inr_paise": 9_000,
        "sgst_inr_paise": 9_000,
        "igst_inr_paise": 0,
        "tax_rate_bps": 1_800,
        "tax_kind": "cgst_sgst",
        "sac_code": "998413",
        "place_of_supply": "Telangana",
        "place_of_supply_code": TELANGANA,
        "customer_gstin": None,
        "supplier_snapshot": tax_service.supplier_snapshot(_config()),
        "buyer_snapshot": _buyer(),
        "fy": "2026-27",
        "sequence": 7,
        "razorpay_order_id": "order_test",
        "razorpay_payment_id": "pay_test",
        "payment_method": "upi",
        "paid_at": datetime(2026, 5, 10, 10, 0, tzinfo=timezone.utc),
        "created_at": datetime(2026, 5, 10, 10, 0, tzinfo=timezone.utc),
        "line_items": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_invoice_payload_reports_gross_and_taxable_separately():
    payload = invoice_service.invoice_payload(_invoice())

    assert payload["gross"] == 1180.0
    assert payload["subtotal"] == 1000.0
    assert payload["tax"] == 180.0
    assert payload["grossInr"] == 1180.0
    assert payload["taxableInr"] == 1000.0
    assert payload["taxInr"] == 180.0
    assert payload["taxKind"] == "cgst_sgst"
    assert payload["downloadUrl"].endswith("/pdf")


def test_amount_in_words_uses_indian_numbering():
    assert (
        invoice_service.amount_in_words(118000.50)
        == "Rupees One Lakh Eighteen Thousand and Fifty Paise Only"
    )
    assert invoice_service.amount_in_words(10_000_000) == "Rupees One Crore Only"
    assert invoice_service.amount_in_words(0) == "Zero"


def test_invoice_pdf_renders_a_real_document_with_credit_notes():
    note = SimpleNamespace(
        credit_note_number="CN-2627-000001",
        created_at=datetime(2026, 5, 12, tzinfo=timezone.utc),
        taxable_inr_paise=50_000,
        tax_inr_paise=9_000,
    )
    pdf = invoice_service.render_invoice_pdf(_invoice(), [note])

    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1_000


# ---------------------------------------------------------------------------
# Crediting, failed payments and refunds
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar_one(self):
        return self.value

    def one(self):
        return self.value if isinstance(self.value, tuple) else (self.value,) * 5


class _CreditSession:
    def __init__(self, order, wallet):
        self.order = order
        self.wallet = wallet
        self.added = []
        self.commits = 0
        self.get_models = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def get(self, model, ident, **_kwargs):
        self.get_models.append(model)
        if model is RazorpayOrder:
            return self.order
        if model is BillingWallet:
            return self.wallet
        if model is InvoiceSequence:
            return InvoiceSequence(kind=ident[0], fy=ident[1], last_number=0)
        return None

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1

    async def execute(self, _stmt):
        return _Result(None)


def _paid_order(tenant_id):
    return SimpleNamespace(
        tenant_id=tenant_id,
        status="created",
        currency="INR",
        amount_minor=118_000,
        gross_minor=118_000,
        taxable_minor=100_000,
        tax_minor=18_000,
        tax_rate_bps=1_800,
        tax_kind="cgst_sgst",
        place_of_supply="Telangana",
        place_of_supply_code=TELANGANA,
        sac_code="998413",
        buyer_snapshot=_buyer(),
        supplier_snapshot=tax_service.supplier_snapshot(_config()),
        amount_inr_paise=100_000,
        payment_id=None,
    )


def _payment(**overrides):
    payment = {
        "id": "pay_test",
        "order_id": "order_test",
        "status": "captured",
        "currency": "INR",
        "amount": 118_000,
        "method": "upi",
    }
    payment.update(overrides)
    return payment


@pytest.mark.asyncio
async def test_captured_payment_credits_taxable_value_and_issues_gst_invoice(monkeypatch):
    tenant_id = uuid.uuid4()
    order = _paid_order(tenant_id)
    wallet = SimpleNamespace(tenant_id=tenant_id, balance_cents=0, balance_inr_paise=5_000)

    session = _CreditSession(order, wallet)
    monkeypatch.setattr(razorpay_service, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(tax_service, "load_config", AsyncMock(return_value=_config()))
    monkeypatch.setattr("server.services.saas.activity_log.record_event", AsyncMock())

    result = await razorpay_service._credit_order_payment(
        "order_test", "pay_test", _payment(), source="checkout"
    )

    invoice = next(item for item in session.added if isinstance(item, BillingInvoice))
    transaction = next(item for item in session.added if isinstance(item, BillingWalletTransaction))

    assert order.status == "paid"
    assert wallet.balance_inr_paise == 105_000  # 5000 existing + 100000 taxable credit
    assert invoice.amount_minor == 118_000
    assert invoice.taxable_inr_paise == 100_000
    assert invoice.tax_inr_paise == 18_000
    assert invoice.cgst_inr_paise == 9_000
    assert invoice.sgst_inr_paise == 9_000
    assert invoice.tax_kind == "cgst_sgst"
    assert invoice.status == "paid"
    assert invoice.invoice_number.startswith("INV-")
    assert transaction.amount_inr_paise == 100_000
    assert transaction.reference_id == "razorpay:pay_test"
    assert result["creditedInr"] == 1000.0
    assert result["taxKind"] == "cgst_sgst"


@pytest.mark.asyncio
async def test_captured_payment_that_underpays_the_gst_gross_is_rejected(monkeypatch):
    tenant_id = uuid.uuid4()
    order = _paid_order(tenant_id)
    wallet = SimpleNamespace(tenant_id=tenant_id, balance_cents=0, balance_inr_paise=0)

    session = _CreditSession(order, wallet)
    monkeypatch.setattr(razorpay_service, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(tax_service, "load_config", AsyncMock(return_value=_config()))

    # The taxable value alone must never be accepted for a GST-inclusive order.
    with pytest.raises(ValueError, match="payment_amount_mismatch"):
        await razorpay_service._credit_order_payment(
            "order_test", "pay_test", _payment(amount=100_000), source="checkout"
        )

    assert order.status == "created"
    assert wallet.balance_inr_paise == 0
    assert session.commits == 0


@pytest.mark.asyncio
async def test_failed_payment_marks_the_order_and_never_touches_the_wallet(monkeypatch):
    tenant_id = uuid.uuid4()
    order = SimpleNamespace(
        tenant_id=tenant_id,
        status="created",
        payment_id=None,
        failure_code=None,
        failure_reason=None,
    )

    class FakeSession(_CreditSession):
        async def get(self, model, ident, **_kwargs):
            self.get_models.append(model)
            if model is RazorpayOrder:
                return order
            return None

    session = FakeSession(order, None)
    monkeypatch.setattr(razorpay_service, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr("server.services.saas.activity_log.record_event", AsyncMock())

    await razorpay_service.mark_order_failed(
        {
            "id": "pay_failed",
            "order_id": "order_test",
            "status": "failed",
            "error": {"code": "BAD_REQUEST_ERROR", "description": "Card declined"},
        }
    )

    assert order.status == "failed"
    assert order.failure_code == "BAD_REQUEST_ERROR"
    assert order.failure_reason == "Card declined"
    assert order.payment_id == "pay_failed"
    assert BillingWallet not in session.get_models
    assert session.commits == 1


@pytest.mark.asyncio
async def test_failed_payment_never_downgrades_an_already_paid_order(monkeypatch):
    tenant_id = uuid.uuid4()
    order = SimpleNamespace(tenant_id=tenant_id, status="paid", payment_id="pay_ok")

    class FakeSession(_CreditSession):
        async def get(self, model, ident, **_kwargs):
            self.get_models.append(model)
            return order if model is RazorpayOrder else None

    session = FakeSession(order, None)
    monkeypatch.setattr(razorpay_service, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr("server.services.saas.activity_log.record_event", AsyncMock())

    await razorpay_service.mark_order_failed(
        {"id": "pay_late", "order_id": "order_test", "status": "failed"}
    )

    assert order.status == "paid"
    assert order.payment_id == "pay_ok"
    assert session.commits == 0


class _RefundSession:
    def __init__(self, invoice, order, wallet, existing_refund=None):
        self.invoice = invoice
        self.order = order
        self.wallet = wallet
        self.existing_refund = existing_refund
        self.added = []
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def get(self, model, ident, **_kwargs):
        if model is RazorpayRefund:
            return self.existing_refund
        if model is BillingWallet:
            return self.wallet
        if model is RazorpayOrder:
            return self.order
        if model is InvoiceSequence:
            return InvoiceSequence(kind=ident[0], fy=ident[1], last_number=0)
        return None

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1

    async def execute(self, stmt):
        entity = stmt.column_descriptions[0].get("entity")
        if entity is BillingInvoice:
            return _Result(self.invoice)
        return _Result(0)


@pytest.mark.asyncio
async def test_partial_refund_reverses_its_share_and_issues_a_credit_note(monkeypatch):
    invoice = _invoice()
    order = SimpleNamespace(status="paid")
    wallet = SimpleNamespace(balance_inr_paise=100_000)

    session = _RefundSession(invoice, order, wallet)
    monkeypatch.setattr(razorpay_service, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(tax_service, "load_config", AsyncMock(return_value=_config()))
    monkeypatch.setattr("server.services.saas.activity_log.record_event", AsyncMock())

    result = await razorpay_service.apply_refund(
        refund_id="rfnd_test",
        payment_id="pay_test",
        amount_minor=59_000,  # half of the 1180.00 gross
        currency="INR",
        reason="Customer cancelled",
        created_by=None,
    )

    note = next(item for item in session.added if isinstance(item, CreditNote))
    transaction = next(item for item in session.added if isinstance(item, BillingWalletTransaction))

    assert wallet.balance_inr_paise == 50_000
    assert invoice.status == "partially_refunded"
    assert order.status == "partially_refunded"
    assert note.gross_inr_paise == 59_000
    assert note.taxable_inr_paise == 50_000
    assert note.tax_inr_paise == 9_000
    assert note.cgst_inr_paise + note.sgst_inr_paise == 9_000
    assert note.credit_note_number.startswith("CN-")
    assert transaction.amount_inr_paise == -50_000
    assert result["walletReversalInr"] == 500.0
    assert result["taxReversalInr"] == 90.0


@pytest.mark.asyncio
async def test_pending_refund_is_recorded_without_moving_money(monkeypatch):
    invoice = _invoice()
    order = SimpleNamespace(status="paid")
    wallet = SimpleNamespace(balance_inr_paise=100_000)

    session = _RefundSession(invoice, order, wallet)
    monkeypatch.setattr(razorpay_service, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(tax_service, "load_config", AsyncMock(return_value=_config()))
    monkeypatch.setattr("server.services.saas.activity_log.record_event", AsyncMock())

    result = await razorpay_service.apply_refund(
        refund_id="rfnd_pending",
        payment_id="pay_test",
        amount_minor=59_000,
        currency="INR",
        reason="Refund initiated",
        created_by="admin@dialtact.com",
        status="pending",
    )

    refund = next(item for item in session.added if isinstance(item, RazorpayRefund))

    assert refund.status == "pending"
    assert wallet.balance_inr_paise == 100_000
    assert invoice.status == "paid"
    assert not [item for item in session.added if isinstance(item, CreditNote)]
    assert result["pending"] is True
    assert result["walletReversalInr"] == 0.0


@pytest.mark.asyncio
async def test_duplicate_processed_refund_is_idempotent(monkeypatch):
    invoice = _invoice()
    existing = SimpleNamespace(
        refund_id="rfnd_test",
        status="processed",
        amount_minor=59_000,
        credit_inr_paise=50_000,
        tax_inr_paise=9_000,
    )

    session = _RefundSession(invoice, SimpleNamespace(status="paid"), SimpleNamespace(balance_inr_paise=100_000), existing)
    monkeypatch.setattr(razorpay_service, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(tax_service, "load_config", AsyncMock(return_value=_config()))
    monkeypatch.setattr("server.services.saas.activity_log.record_event", AsyncMock())

    result = await razorpay_service.apply_refund(
        refund_id="rfnd_test",
        payment_id="pay_test",
        amount_minor=59_000,
        currency="INR",
        reason="Retry delivery",
        created_by=None,
        status="processed",
    )

    assert result["duplicate"] is True
    assert session.commits == 0
    assert not session.added


# ---------------------------------------------------------------------------
# Tenant isolation and profile validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invoice_lookup_is_scoped_to_the_requesting_tenant(monkeypatch):
    invoice = _invoice()
    other_tenant = uuid.uuid4()

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, model, ident, **_kwargs):
            return invoice if model is BillingInvoice else None

        async def execute(self, _stmt):
            return _Result([])

    monkeypatch.setattr(razorpay_service, "get_session_factory", lambda: lambda: FakeSession())

    found, notes = await razorpay_service.get_invoice(other_tenant, invoice.invoice_id)

    assert found is None
    assert notes == []


@pytest.mark.asyncio
async def test_billing_profile_rejects_gstin_that_does_not_match_the_state(monkeypatch):
    monkeypatch.setattr(billing_profile_service, "get_session_factory", lambda: lambda: None)

    with pytest.raises(ValueError, match="gstin_state_mismatch"):
        await billing_profile_service.update_profile(
            uuid.uuid4(),
            {
                "legalName": "Acme Callers",
                "gstin": VALID_MAHARASHTRA_GSTIN,
                "stateCode": TELANGANA,
                "countryCode": "IN",
                "customerType": "business",
            },
        )


@pytest.mark.asyncio
async def test_billing_profile_rejects_a_bad_gstin_before_persisting(monkeypatch):
    monkeypatch.setattr(billing_profile_service, "get_session_factory", lambda: lambda: None)

    with pytest.raises(ValueError, match="gstin_invalid_checksum"):
        await billing_profile_service.update_profile(
            uuid.uuid4(),
            {
                "legalName": "Acme Callers",
                "gstin": "27AAPFU0939F1ZX",
                "countryCode": "IN",
                "customerType": "business",
            },
        )
