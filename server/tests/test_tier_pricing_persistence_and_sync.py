"""Verification that tier pricing and wholesale supplier costs sustain and synchronize universally."""
from __future__ import annotations

import pytest
from server.db.connection import get_session_factory, init_db
from server.services.dev_runtime import effective_app_environment
from server.services.saas.voice_stack_profiles import (
    save_composed_profile,
    profile_view,
    load_profile_records,
)
from server.services.saas.voice_stack_defaults import recommended_composed_profile
from server.services.saas.billing_rates import (
    load_current_rates,
    update_rates_versioned,
    clear_rates_cache,
)
from server.services.saas.billing_wallet_service import wallet_summary
from server.db.models.entities import TierAssignment
from server.db.models.saas_models import BillingRateVersion
from sqlalchemy import select, desc
import uuid


@pytest.mark.asyncio
async def test_tier_pricing_and_supplier_cost_persistence_and_sync():
    await init_db()
    factory = get_session_factory()
    if factory is None:
        pytest.skip("Requires database connection (LIVE_DB=1)")
    env = effective_app_environment()

    # 1. Verify premium template loads cleanly with allow_premium=True
    premium_tmpl = recommended_composed_profile("premium", allow_premium=True)
    assert premium_tmpl["llm"]["provider"] == "gemini"
    assert premium_tmpl["llm"]["apiMode"] == "websocket"

    # 2. Save Low tier with custom platform retail price and supplier wholesale cost
    low_tmpl = recommended_composed_profile("low")
    low_tmpl["retailRateInr"] = 4.25
    low_view_curr = await profile_view("low", env, include_internal=True)
    low_tmpl["retailRateInr"] = 4.25
    low_tmpl["supplierCostInr"] = 1.35
    low_view = await save_composed_profile(
        environment=env,
        tier="low",
        expected_revision=low_view_curr["profileRevision"],
        payload=low_tmpl,
        actor="admin@test.local",
        allow_premium=True,
    )
    assert low_view["composedProfile"]["retailRateInr"] == 4.25
    assert low_view["composedProfile"]["supplierCostInr"] == 1.35

    # Verify that BillingRateVersion was automatically synchronized with 4.25 (425 paise)
    rates = await load_current_rates()
    assert rates["pstn_low_rate_inr_paise_per_min"] == 425

    # 3. Save Medium tier with custom platform retail price and supplier wholesale cost
    med_view_curr = await profile_view("medium", env, include_internal=True)
    med_tmpl = recommended_composed_profile("medium")
    med_tmpl["retailRateInr"] = 6.20
    med_tmpl["supplierCostInr"] = 2.15
    med_view = await save_composed_profile(
        environment=env,
        tier="medium",
        expected_revision=med_view_curr["profileRevision"],
        payload=med_tmpl,
        actor="admin@test.local",
        allow_premium=True,
    )
    assert med_view["composedProfile"]["retailRateInr"] == 6.20
    assert med_view["composedProfile"]["supplierCostInr"] == 2.15

    rates = await load_current_rates()
    assert rates["pstn_medium_rate_inr_paise_per_min"] == 620

    # 4. Save Premium (Gemini 3.8 Live) tier with custom platform retail price and supplier wholesale cost
    prem_view_curr = await profile_view("premium", env, include_internal=True)
    premium_tmpl["retailRateInr"] = 12.50
    premium_tmpl["supplierCostInr"] = 4.00
    prem_view = await save_composed_profile(
        environment=env,
        tier="premium",
        expected_revision=prem_view_curr["profileRevision"],
        payload=premium_tmpl,
        actor="admin@test.local",
        allow_premium=True,
    )
    assert prem_view["composedProfile"]["retailRateInr"] == 12.50
    assert prem_view["composedProfile"]["supplierCostInr"] == 4.00

    rates = await load_current_rates()
    assert rates["pstn_premium_rate_inr_paise_per_min"] == 1250

    # 5. Verify that wallet_summary reflects these configured rates top-level
    async with factory() as session:
        from server.db.models.entities import Tenant
        res = await session.execute(select(Tenant.tenant_id).limit(1))
        existing_tenant = res.scalar_one_or_none()
        if not existing_tenant:
            new_tenant = Tenant(tenant_id=uuid.uuid4(), name="Test Tenant")
            session.add(new_tenant)
            await session.commit()
            existing_tenant = new_tenant.tenant_id

    summary_result = await wallet_summary(tenant_id=existing_tenant)
    assert summary_result["pstnLowRateInrPerMin"] == 4.25
    assert summary_result["pstnMediumRateInrPerMin"] == 6.20
    assert summary_result["pstnPremiumRateInrPerMin"] == 12.50
    assert summary_result["rateInrPerMin"] == 12.50
    assert summary_result["tierRates"]["low"]["inrPerMin"] == 4.25
    assert summary_result["tierRates"]["medium"]["inrPerMin"] == 6.20
    assert summary_result["tierRates"]["premium"]["inrPerMin"] == 12.50

    # 6. Verify reverse synchronization: Updating rates via update_rates_versioned
    # synchronizes back into TierAssignment composed_voice_profile
    await update_rates_versioned(
        actor="admin@test.local",
        reason="Admin updated rates from Pricing tab",
        rate_currency="INR",
        pstn_low_inr_per_min="3.75",
        pstn_medium_inr_per_min="5.50",
        pstn_premium_inr_per_min="11.00",
    )

    low_reloaded = await profile_view("low", env, include_internal=True)
    assert low_reloaded["composedProfile"]["retailRateInr"] == 3.75

    med_reloaded = await profile_view("medium", env, include_internal=True)
    assert med_reloaded["composedProfile"]["retailRateInr"] == 5.50

    prem_reloaded = await profile_view("premium", env, include_internal=True)
    assert prem_reloaded["composedProfile"]["retailRateInr"] == 11.00
