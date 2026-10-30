"""Concurrent call channels: pricing, charging, renewal, grace/lapse and admission caps.

Runs on an isolated SQLite database; no carrier, payment or Vobiz call is made.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import JSON, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from server.db.models.concurrency_models import (
    TenantChannelEvent,
    TenantChannelSubscription,
    TenantConcurrencyDaily,
)
from server.db.models.entities import Agent, Base, Call, ConfigVersion, Tenant
from server.db.models.phase5_models import PstnDialRequest
from server.db.models.saas_models import BillingWallet, BillingWalletTransaction, User
from server.services.saas import call_admission as admission
from server.services.saas import concurrency_service as channels

T1, T2, UID = (uuid.UUID(f"bbbbbbbb-0000-4000-8000-{i:012d}") for i in (7001, 7002, 7003))


@compiles(JSONB, "sqlite")
def _sqlite_json(*_args, **_kw):
    return "JSON"


def _pricing(price_paise=0, *, capacity=10, included=1, grace=3, max_per_tenant=0, version=1):
    return {
        "configured": True, "version": version,
        "priceInrPaisePerChannel": price_paise,
        "priceUsdMicrosPerChannel": (price_paise * 1_000_000) // 9_500 if price_paise else 0,
        "fxRateInr": 95.0, "platformCapacity": capacity, "includedChannels": included,
        "graceDays": grace, "maxChannelsPerTenant": max_per_tenant, "periodDays": 30,
        "updatedAt": None, "actor": "test", "reason": "test pricing",
    }


@pytest.fixture
async def db(tmp_path, monkeypatch):
    models = [Tenant, User, Agent, Call, PstnDialRequest, ConfigVersion, BillingWallet, BillingWalletTransaction,
              TenantChannelSubscription, TenantChannelEvent, TenantConcurrencyDaily]
    for model in models:
        for column in model.__table__.columns:
            if isinstance(column.type, ARRAY):
                monkeypatch.setattr(column, "type", column.type.with_variant(JSON(), "sqlite"))
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'channels.db'}", connect_args={"timeout": 20})
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[m.__table__ for m in models]))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(admission, "get_session_factory", lambda: factory)
    monkeypatch.setattr(channels, "get_session_factory", lambda: factory)
    settings = SimpleNamespace(saas_max_concurrent_pstn=20, saas_max_outbound_cps=100)
    monkeypatch.setattr(admission, "get_settings", lambda: settings)
    monkeypatch.setattr("server.config.env.get_settings", lambda: SimpleNamespace(**vars(settings)))
    async with factory() as session:
        session.add_all([Tenant(tenant_id=T1, name="One", limits={"max_concurrent_pstn": 2}),
                         Tenant(tenant_id=T2, name="Two", limits={})])
        session.add(User(user_id=UID, email="channels@example.test", password_hash="unused"))
        await session.commit()
    channels.clear_pricing_cache()
    yield factory
    channels.clear_pricing_cache()
    await engine.dispose()


async def _fund(factory, tenant_id, paise):
    async with factory() as session:
        session.add(BillingWallet(tenant_id=tenant_id, balance_cents=0, balance_inr_paise=paise, currency="inr",
                                  updated_at=channels._utcnow()))
        await session.commit()


async def _wallet(factory, tenant_id):
    async with factory() as session:
        wallet = await session.get(BillingWallet, tenant_id)
        txs = (await session.execute(select(BillingWalletTransaction).where(
            BillingWalletTransaction.tenant_id == tenant_id))).scalars().all()
        return wallet, txs


async def _sub(factory, tenant_id):
    async with factory() as session:
        return await session.get(TenantChannelSubscription, tenant_id)


# ---------------------------------------------------------------------------
# Pricing and charging
# ---------------------------------------------------------------------------

async def test_zero_price_grants_channels_without_any_debit(db):
    channels.set_cached_pricing(_pricing(0, included=1))
    quote = await channels.quote_change(T1, 3)
    assert quote["chargeNowInrPaise"] == 0 and quote["free"] is True
    result = await channels.apply_change(T1, 3, request_id="req-free-0001", expected_charge_inr_paise=0,
                                         user_id=UID, actor="u")
    assert result["kind"] == "purchase" and result["chargedInrPaise"] == 0
    wallet, txs = await _wallet(db, T1)
    assert wallet is None and txs == []  # nothing debited, no ledger row
    async with db() as session:
        cap = await channels.channel_cap(session, await session.get(Tenant, T1), settings=None)
    assert cap["cap"] == 4 and cap["paid"] == 3 and cap["included"] == 1


async def test_paid_purchase_charges_price_times_channels_once(db):
    channels.set_cached_pricing(_pricing(50_000, included=1))  # ₹500 per channel per 30 days
    await _fund(db, T1, 200_000)
    quote = await channels.quote_change(T1, 2)
    assert quote["chargeNowInrPaise"] == 100_000 and quote["rule"] == "new_period"
    assert quote["recurringInr"] == 1000.0
    first = await channels.apply_change(T1, 2, request_id="req-buy-0001", expected_charge_inr_paise=100_000,
                                        user_id=UID, actor="u")
    retry = await channels.apply_change(T1, 2, request_id="req-buy-0001", expected_charge_inr_paise=100_000,
                                        user_id=UID, actor="u")
    assert first["chargedInrPaise"] == 100_000
    assert retry["duplicate"] is True
    wallet, txs = await _wallet(db, T1)
    assert wallet.balance_inr_paise == 100_000
    assert [(t.kind, t.amount_inr_paise) for t in txs] == [("channel_purchase", -100_000)]
    sub = await _sub(db, T1)
    assert sub.paid_channels == 2 and sub.status == "active" and sub.pricing_version == 1
    assert channels._aware(sub.current_period_end) - channels._aware(sub.current_period_start) == timedelta(days=30)


async def test_insufficient_balance_changes_nothing(db):
    channels.set_cached_pricing(_pricing(50_000))
    await _fund(db, T1, 10_000)
    with pytest.raises(HTTPException) as exc:
        await channels.apply_change(T1, 1, request_id="req-poor-0001", expected_charge_inr_paise=50_000,
                                    user_id=UID, actor="u")
    assert exc.value.status_code == 402
    wallet, txs = await _wallet(db, T1)
    assert wallet.balance_inr_paise == 10_000 and txs == []
    assert await _sub(db, T1) is None


async def test_price_change_between_quote_and_confirm_is_refused(db):
    channels.set_cached_pricing(_pricing(50_000))
    await _fund(db, T1, 500_000)
    quote = await channels.quote_change(T1, 1)
    channels.set_cached_pricing(_pricing(60_000, version=2))
    with pytest.raises(HTTPException) as exc:
        await channels.apply_change(T1, 1, request_id="req-stale-0001",
                                    expected_charge_inr_paise=quote["chargeNowInrPaise"], user_id=UID, actor="u")
    assert exc.value.status_code == 409
    assert exc.value.detail["error"]["code"] == "quote_changed"
    _, txs = await _wallet(db, T1)
    assert txs == []


async def test_mid_period_increase_is_prorated_and_keeps_renewal_date(db):
    channels.set_cached_pricing(_pricing(60_000))
    await _fund(db, T1, 1_000_000)
    await channels.apply_change(T1, 1, request_id="req-base-0001", expected_charge_inr_paise=60_000, user_id=UID, actor="u")
    async with db() as session:
        sub = await session.get(TenantChannelSubscription, T1)
        end = channels._utcnow() + timedelta(days=15)
        sub.current_period_end = end
        sub.current_period_start = end - timedelta(days=30)
        await session.commit()
    quote = await channels.quote_change(T1, 3)
    # Two added channels for half a period: 2 x ₹600 x 0.5 = ₹600 (± rounding for elapsed ms).
    assert abs(quote["chargeNowInrPaise"] - 60_000) <= 2 and quote["rule"] == "prorated"
    await channels.apply_change(T1, 3, request_id="req-add-0001",
                                expected_charge_inr_paise=quote["chargeNowInrPaise"], user_id=UID, actor="u")
    sub = await _sub(db, T1)
    assert sub.paid_channels == 3
    assert abs((channels._aware(sub.current_period_end) - end).total_seconds()) < 1


async def test_downgrade_applies_at_renewal_without_refund(db):
    channels.set_cached_pricing(_pricing(10_000))
    await _fund(db, T1, 1_000_000)
    await channels.apply_change(T1, 4, request_id="req-four-0001", expected_charge_inr_paise=40_000, user_id=UID, actor="u")
    result = await channels.apply_change(T1, 1, request_id="req-down-0001", expected_charge_inr_paise=0,
                                         user_id=UID, actor="u")
    assert result["kind"] == "downgrade_scheduled" and result["chargedInrPaise"] == 0
    sub = await _sub(db, T1)
    assert sub.paid_channels == 4 and sub.pending_paid_channels == 1  # still usable this period
    later = channels._aware(sub.current_period_end) + timedelta(minutes=1)
    assert await channels.renew_tenant(T1, now=later) == "renewed"
    assert await channels.renew_tenant(T1, now=later) == "skipped"  # next period not due
    sub = await _sub(db, T1)
    assert sub.paid_channels == 1 and sub.pending_paid_channels is None
    wallet, txs = await _wallet(db, T1)
    assert sorted(t.amount_inr_paise for t in txs) == [-40_000, -10_000]
    assert wallet.balance_inr_paise == 1_000_000 - 50_000


async def test_renewal_failure_grace_then_lapse_to_included(db):
    channels.set_cached_pricing(_pricing(30_000, included=1, grace=3))
    await _fund(db, T1, 60_000)
    await channels.apply_change(T1, 2, request_id="req-two-0001", expected_charge_inr_paise=60_000, user_id=UID, actor="u")
    sub = await _sub(db, T1)
    due = channels._aware(sub.current_period_end) + timedelta(minutes=1)
    assert await channels.renew_tenant(T1, now=due) == "grace"
    sub = await _sub(db, T1)
    assert sub.status == "grace" and "Add funds" in sub.notice
    async with db() as session:
        cap = await channels.channel_cap(session, await session.get(Tenant, T1), settings=None)
    assert cap["cap"] == 3  # channels kept during grace
    after_grace = channels._aware(sub.grace_until) + timedelta(minutes=1)
    assert await channels.renew_tenant(T1, now=after_grace) == "lapsed"
    sub = await _sub(db, T1)
    assert sub.status == "lapsed" and sub.paid_channels == 0 and "included" in sub.notice
    async with db() as session:
        cap = await channels.channel_cap(session, await session.get(Tenant, T1), settings=None)
        kinds = [e.kind for e in (await session.execute(select(TenantChannelEvent).where(
            TenantChannelEvent.tenant_id == T1).order_by(TenantChannelEvent.created_at))).scalars()]
    assert cap["cap"] == 1
    assert kinds == ["purchase", "renewal_failed", "lapsed"]
    _, txs = await _wallet(db, T1)
    assert len(txs) == 1  # the failed renewal never wrote a partial debit


async def test_platform_capacity_prevents_overselling_paid_channels(db):
    channels.set_cached_pricing(_pricing(0, capacity=3, included=1))
    await channels.apply_change(T1, 2, request_id="req-t1-00001", expected_charge_inr_paise=0, user_id=UID, actor="u")
    with pytest.raises(HTTPException) as exc:
        await channels.apply_change(T2, 2, request_id="req-t2-00001", expected_charge_inr_paise=0, user_id=UID, actor="u")
    assert exc.value.status_code == 409 and exc.value.detail["error"]["code"] == "platform_capacity"


# ---------------------------------------------------------------------------
# Admission enforcement
# ---------------------------------------------------------------------------

async def test_legacy_caps_unchanged_until_pricing_is_configured(db):
    channels.set_cached_pricing(None)
    channels.clear_pricing_cache()
    async with db() as session:
        cap = await channels.channel_cap(session, await session.get(Tenant, T1),
                                         settings=SimpleNamespace(saas_max_concurrent_pstn=20))
    assert cap == {"legacy": True, "cap": 2, "included": 2, "paid": 0, "platformCapacity": 20, "pricingVersion": None}


async def test_admission_caps_tenant_at_channels_and_counts_rejections(db):
    channels.set_cached_pricing(_pricing(0, included=1, capacity=10))
    await admission.reserve(T1, "inbound:call-1", provider="vobiz", payload={"direction": "inbound", "call": "1"})
    with pytest.raises(HTTPException) as inbound:
        await admission.reserve(T1, "inbound:call-2", provider="vobiz", payload={"direction": "inbound", "call": "2"})
    with pytest.raises(HTTPException) as campaign:
        await admission.reserve(T1, "camp:c:1:a", provider="vobiz", payload={"direction": "outbound", "call": "3"})
    assert inbound.value.status_code == 429 and inbound.value.detail["error"]["code"] == "concurrency_limit"
    assert campaign.value.status_code == 429  # the campaign runner re-queues on 429
    async with db() as session:
        daily = (await session.execute(select(TenantConcurrencyDaily).where(
            TenantConcurrencyDaily.tenant_id == T1))).scalar_one()
    assert (daily.admitted, daily.rejected, daily.queued, daily.peak_active, daily.channel_cap) == (1, 1, 1, 1, 1)
    # Buying one channel lifts the cap immediately.
    await channels.apply_change(T1, 1, request_id="req-lift-0001", expected_charge_inr_paise=0, user_id=UID, actor="u")
    await admission.reserve(T1, "inbound:call-4", provider="vobiz", payload={"direction": "inbound", "call": "4"})


async def test_platform_capacity_caps_all_tenants_together(db):
    channels.set_cached_pricing(_pricing(0, included=1, capacity=1))
    await admission.reserve(T1, "inbound:p-1", provider="vobiz", payload={"direction": "inbound", "call": "p1"})
    with pytest.raises(HTTPException) as exc:
        await admission.reserve(T2, "inbound:p-2", provider="vobiz", payload={"direction": "inbound", "call": "p2"})
    assert exc.value.status_code == 429 and exc.value.detail["error"]["code"] == "platform_capacity"


async def test_overview_reports_channels_usage_and_charges(db):
    channels.set_cached_pricing(_pricing(25_000, included=1))
    await _fund(db, T1, 100_000)
    await channels.apply_change(T1, 1, request_id="req-view-0001", expected_charge_inr_paise=25_000, user_id=UID, actor="u")
    await admission.reserve(T1, "inbound:v-1", provider="vobiz", payload={"direction": "inbound", "call": "v1"})
    view = await channels.tenant_overview(T1, days=7)
    assert view["channels"]["cap"] == 2 and view["channels"]["activeNow"] == 1
    assert view["pricing"]["priceInrPerChannel"] == 250.0
    assert len(view["daily"]) == 7 and view["daily"][-1]["admitted"] == 1
    assert view["events"][0]["kind"] == "purchase" and view["events"][0]["amountInr"] == 250.0
    assert view["subscription"]["paidChannels"] == 1


async def test_admin_pricing_is_versioned_and_cannot_undercut_sold_channels(db, monkeypatch):
    from unittest.mock import AsyncMock

    monkeypatch.setattr("server.services.saas.billing_rates.load_current_rates",
                        AsyncMock(return_value={"fx_rate_inr": 95.0}))
    first = await channels.save_pricing(actor="admin", reason="initial channel price", price_inr_per_channel="499.00",
                                        platform_capacity=5, included_channels=1)
    assert first["version"] == 1 and first["priceInrPaisePerChannel"] == 49_900
    assert first["priceUsdMicrosPerChannel"] == 5_252_632  # ₹499 / 95
    await _fund(db, T1, 1_000_000)
    await channels.apply_change(T1, 3, request_id="req-sold-0001", expected_charge_inr_paise=149_700, user_id=UID, actor="u")
    with pytest.raises(ValueError, match="already sold"):
        await channels.save_pricing(actor="admin", reason="shrink capacity", price_inr_per_channel=0,
                                    platform_capacity=2, included_channels=1)
    second = await channels.save_pricing(actor="admin", reason="free channels promo", price_inr_per_channel=0,
                                         platform_capacity=5, included_channels=2)
    assert second["version"] == 2 and second["priceInrPaisePerChannel"] == 0
    # The paid period keeps the price it was bought at; the new price applies at renewal.
    sub = await _sub(db, T1)
    assert sub.price_inr_paise_per_channel == 49_900 and sub.pricing_version == 1
    assert await channels.renew_tenant(T1, now=channels._aware(sub.current_period_end) + timedelta(seconds=1)) == "renewed"
    _, txs = await _wallet(db, T1)
    assert [t.kind for t in txs] == ["channel_purchase"]  # a free renewal debits nothing
    sub = await _sub(db, T1)
    assert sub.pricing_version == 2 and sub.status == "active"
