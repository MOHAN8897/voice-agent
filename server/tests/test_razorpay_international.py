"""Currency correctness for international Razorpay top-ups.

These guard the two things that silently overcharge a customer: a currency's
subunit (JPY has no decimal, so a naive *100 bills 100x) and the INR credit
derived from it.
"""
from __future__ import annotations

import uuid

import pytest

from server.services.saas import payment_settings, razorpay_service as rzp


@pytest.fixture(autouse=True)
def _intl_on(monkeypatch):
    """International enabled, so the currency logic is actually exercised."""
    monkeypatch.setattr(payment_settings, "is_international_enabled", lambda: True)
    monkeypatch.setattr(payment_settings, "charge_currency", lambda: "USD")


def test_zero_decimal_currency_is_not_scaled_by_100():
    # ¥100 is 100 minor units, not 10000. Getting this wrong bills 100x.
    assert rzp.CURRENCY_SUBUNITS["JPY"] == 1
    assert rzp.to_minor(100, "JPY") == 100
    assert rzp.from_minor(100, "JPY") == 100.0


def test_two_decimal_currency_scales_by_100():
    assert rzp.to_minor(25, "USD") == 2500
    assert rzp.from_minor(2500, "USD") == 25.0


def test_round_trip_preserves_the_amount():
    # Only two-decimal currencies can represent cents; zero-decimal ones floor.
    for code in ("USD", "EUR", "GBP", "AED"):
        assert rzp.from_minor(rzp.to_minor(12.34, code), code) == pytest.approx(12.34, abs=0.01)


def test_zero_decimal_round_trip_truncates_to_whole_units():
    """JPY has no subunit, so the round trip floors — never invents fractional yen."""
    assert rzp.from_minor(rzp.to_minor(1234, "JPY"), "JPY") == 1234.0


def test_international_off_forces_inr(monkeypatch):
    """An unapproved account would decline the card, so never create a foreign order."""
    monkeypatch.setattr(payment_settings, "is_international_enabled", lambda: False)
    assert rzp.normalize_currency("USD") == "INR"


def test_unknown_currency_falls_back_to_inr():
    assert rzp.normalize_currency("XYZ") == "INR"
    assert rzp.normalize_currency(None) == "USD"  # configured default


def test_inr_credit_uses_the_admin_charge_rate(monkeypatch):
    monkeypatch.setattr(
        "server.services.saas.billing_rates.effective_rates",
        lambda: {"fx_rate_inr": 95.64},
    )
    # $25 -> ₹2391 at 95.64. Not a live quote, so a price cannot drift mid-payment.
    assert rzp.inr_credit_for("USD", 2500) == 239100


def test_inr_credit_is_identity_for_domestic():
    assert rzp.inr_credit_for("INR", 50000) == 50000


def test_minimum_is_enforced_per_currency():
    from server.services.saas.razorpay_service import MIN_CHARGE

    assert MIN_CHARGE["INR"] == 100.0
    assert MIN_CHARGE["USD"] == 1.0
    assert MIN_CHARGE["JPY"] == 100.0


def test_signature_verification_rejects_a_forged_signature(monkeypatch):
    monkeypatch.setattr(rzp, "get_settings", lambda: type("S", (), {"razorpay_api_secret": "s3cr3t"})())
    import hashlib
    import hmac

    order_id, payment_id = "order_1", "pay_1"
    good = hmac.new(b"s3cr3t", f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()
    assert rzp.verify_payment_signature(order_id, payment_id, good) is True
    assert rzp.verify_payment_signature(order_id, payment_id, "deadbeef") is False


def test_payment_settings_masks_the_key_id():
    assert payment_settings._mask("") == ""
    assert payment_settings._mask("short") == "••••••••"
    masked = payment_settings._mask("rzp_test_abcdefghijklmnop")
    assert masked.startswith("rzp_te") and masked.endswith("mnop")
    assert "abcdefghij" not in masked


def test_settings_state_reports_upi_only_for_inr():
    state = payment_settings.settings_state()
    assert state["settlesIn"] == "INR"
    # With international on and USD selected, UPI must not be advertised.
    assert state["supportsUpi"] is False