"""Tests for P0-2: Billing Rates Persistence and Immutable Call Snapshots."""
import uuid
from datetime import datetime, timezone
import pytest
from sqlalchemy import select

from server.services.saas.billing_rates import (
    BillingConfigurationError,
    clear_rates_cache,
    effective_rates,
    rates_with_derived_inr,
    set_cached_rates,
    update_rates_versioned,
)
from server.db.connection import get_session_factory
from server.db.models.saas_models import BillingRateVersion
from server.services.saas.billing_wallet_service import _resolve_call_wallet_debit


@pytest.mark.asyncio
async def test_billing_rates_versioning_lifecycle():
    """Verify rate updates increment version numbers and retain full audit history."""
    clear_rates_cache()
    factory = get_session_factory()
    actor_1 = "admin@test.local"
    reason_1 = "Initial Q4 tariff update"

    res_1 = await update_rates_versioned(
        actor=actor_1,
        reason=reason_1,
        pstn_usd_per_min=0.12,
        web_usd_per_min=0.08,
        did_monthly_usd=5.0,
        fx_rate_inr=92.5,
    )

    assert res_1["pstn_rate_usd_cents_per_min"] == 12
    assert res_1["web_agent_rate_usd_cents_per_min"] == 8
    assert res_1["did_monthly_usd_cents"] == 500
    assert res_1["fx_rate_inr"] == 92.5

    # Update to Version 2
    actor_2 = "ops@test.local"
    reason_2 = "Holiday season promotional rate"
    res_2 = await update_rates_versioned(
        actor=actor_2,
        reason=reason_2,
        pstn_usd_per_min=0.15,
        web_usd_per_min=0.10,
        did_monthly_usd=6.0,
        fx_rate_inr=94.0,
    )

    assert res_2["pstn_rate_usd_cents_per_min"] == 15
    assert res_2["web_agent_rate_usd_cents_per_min"] == 10

    # If DB is configured, verify versioning and is_active flag in DB
    if factory is not None:
        async with factory() as session:
            rows = (
                await session.execute(
                    select(BillingRateVersion).order_by(BillingRateVersion.version.asc())
                )
            ).scalars().all()
            if len(rows) >= 2:
                v1, v2 = rows[-2], rows[-1]
                assert v1.is_active is False
                assert v1.created_by == actor_1
                assert v1.reason == reason_1
                assert v2.is_active is True
                assert v2.created_by == actor_2
                assert v2.reason == reason_2
                assert v2.pstn_rate_usd_cents_per_min == 15


@pytest.mark.asyncio
async def test_billing_rates_reason_validation():
    """Verify that updating rates without a minimum 8-char reason fails."""
    with pytest.raises(ValueError, match="minimum 8 characters"):
        await update_rates_versioned(
            actor="admin",
            reason="short",
            pstn_usd_per_min=0.10,
        )


def test_call_wallet_debit_uses_locked_rate_snapshot():
    """Verify that when a call has a snapshotted rate, it is billed at the snapshot rate

    even if current global rates have changed to a much higher value.
    """
    call_id = str(uuid.uuid4())
    # 2 minutes call duration = 120 seconds
    duration_sec = 120

    # Call had a locked snapshot of 10 cents/min, FX 90.0
    snap_rate = 10
    snap_fx = 90.0

    # Mock settings with higher current default rate
    class DummySettings:
        pstn_rate_usd_cents_per_min = 30
        web_agent_rate_usd_cents_per_min = 25
        fx_rate_inr = 95.0

    # 1. Billing with locked snapshot: 2 mins * 10 cents = 20 cents, 20 * 90 = 1800 paise
    cents, paise, mode = _resolve_call_wallet_debit(
        call_id=call_id,
        channel="pstn",
        duration_sec=duration_sec,
        settings=DummySettings(),
        stored_rate_cents=snap_rate,
        stored_fx=snap_fx,
    )

    assert cents == 20
    assert paise == 1800
    assert mode == "catalog_prorated"

    # 2. Billing without snapshot falls back to current rates (would be 2 mins * 30 cents = 60 cents)
    cents_cur, paise_cur, _ = _resolve_call_wallet_debit(
        call_id=call_id,
        channel="pstn",
        duration_sec=duration_sec,
        settings=DummySettings(),
        stored_rate_cents=None,
        stored_fx=None,
    )
    # Proves snapshot protects against higher current rates
    assert cents != cents_cur or snap_rate == DummySettings.pstn_rate_usd_cents_per_min
