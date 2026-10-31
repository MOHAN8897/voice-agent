"""Tier merchandising: validation, public catalog exposure, admin authorization."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from server.services.saas import pricing_merchandising as merchandising


def _tiers(**overrides):
    base = {
        "low": {"tags": [{"label": "Best value", "tone": "success"}], "featured": True, "visible": True},
        "medium": {"tags": [], "featured": False, "visible": True},
        "premium": {"tags": [], "featured": False, "visible": True},
    }
    base.update(overrides)
    return base


def test_validate_accepts_clean_tags_and_featured():
    cleaned = merchandising.validate_merchandising(_tiers())
    assert cleaned["low"] == {
        "tags": [{"label": "Best value", "tone": "success"}],
        "featured": True,
        "visible": True,
    }
    assert cleaned["medium"] == {"tags": [], "featured": False, "visible": True}


def test_validate_defaults_missing_tiers_but_keeps_them_visible():
    cleaned = merchandising.validate_merchandising({})
    assert set(cleaned) == {"low", "medium", "premium"}
    assert all(entry["visible"] and not entry["featured"] and entry["tags"] == [] for entry in cleaned.values())


def test_validate_rejects_too_many_tags_and_long_labels():
    with pytest.raises(merchandising.MerchandisingError, match="at most 3"):
        merchandising.validate_merchandising(
            {"low": {"tags": [{"label": f"Tag {i}"} for i in range(4)]}}
        )
    with pytest.raises(merchandising.MerchandisingError, match="32 characters"):
        merchandising.validate_merchandising({"low": {"tags": [{"label": "x" * 33}]}})


def test_validate_rejects_vendor_names_links_and_control_characters():
    for label in ("Vobiz deal", "Powered by telnyx", "https://example.com", "bad\x07tag"):
        with pytest.raises(merchandising.MerchandisingError):
            merchandising.validate_merchandising({"low": {"tags": [{"label": label}]}})


def test_validate_rejects_duplicates_bad_tones_and_unknown_fields():
    with pytest.raises(merchandising.MerchandisingError, match="repeated"):
        merchandising.validate_merchandising(
            {"low": {"tags": [{"label": "Most chosen"}, {"label": "most chosen"}]}}
        )
    with pytest.raises(merchandising.MerchandisingError, match="style"):
        merchandising.validate_merchandising({"low": {"tags": [{"label": "Hot", "tone": "danger"}]}})
    with pytest.raises(merchandising.MerchandisingError):
        merchandising.validate_merchandising({"low": {"tag": "Most chosen"}})


def test_validate_rejects_unknown_tiers_and_multiple_featured():
    with pytest.raises(merchandising.MerchandisingError, match="configured in the voice stack"):
        merchandising.validate_merchandising({"enterprise": {"tags": []}})
    with pytest.raises(merchandising.MerchandisingError, match="one tier"):
        merchandising.validate_merchandising(_tiers(medium={"featured": True}))
    with pytest.raises(merchandising.MerchandisingError, match="hidden tier"):
        merchandising.validate_merchandising(
            {"low": {"featured": True, "visible": False}}
        )


def test_validate_accepts_operator_created_tiers():
    cleaned = merchandising.validate_merchandising(
        {
            "low": {"tags": [{"label": "Most chosen", "tone": "accent"}]},
            "medium_copy_1": {"tags": [{"label": "New stack"}], "featured": True},
        },
        allowed_tiers=("low", "medium_copy_1"),
    )
    assert set(cleaned) == {"low", "medium_copy_1"}
    assert cleaned["medium_copy_1"]["featured"] is True
    assert cleaned["medium_copy_1"]["tags"] == [{"label": "New stack", "tone": "neutral"}]


def test_validate_rejects_tiers_outside_the_configured_set():
    with pytest.raises(merchandising.MerchandisingError, match="configured in the voice stack"):
        merchandising.validate_merchandising(
            {"premium": {"tags": []}}, allowed_tiers=("low", "medium_copy_1")
        )


def test_featured_style_defaults_to_graphite_and_rejects_unknown_names():
    assert merchandising.default_merchandising()["featuredStyle"] == "graphite"
    for style in merchandising.FEATURED_STYLES:
        assert merchandising.validate_featured_style(style) == style
    for raw in ("neon", "", 3, ["ivory"]):
        with pytest.raises(merchandising.MerchandisingError) as exc:
            merchandising.validate_featured_style(raw)
        assert exc.value.code == "invalid_featured_style"
        assert exc.value.status_code == 422


def test_stored_rows_without_a_style_use_the_default():
    row = SimpleNamespace(payload={"tiers": {}}, version=2, created_at=None)
    assert merchandising._from_row(row)["featuredStyle"] == "graphite"
    row_with_style = SimpleNamespace(payload={"tiers": {}, "featuredStyle": "forest"}, version=3, created_at=None)
    assert merchandising._from_row(row_with_style)["featuredStyle"] == "forest"
    stale_style = SimpleNamespace(payload={"tiers": {}, "featuredStyle": "neon"}, version=4, created_at=None)
    assert merchandising._from_row(stale_style)["featuredStyle"] == "graphite"


def test_calculator_switches_default_on_and_require_booleans():
    assert merchandising.default_merchandising()["calculator"] == {
        "allowMinuteInput": True,
        "compareTiers": True,
        "shareableEstimate": True,
        "showGstToggle": True,
    }
    cleaned = merchandising.validate_calculator({"compareTiers": False, "showGstToggle": False})
    assert cleaned["compareTiers"] is False
    assert cleaned["showGstToggle"] is False
    assert cleaned["allowMinuteInput"] is True
    for raw in ({"compareTiers": "no"}, {"unknownToggle": True}, ["compareTiers"]):
        with pytest.raises(merchandising.MerchandisingError) as exc:
            merchandising.validate_calculator(raw)
        assert exc.value.code == "invalid_calculator"
        assert exc.value.status_code == 422


def test_stored_rows_without_calculator_switches_use_enabled_defaults():
    row = SimpleNamespace(payload={"tiers": {}, "calculator": {"compareTiers": False}}, version=2, created_at=None)
    view = merchandising._from_row(row)
    assert view["calculator"]["compareTiers"] is False
    assert view["calculator"]["allowMinuteInput"] is True

    stale = SimpleNamespace(
        payload={"tiers": {}, "calculator": {"compareTiers": "off", "shareableEstimate": False}},
        version=3,
        created_at=None,
    )
    tolerance = merchandising._from_row(stale)
    assert tolerance["calculator"]["compareTiers"] is True
    assert tolerance["calculator"]["shareableEstimate"] is False


async def test_save_rejects_unknown_featured_style_before_touching_storage(monkeypatch):
    monkeypatch.setattr(merchandising, "get_session_factory", lambda: None)
    with pytest.raises(merchandising.MerchandisingError) as exc:
        await merchandising.save_tier_merchandising(
            tiers=_tiers(), expected_version=0, actor="admin", featured_style="neon"
        )
    assert exc.value.code == "invalid_featured_style"


async def test_load_without_database_returns_neutral_defaults(monkeypatch):
    monkeypatch.setattr(merchandising, "get_session_factory", lambda: None)
    view = await merchandising.load_tier_merchandising(force=True)
    assert view["version"] == 0
    assert view["tiers"]["premium"] == {"tags": [], "featured": False, "visible": True}


async def test_save_requires_durable_store(monkeypatch):
    monkeypatch.setattr(merchandising, "get_session_factory", lambda: None)
    with pytest.raises(merchandising.MerchandisingError) as exc:
        await merchandising.save_tier_merchandising(tiers=_tiers(), expected_version=0, actor="admin")
    assert exc.value.code == "durable_store_unavailable"
    assert exc.value.status_code == 503


async def test_public_tax_summary_matches_the_saved_tax_settings(monkeypatch):
    from server.routes import app_billing
    from server.services.saas import tax_service

    config = {
        "enabled": True,
        "legalName": "Acme Voice Pvt Ltd",
        "addressLine1": "1 MG Road",
        "city": "Mumbai",
        "stateCode": "27",
        "gstin": "27AAPFU0939F1ZV",
        "countryCode": "IN",
        "defaultRateBps": 1800,
        "priceIncludesTax": False,
    }
    monkeypatch.setattr(tax_service, "load_config", AsyncMock(return_value=config))
    assert await app_billing._public_tax_summary() == {
        "enabled": True,
        "ratePercent": 18.0,
        "priceIncludesTax": False,
        "countryCode": "IN",
    }

    monkeypatch.setattr(
        tax_service,
        "load_config",
        AsyncMock(return_value={**config, "priceIncludesTax": True}),
    )
    assert (await app_billing._public_tax_summary())["priceIncludesTax"] is True

    # An enabled switch without the invoice identity never publishes GST: checkout
    # cannot charge it, so the calculator must not quote it either.
    monkeypatch.setattr(
        tax_service,
        "load_config",
        AsyncMock(return_value={**config, "legalName": ""}),
    )
    summary = await app_billing._public_tax_summary()
    assert summary["enabled"] is False
    assert summary["ratePercent"] == 18.0


async def test_public_catalog_exposes_tier_prices_tags_and_no_vendors(monkeypatch):
    from server.routes import app_billing
    from server.services.saas import billing_rates, tax_service, voice_stack_profiles

    rates = {
        "version": 9,
        "fx_rate_inr": 100,
        "pstn_rate_usd_cents_per_min": 10,
        "pstn_rate_usd_micros_per_min": 100_000,
        "pstn_rate_inr_paise_per_min": 1000,
        "web_agent_rate_usd_cents_per_min": 7,
        "web_agent_rate_usd_micros_per_min": 70_000,
        "web_agent_rate_inr_paise_per_min": 700,
        "did_monthly_usd_cents": 400,
        "did_monthly_usd_micros": 4_000_000,
        "did_monthly_inr_paise": 40_000,
        "pstn_low_rate_usd_micros_per_min": 50_000,
        "pstn_low_rate_inr_paise_per_min": 500,
        "pstn_medium_rate_usd_micros_per_min": 90_000,
        "pstn_medium_rate_inr_paise_per_min": 900,
        "pstn_premium_rate_usd_micros_per_min": 150_000,
        "pstn_premium_rate_inr_paise_per_min": 1500,
    }
    evidence = {
        "sarvamModelAccess": True,
        "sttVerified": True,
        "ttsCatalogVerified": True,
        "toolsVerified": True,
        "capacityVerified": True,
        "mediaFormatsVerified": True,
        "credentialRefConfigured": True,
    }
    records = {
        "low": {"revision": 3, "profile": {"enabled": True, "evidence": evidence, "retailRateInr": 6, "webRetailRateInr": 8}},
        "medium": {"revision": 2, "profile": {"enabled": True, "evidence": evidence}},
        # Operator-created stack: appears on the shelf while enabled and ready.
        "medium_copy_1": {
            "revision": 4,
            "profile": {"enabled": True, "label": "premium", "evidence": evidence, "retailRateInr": 6.5, "webRetailRateInr": 5.5},
        },
        # Enabled but never verified: the tenant catalog hides it, marketing must too.
        "medium_copy_2": {"revision": 1, "profile": {"enabled": True}},
        "premium": {"revision": 5, "profile": {"enabled": False}},
    }
    merch_view = {
        "version": 4,
        "featuredStyle": "forest",
        "updatedAt": "2026-10-28T00:00:00+00:00",
        "updatedBy": "admin",
        "calculator": {
            "allowMinuteInput": False,
            "compareTiers": True,
            "shareableEstimate": False,
            "showGstToggle": True,
        },
        "tiers": {
            "low": {"tags": [{"label": "Best value", "tone": "success"}], "featured": True, "visible": True},
            "medium": {"tags": [], "featured": False, "visible": True},
            "medium_copy_1": {"tags": [{"label": "New stack", "tone": "warning"}], "featured": False, "visible": True},
            "premium": {"tags": [{"label": "Most chosen", "tone": "accent"}], "featured": False, "visible": False},
        },
    }
    monkeypatch.setattr(billing_rates, "load_current_rates", AsyncMock(return_value=rates))
    monkeypatch.setattr(tax_service, "load_config", AsyncMock(return_value={"enabled": False}))
    monkeypatch.setattr(voice_stack_profiles, "load_profile_records", AsyncMock(return_value=records))
    # Provider registration is exercised by the voice-stack suite; this test owns shelf composition.
    monkeypatch.setattr(voice_stack_profiles, "_runtime_profile_blockers", lambda profile: [])
    monkeypatch.setattr(merchandising, "load_tier_merchandising", AsyncMock(return_value=merch_view))

    result = await app_billing.billing_catalog()

    assert result["pricingVersion"] == 9
    assert result["merchandisingVersion"] == 4
    assert result["featuredStyle"] == "forest"
    assert result["calculator"] == {
        "allowMinuteInput": False,
        "compareTiers": True,
        "shareableEstimate": False,
        "showGstToggle": True,
    }
    # The catalog quotes GST from the same saved settings checkout uses.
    assert result["tax"] == {
        "enabled": False,
        "ratePercent": 0.0,
        "priceIncludesTax": False,
        "countryCode": "IN",
    }
    # Disabled and unverified tiers never reach the public shelf; custom stacks do.
    assert [tier["id"] for tier in result["tiers"]] == ["low", "medium", "medium_copy_1"]
    assert [tier["label"] for tier in result["tiers"]] == ["Economical", "Standard Regional", "premium"]

    low, medium, custom = result["tiers"]
    # The approved profile price wins over the rate-table default.
    assert low["pstn"] == {"usdPerMin": 0.06, "inrPerMin": 6.0}
    assert low["web"] == {"usdPerMin": 0.08, "inrPerMin": 8.0}
    assert low["featured"] is True
    assert low["tags"] == [{"label": "Best value", "tone": "success"}]
    assert medium["pstn"] == {"usdPerMin": 0.09, "inrPerMin": 9.0}
    assert custom["pstn"] == {"usdPerMin": 0.065, "inrPerMin": 6.5}
    assert custom["web"] == {"usdPerMin": 0.055, "inrPerMin": 5.5}
    assert custom["tags"] == [{"label": "New stack", "tone": "warning"}]

    payload = json.dumps(result).lower()
    for forbidden in ("sarvam", "vobiz", "telnyx", "nango", "http://", "https://"):
        assert forbidden not in payload


async def test_admin_merchandising_endpoints_enforce_permission_and_validation(monkeypatch):
    from server.routes import dev_admin

    view = {
        "version": 1,
        "featuredStyle": "midnight",
        "updatedAt": "2026-10-28T00:00:00+00:00",
        "updatedBy": "fixture",
        "calculator": merchandising.default_calculator(),
        "tiers": merchandising.default_merchandising()["tiers"],
    }
    load = AsyncMock(return_value=view)
    save = AsyncMock(return_value=view)
    audit = AsyncMock()
    monkeypatch.setattr(merchandising, "load_tier_merchandising", load)
    monkeypatch.setattr(merchandising, "save_tier_merchandising", save)
    monkeypatch.setattr(dev_admin, "record_admin_action", audit)

    app = FastAPI()
    app.include_router(dev_admin.router)
    app.dependency_overrides[dev_admin.require_dev_session] = lambda: SimpleNamespace(
        role="developer", kind="dev", subject="fixture"
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
        response = await client.get("/api/dev/admin/pricing-merchandising")
        assert response.status_code == 200
        assert [tier["id"] for tier in response.json()["tiers"]] == ["low", "medium", "premium"]
        assert response.json()["featuredStyle"] == "midnight"
        assert response.json()["featuredStyles"] == list(merchandising.FEATURED_STYLES)
        assert response.json()["calculator"] == merchandising.default_calculator()
        assert response.json()["calculatorFeatures"] == list(merchandising.CALCULATOR_FEATURES)

        response = await client.put(
            "/api/dev/admin/pricing-merchandising",
            json={
                "expectedVersion": 0,
                "featuredStyle": "ivory",
                "calculator": {"compareTiers": False},
                "tiers": {"low": {"featured": True}},
            },
        )
        assert response.status_code == 200
        save.assert_awaited_once()
        assert save.await_args.kwargs["featured_style"] == "ivory"
        assert save.await_args.kwargs["calculator"] == {"compareTiers": False}

        save.side_effect = merchandising.MerchandisingError(
            "invalid_featured_style", "Choose one of the available featured card styles."
        )
        response = await client.put(
            "/api/dev/admin/pricing-merchandising",
            json={"expectedVersion": 1, "featuredStyle": "neon", "tiers": {"low": {"featured": True}}},
        )
        assert response.status_code == 422
        assert response.json()["detail"]["error"]["code"] == "invalid_featured_style"

        save.side_effect = merchandising.MerchandisingError("invalid_tag", "Tag labels cannot mention vendors.")
        response = await client.put(
            "/api/dev/admin/pricing-merchandising",
            json={"expectedVersion": 1, "tiers": {"low": {"tags": [{"label": "Vobiz"}]}}},
        )
        assert response.status_code == 422
        assert response.json()["detail"]["error"]["code"] == "invalid_tag"

        app.dependency_overrides[dev_admin.require_dev_session] = lambda: SimpleNamespace(
            role="customer_admin", kind="app", subject="fixture"
        )
        assert (await client.get("/api/dev/admin/pricing-merchandising")).status_code == 403
