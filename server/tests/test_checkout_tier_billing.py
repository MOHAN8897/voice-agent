import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.db.models.saas_models import BillingInvoice
from server.services.saas import razorpay_service, tax_service, voice_stack_profiles
from server.tests.test_billing_gst_invoices import (
    _buyer,
    _config,
    _CreditSession,
    _paid_order,
    _payment,
)


def test_payment_currency_does_not_make_an_indian_customer_an_export():
    quote = tax_service.compute_tax(100, "USD", fx_rate_inr=100, config=_config(), buyer=_buyer())
    assert quote["taxMinor"] == 1800 and quote["totalMinor"] == 11800
    assert quote["creditInrPaise"] == 1000000
    assert quote["taxKind"] == "cgst_sgst"
    assert quote["cgst"] == 9 and quote["sgst"] == 9


def test_export_policy_off_charges_igst_even_in_foreign_currency():
    quote = tax_service.compute_tax(100, "USD", fx_rate_inr=100,
        config=_config(exportZeroRated=False), buyer=_buyer(country="US"))
    assert quote["taxKind"] == "igst" and quote["tax"] == 18
    assert quote["placeOfSupplyCode"] == "US"


def test_tax_rounding_is_half_up_and_wallet_excludes_tax():
    quote = tax_service.compute_tax(1, "INR", fx_rate_inr=100,
        config=_config(defaultRateBps=50), buyer=_buyer())
    assert quote["taxMinor"] == 1 and quote["totalMinor"] == 101


@pytest.mark.parametrize("currency,international,base_amount", [("INR", True, 118000), ("USD", True, 118000)])
async def test_international_settlement_does_not_credit_gst(monkeypatch, currency, international, base_amount):
    tenant = uuid.uuid4()
    order = _paid_order(tenant)
    order.currency = currency
    wallet = SimpleNamespace(tenant_id=tenant, balance_cents=0, balance_inr_paise=0)
    session = _CreditSession(order, wallet)
    monkeypatch.setattr(razorpay_service, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(tax_service, "load_config", AsyncMock(return_value=_config()))
    monkeypatch.setattr("server.services.saas.activity_log.record_event", AsyncMock())
    result = await razorpay_service._credit_order_payment("order_test", "pay_test",
        _payment(currency=currency, international=international, base_amount=base_amount), source="checkout")
    invoice = next(item for item in session.added if isinstance(item, BillingInvoice))
    assert result["creditedInr"] == 1000
    assert wallet.balance_inr_paise == 100000 and invoice.tax_inr_paise == 18000


async def test_changed_quote_never_creates_provider_order(monkeypatch):
    monkeypatch.setattr(razorpay_service, "quote_wallet_topup", AsyncMock(return_value={
        "quote": {"totalMinor": 11800}, "taxConfig": {}, "buyer": {}, "currency": "INR", "ceiling": 500000}))
    client = AsyncMock()
    monkeypatch.setattr(razorpay_service, "_client", client)
    with pytest.raises(ValueError, match="quote_changed"):
        await razorpay_service.create_wallet_order(uuid.uuid4(), 100, expected_total_minor=11000)
    client.assert_not_called()


async def test_checkout_tax_read_fails_closed_on_missing_store(monkeypatch):
    monkeypatch.setattr(tax_service, "get_session_factory", lambda: None)
    with pytest.raises(ValueError, match="tax_configuration_unavailable"):
        await tax_service.load_config(strict=True)


def test_web_rate_is_exact_profile_and_independent_of_pstn():
    rates = {"fx_rate_inr": 100, "version": 2, "web_agent_rate_usd_micros_per_min": 50000,
        "web_agent_rate_inr_paise_per_min": 500}
    first = {"revision": 7, "profile": {"retailRateInr": 15, "webRetailRateInr": 3}}
    second = {"revision": 8, "profile": {"retailRateInr": 15, "webRetailRateInr": 6}}
    assert voice_stack_profiles._web_tier_retail_rate(rates, "custom_one", first)["inrPaisePerMin"] == 300
    assert voice_stack_profiles._web_tier_retail_rate(rates, "custom_two", second)["inrPaisePerMin"] == 600
    assert voice_stack_profiles._native_tier_retail_rate(rates, "custom_one", first)["inrPaisePerMin"] == 1500
    assert voice_stack_profiles._web_tier_retail_rate(rates, "medium", {})["inrPaisePerMin"] == 500


async def test_gst_preview_prices_draft_without_saving_and_rejects_tenant_role(monkeypatch):
    import httpx
    from fastapi import FastAPI

    from server.routes import dev_admin
    from server.services.saas import billing_rates
    monkeypatch.setattr(billing_rates, "load_current_rates", AsyncMock(return_value={"fx_rate_inr": 100}))
    save = AsyncMock()
    monkeypatch.setattr(tax_service, "save_config", save)
    app = FastAPI()
    app.include_router(dev_admin.router)
    app.dependency_overrides[dev_admin.require_dev_session] = lambda: SimpleNamespace(role="developer", kind="dev", subject="fixture")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/dev/admin/payments/tax-preview", json={"settings": _config(), "amount": 100,
            "currency": "USD", "buyerCountry": "IN", "buyerState": "36"})
        assert response.status_code == 200 and response.json()["total"] == 118
        app.dependency_overrides[dev_admin.require_dev_session] = lambda: SimpleNamespace(role="customer_admin", kind="app", subject="fixture")
        assert (await client.post("/api/dev/admin/payments/tax-preview", json={"settings": _config()})).status_code == 403
    save.assert_not_awaited()


async def test_billing_catalog_renders_without_creating_an_order(monkeypatch):
    from server.routes import app_billing
    from server.services.saas import billing_rates
    rates = {"fx_rate_inr": 100, "did_monthly_usd_cents": 100, "did_monthly_usd_micros": 1000000,
        "did_monthly_inr_paise": 10000, "pstn_rate_usd_micros_per_min": 100000,
        "pstn_rate_inr_paise_per_min": 1000, "web_agent_rate_usd_micros_per_min": 50000,
        "web_agent_rate_inr_paise_per_min": 500}
    monkeypatch.setattr(billing_rates, "load_current_rates", AsyncMock(return_value=rates))
    monkeypatch.setattr(tax_service, "load_config", AsyncMock(return_value=_config()))
    result = await app_billing.billing_catalog()
    assert result["rates"]["webInrPerMin"] == 5
