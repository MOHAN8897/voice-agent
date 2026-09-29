"""Number purchase: what is charged, and what is refused before any money moves."""
from __future__ import annotations

import pytest

from server.config.env import get_settings
from server.services.saas.number_purchase_service import E164_RE, normalize_e164


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+14155552671", "+14155552671"),
        ("+1 415 555 2671", "+14155552671"),
        ("+1-415-555-2671", "+14155552671"),
        ("0091 99999 99999", "+919999999999"),
        ("9999999999", "+919999999999"),
        ("  +919999999999  ", "+919999999999"),
        # Punctuation is stripped rather than refused — only the digits matter.
        ("++1 415 555 2671", "+14155552671"),
    ],
)
def test_accepts_the_forms_humans_type(raw, expected):
    assert normalize_e164(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        None,
        "abc",
        "+0123456789",  # country code may not start with 0
        "+1234567",  # 7 digits is too short
        "+" + "1" * 16,  # 16 digits is too long
        "0",
    ],
)
def test_rejects_anything_that_is_not_strict_e164(raw):
    """A number is charged for and sent to the carrier, so validate before paying."""
    with pytest.raises(ValueError) as exc:
        normalize_e164(raw)
    assert str(exc.value) == "invalid_e164"


def test_regex_agrees_with_the_validator():
    assert E164_RE.match("+14155552671")
    assert not E164_RE.match("+01234552671")


def test_number_costs_four_dollars():
    """The price the console shows must be the price that is charged."""
    assert get_settings().did_monthly_usd_cents == 400


def test_stripe_checkout_uses_the_same_price():
    """The card path and the wallet path must not disagree about the amount."""
    import inspect

    from server.services.saas import number_purchase_service as svc

    source = inspect.getsource(svc.create_purchase_checkout)
    # A hard-coded 500 would silently charge $5 while the console says $4.
    assert "unit_amount\": 500" not in source
    assert "settings.did_monthly_usd_cents" in source
