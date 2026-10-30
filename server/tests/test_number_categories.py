"""Catalog number categories (mobile / landline / toll-free / other) and filters."""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from server.routes import app_telephony
from server.services.saas.number_categories import (
    classify_number,
    matches_area,
    normalize_category,
    number_requirements,
    provider_search_hint,
)
from server.services.saas.tenant_guard import SubscriberPrincipal
from server.tests.test_vobiz_number_catalog import _configure_catalog_route


# Row shapes as Vobiz's inventory returns them (region is free text, no type field).
BENGALURU = {"e164": "+918064269814", "country": "IN", "region": "Karnataka", "status": "active", "auth_id": None,
             "setup_fee": 100, "monthly_fee": 500, "currency": "INR", "aadhaar_verification_required": False}
AHMEDABAD = {"e164": "+917965481844", "country": "IN", "region": "Gujarat", "status": "active", "auth_id": None,
             "setup_fee": 100, "monthly_fee": 600, "currency": "INR", "aadhaar_verification_required": False}
SERIES_92 = {"e164": "+919240954115", "country": "IN", "region": "92 Series", "status": "active", "auth_id": None,
             "setup_fee": 100, "monthly_fee": 1000, "currency": "INR", "aadhaar_verification_required": True}
TOLL_FREE = {"e164": "+9118001234567", "country": "IN", "region": "", "status": "active", "auth_id": None}


@pytest.mark.parametrize(
    "row, category, std, city",
    [
        (BENGALURU, "landline", "080", "Bengaluru"),
        (AHMEDABAD, "landline", "079", "Ahmedabad"),
        (SERIES_92, "mobile", "", ""),
        (TOLL_FREE, "toll_free", "", ""),
        ({"e164": "+912240001234", "country": "IN", "region": "Maharashtra"}, "landline", "022", "Mumbai"),
        ({"e164": "+911141234567", "country": "IN", "region": ""}, "landline", "011", "Delhi"),
        ({"e164": "+918050123456", "country": "IN", "region": ""}, "mobile", "", ""),  # 80xx mobile range
        ({"e164": "+919876543210", "country": "IN", "region": ""}, "mobile", "", ""),
        ({"e164": "+911400123456", "country": "IN", "region": ""}, "other", "", ""),
        ({"e164": "+911600123456", "country": "IN", "region": ""}, "other", "", ""),
        ({"e164": "+911860123456", "country": "IN", "region": ""}, "other", "", ""),
        ({"e164": "+18885550100", "country": "US", "region": ""}, "toll_free", "", ""),
        ({"e164": "+14155550100", "country": "US", "region": "CA"}, "other", "", ""),
    ],
)
def test_classify_number(row, category, std, city):
    info = classify_number(row["e164"], country=row["country"], region=row["region"])
    assert info["category"] == category
    assert info["stdCode"] == std
    assert info["city"] == city
    assert info["categoryLabel"] in {"Mobile", "Landline", "Toll-free", "Other"}


def test_landline_area_label_names_city_and_std_code():
    info = classify_number(BENGALURU["e164"], country="IN", region="Karnataka")
    assert info["areaLabel"] == "Bengaluru (STD 080)"
    assert info["state"] == "Karnataka"


def test_unknown_std_code_keeps_carrier_region_instead_of_inventing_a_city():
    info = classify_number("+913592123456", country="IN", region="Sikkim")
    assert info["category"] == "landline"
    assert info["city"] == ""
    assert info["areaLabel"] == "Sikkim"


def test_requirements_come_only_from_documented_fields():
    assert number_requirements(BENGALURU) == []
    assert any("Aadhaar" in r for r in number_requirements(SERIES_92))
    assert any("3 months" in r for r in number_requirements({"minimum_commitment_months": 3}))


@pytest.mark.parametrize("raw, expected", [(None, None), ("all", None), ("Landline", "landline"),
                                           ("toll-free", "toll_free"), ("tollfree", "toll_free"), ("mobile", "mobile")])
def test_normalize_category(raw, expected):
    assert normalize_category(raw) == expected


def test_normalize_category_rejects_unknown():
    with pytest.raises(ValueError):
        normalize_category("premium")


def test_area_filter_matches_city_state_and_std_code():
    info = classify_number(BENGALURU["e164"], country="IN", region="Karnataka")
    for needle in ("080", "80", "Bengaluru", "bengaluru", "Karnataka", "8064"):
        assert matches_area(BENGALURU, info, needle), needle
    for needle in ("079", "Ahmedabad", "Gujarat"):
        assert not matches_area(BENGALURU, info, needle), needle


def test_provider_search_hint_uses_number_digits_only():
    assert provider_search_hint("landline", "080", "IN") == "9180"
    assert provider_search_hint(None, "Bengaluru", "IN") == "9180"
    assert provider_search_hint("toll_free", None, "IN") == "911800"
    assert provider_search_hint("mobile", None, "IN") is None
    assert provider_search_hint("landline", "080", "US") is None


def _principal():
    return SubscriberPrincipal(uuid.uuid4(), uuid.uuid4(), "owner", "buyer@example.test")


def _rent_covers_inventory(monkeypatch):
    """Rent above every fixture's carrier price (setup + monthly, up to ₹1,100).

    Numbers whose carrier price exceeds the rent are hidden from the catalog
    (they cannot be sold); these tests are about categories, not pricing.
    """
    async def rates():
        return {"did_monthly_usd_cents": 1300, "did_monthly_inr_paise": 120000}

    monkeypatch.setattr("server.services.saas.billing_rates.load_current_rates", rates)


@pytest.mark.asyncio
async def test_catalog_returns_category_and_area_and_hides_carrier_cost(monkeypatch):
    async def provider_search(_client, *, country, limit):
        assert (country, limit) == ("IN", 100)
        return [dict(BENGALURU), dict(SERIES_92), dict(TOLL_FREE)]

    _configure_catalog_route(monkeypatch, search=provider_search)
    _rent_covers_inventory(monkeypatch)
    result = await app_telephony.search_numbers(country="IN", principal=_principal())

    rows = {row["e164"]: row for row in result["numbers"]}
    assert rows[BENGALURU["e164"]]["category"] == "landline"
    assert rows[BENGALURU["e164"]]["areaLabel"] == "Bengaluru (STD 080)"
    assert rows[SERIES_92["e164"]]["category"] == "mobile"
    assert rows[SERIES_92["e164"]]["requirements"]
    assert rows[TOLL_FREE["e164"]]["category"] == "toll_free"
    assert result["category"] == "all"
    for row in result["numbers"]:
        # Tenant price is the platform rent; the carrier's cost stays internal.
        assert row["monthlyInr"] == 1200.0
        assert not {"setup_fee", "monthly_fee", "release_fee", "currency"}.intersection(row)


@pytest.mark.asyncio
async def test_catalog_filters_by_category_and_area(monkeypatch):
    calls = []

    async def provider_search(_client, *, country, limit, search=None):
        calls.append((country, limit, search))
        return [dict(BENGALURU), dict(AHMEDABAD), dict(SERIES_92), dict(TOLL_FREE)]

    _configure_catalog_route(monkeypatch, search=provider_search)
    _rent_covers_inventory(monkeypatch)

    landlines = await app_telephony.search_numbers(country="IN", category="landline", principal=_principal())
    assert {r["e164"] for r in landlines["numbers"]} == {BENGALURU["e164"], AHMEDABAD["e164"]}
    assert landlines["category"] == "landline"

    bengaluru = await app_telephony.search_numbers(country="IN", category="landline", area="080", principal=_principal())
    assert [r["e164"] for r in bengaluru["numbers"]] == [BENGALURU["e164"]]

    mobiles = await app_telephony.search_numbers(country="IN", category="mobile", principal=_principal())
    assert [r["e164"] for r in mobiles["numbers"]] == [SERIES_92["e164"]]

    toll = await app_telephony.search_numbers(country="IN", category="toll-free", principal=_principal())
    assert [r["e164"] for r in toll["numbers"]] == [TOLL_FREE["e164"]]

    assert calls == [("IN", 300, None), ("IN", 300, "9180"), ("IN", 300, None), ("IN", 300, "911800")]


@pytest.mark.asyncio
async def test_catalog_rejects_unknown_category(monkeypatch):
    async def provider_search(_client, **_kwargs):
        raise AssertionError("must not reach the carrier")

    _configure_catalog_route(monkeypatch, search=provider_search)
    with pytest.raises(HTTPException) as caught:
        await app_telephony.search_numbers(country="IN", category="premium", principal=_principal())
    assert caught.value.status_code == 422
