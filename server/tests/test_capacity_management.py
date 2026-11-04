"""Call capacity: number-held channels, fair admission, approval modes and Vobiz bundle purchases.

Runs on an isolated SQLite database. Vobiz is a fake: no money moves.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import JSON, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from server.db.models.concurrency_models import (
    CapacityIncident,
    TenantChannelEvent,
    TenantChannelSubscription,
    TenantConcurrencyDaily,
    VobizCapacityPurchase,
)
from server.db.models.entities import Agent, Base, Call, ConfigVersion, Tenant
from server.db.models.phase5_models import PhoneNumber, PstnDialRequest
from server.db.models.saas_models import (
    BillingWallet,
    BillingWalletTransaction,
    NumberPurchase,
    NumberReservation,
    ProvisionJob,
    User,
)
from server.services.saas import call_admission as admission
from server.services.saas import capacity_incidents, capacity_planner, capacity_policy
from server.services.saas import concurrency_service as channels
from server.services.saas import vobiz_concurrency as vobiz

A, B, C, UID = (uuid.UUID(f"cccccccc-0000-4000-8000-{i:012d}") for i in (1, 2, 3, 9))


@compiles(JSONB, "sqlite")
def _sqlite_json(*_args, **_kw):
    return "JSON"


def _pricing(*, capacity=3, included=1, per_number=1, block=10, cps=0, version=1):
    return {
        "configured": True, "version": version, "priceInrPaisePerChannel": 0, "priceUsdMicrosPerChannel": 0,
        "fxRateInr": 95.0, "platformCapacity": capacity, "includedChannels": included, "graceDays": 3,
        "maxChannelsPerTenant": 0, "channelsPerNumber": per_number, "platformCps": cps,
        "concurrencyBlockSize": block, "periodDays": 30, "updatedAt": None, "actor": "t", "reason": "test pricing",
    }


@pytest.fixture
async def db(tmp_path, monkeypatch):
    models = [Tenant, User, Agent, Call, PstnDialRequest, ConfigVersion, BillingWallet, BillingWalletTransaction,
              TenantChannelSubscription, TenantChannelEvent, TenantConcurrencyDaily, PhoneNumber, NumberPurchase,
              NumberReservation, ProvisionJob, CapacityIncident, VobizCapacityPurchase]
    for model in models:
        for column in model.__table__.columns:
            if isinstance(column.type, ARRAY):
                monkeypatch.setattr(column, "type", column.type.with_variant(JSON(), "sqlite"))
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'capacity.db'}", connect_args={"timeout": 20})
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[m.__table__ for m in models]))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    for module in (admission, channels, capacity_incidents, capacity_planner, capacity_policy):
        monkeypatch.setattr(module, "get_session_factory", lambda: factory)
    settings = SimpleNamespace(saas_max_concurrent_pstn=20, saas_max_outbound_cps=1)
    monkeypatch.setattr(admission, "get_settings", lambda: settings)
    monkeypatch.setattr("server.config.env.get_settings", lambda: settings)
    async with factory() as session:
        session.add_all([Tenant(tenant_id=t, name=n, limits={}) for t, n in ((A, "Alpha"), (B, "Beta"), (C, "Gamma"))])
        session.add(User(user_id=UID, email="cap@example.test", password_hash="unused"))
        await session.commit()
    channels.clear_pricing_cache()
    yield factory
    channels.clear_pricing_cache()
    await engine.dispose()


async def _numbers(factory, tenant_id, n, status="active"):
    async with factory() as session:
        for i in range(n):
            session.add(PhoneNumber(tenant_id=tenant_id, e164=f"+9180{uuid.uuid4().int % 10**8:08d}", status=status))
        await session.commit()


async def _live(factory, tenant_id, n):
    async with factory() as session:
        for _ in range(n):
            session.add(PstnDialRequest(request_key=uuid.uuid4().hex, tenant_id=tenant_id, fingerprint="f",
                                        provider="vobiz", status="answered",
                                        created_at=channels._utcnow() - channels.timedelta(minutes=5),
                                        updated_at=channels._utcnow()))
        await session.commit()


# --------------------------------------------------------------------- pure rules


def test_held_channels_are_never_taken_by_best_effort_calls():
    held = {A: {"held": 2}, B: {"held": 0}}
    # B (best effort) may not take A's two unused held channels out of three.
    assert channels.admission_decision(B, capacity=3, active={B: 1}, held=held) == "reserved_full"
    # A is inside its held channels: admitted even though B uses the free one.
    assert channels.admission_decision(A, capacity=3, active={B: 1}, held=held) is None
    # The pool is full: nobody gets in.
    assert channels.admission_decision(A, capacity=3, active={A: 2, B: 1}, held=held) == "platform_full"
    # Free capacity left after every held channel: best effort is admitted.
    assert channels.admission_decision(B, capacity=4, active={}, held=held) is None


def test_estimate_rounds_to_vobiz_blocks_and_adds_a_block_after_refusals():
    est = capacity_planner.estimate(owned=3, held=4, peak=2, block=10, platform_incidents_24h=0)
    assert est["required"] == 4 and est["recommended"] == 5 and est["buy"] == 10
    calm = capacity_planner.estimate(owned=20, held=4, peak=3, block=10, platform_incidents_24h=0)
    assert calm["buy"] == 0
    refused = capacity_planner.estimate(owned=20, held=4, peak=3, block=10, platform_incidents_24h=2)
    assert refused["buy"] == 10


def test_signals_warn_before_running_out_and_flag_overcommit():
    est = capacity_planner.estimate(owned=10, held=8, peak=0, block=10, platform_incidents_24h=0)
    codes = [s["code"] for s in capacity_planner.signals(configured=True, owned=10, held=8, peak=0, vobiz_max=10,
                                                         vobiz_cps=1, owned_cps=1, incidents={}, est=est)]
    assert codes == ["filling_up"]
    est = capacity_planner.estimate(owned=3, held=5, peak=0, block=10, platform_incidents_24h=0)
    out = capacity_planner.signals(configured=True, owned=3, held=5, peak=0, vobiz_max=3, vobiz_cps=1,
                                   owned_cps=2, incidents={}, est=est)
    assert out[0]["level"] == "critical" and {"overcommitted", "cps_above_vobiz"} <= {s["code"] for s in out}


# --------------------------------------------------------------------- held channels


async def test_each_number_holds_a_channel_and_raises_the_tenant_cap(db):
    channels.set_cached_pricing(_pricing(capacity=10, included=1))
    await _numbers(db, A, 3)
    await _numbers(db, A, 1, status="suspended")  # an unpaid number holds nothing
    async with db() as session:
        cap = await channels.channel_cap(session, await session.get(Tenant, A), settings=None)
        held = await channels.held_by_tenant(session, _pricing())
    assert cap["numbers"] == 3 and cap["numberChannels"] == 3 and cap["cap"] == 4
    assert held[A]["held"] == 3


async def test_admission_keeps_a_numbered_tenants_channel_free(db):
    channels.set_cached_pricing(_pricing(capacity=2, included=2))
    await _numbers(db, A, 1)
    await _live(db, B, 1)
    # B has no number: its second call would take the channel A's number holds.
    with pytest.raises(HTTPException) as exc:
        await admission.reserve(B, "b-2", provider="vobiz", payload={})
    assert exc.value.status_code == 429 and exc.value.detail["error"]["code"] == "platform_capacity"
    key, previous = await admission.reserve(A, "a-1", provider="vobiz", payload={})
    assert previous is None and key
    async with db() as session:
        kinds = (await session.execute(select(CapacityIncident.kind, CapacityIncident.tenant_id))).all()
    assert ("reserved_full", B) in kinds


async def test_platform_cps_is_shared_by_every_tenant(db):
    channels.set_cached_pricing(_pricing(capacity=10, included=5, cps=1))
    await admission.reserve(A, "a-cps", provider="vobiz", payload={"to": "+919000000001"})
    with pytest.raises(HTTPException) as exc:
        await admission.reserve(B, "b-cps", provider="vobiz", payload={"to": "+919000000002"})
    assert exc.value.detail["error"]["code"] == "call_pacing"
    async with db() as session:
        assert (await session.execute(select(CapacityIncident.kind))).scalars().all() == ["cps_paced"]


async def test_paid_channels_cannot_be_sold_into_number_held_capacity(db):
    channels.set_cached_pricing(_pricing(capacity=3, included=0))
    await _numbers(db, A, 2)
    async with db() as session:
        session.add(BillingWallet(tenant_id=B, balance_cents=0, balance_inr_paise=10**7, currency="inr",
                                  updated_at=channels._utcnow()))
        await session.commit()
    with pytest.raises(HTTPException) as exc:
        await channels.apply_change(B, 2, request_id="buy-2", expected_charge_inr_paise=0, user_id=UID, actor="t")
    assert exc.value.status_code == 409 and "not charged" in exc.value.detail["error"]["message"]
    ok = await channels.apply_change(B, 1, request_id="buy-1", expected_charge_inr_paise=0, user_id=UID, actor="t")
    assert ok["ok"] and ok["subscription"]["paidChannels"] == 1


# --------------------------------------------------------------------- approval modes


async def _policy(factory, **payload):
    async with factory() as session:
        session.add(ConfigVersion(id=uuid.uuid4(), resource_type="capacity_policy", resource_id="platform",
                                  version=1, payload=payload, created_at=channels._utcnow()))
        await session.commit()


async def test_auto_mode_approves_when_there_is_room_and_queues_when_there_is_not(db):
    channels.set_cached_pricing(_pricing(capacity=2))
    await _numbers(db, A, 1)
    assert (await capacity_policy.decide_number_purchase(B))["approved"] is True
    await _numbers(db, B, 1)
    decision = await capacity_policy.decide_number_purchase(C)
    assert decision == {"approved": False, "reason": "needs_capacity", "policy": "auto"}


async def test_manual_mode_queues_every_purchase(db):
    channels.set_cached_pricing(_pricing(capacity=50))
    await _policy(db, approvalMode="manual")
    assert (await capacity_policy.decide_number_purchase(A))["reason"] == "manual"


class FakeVobiz:
    def __init__(self, *, limit=3, price="4990.00", fail_purchase=None):
        self.limit, self.price, self.fail_purchase, self.bought = limit, price, fail_purchase, []

    async def preview(self, quantity, client=None, *, resource_type="concurrent_calls"):
        return {"available": True, "resourceType": resource_type, "quantity": quantity,
                "monthlyCost": self.price, "currency": "INR", "periodDays": 30}

    async def purchase(self, resource_type, quantity, client=None):
        if self.fail_purchase:
            return self.fail_purchase
        self.bought.append((resource_type, quantity))
        self.limit += quantity
        return {"status": "succeeded", "subscriptionId": "sub_1", "monthlyCost": self.price, "currency": "INR",
                "nextBillingDate": "2026-12-04"}

    async def limits(self, client=None):
        return {"available": True, "concurrentLimit": self.limit, "cpsLimit": 1}

    async def live(self, client=None):
        return {"available": True, "maxConcurrent": self.limit, "concurrentCalls": 0}

    async def balance(self, client=None):
        return {"available": True, "balance": "100000", "currency": "INR"}


@pytest.fixture
def fake_vobiz(monkeypatch):
    fake = FakeVobiz()
    monkeypatch.setattr(vobiz, "preview_channel_price", fake.preview)
    monkeypatch.setattr(vobiz, "purchase_capacity", fake.purchase)
    monkeypatch.setattr(vobiz, "fetch_account_limits", fake.limits)
    monkeypatch.setattr(vobiz, "fetch_platform_concurrency", fake.live)
    monkeypatch.setattr(vobiz, "fetch_balance", fake.balance)

    async def save_pricing(**kw):
        cfg = _pricing(capacity=kw["platform_capacity"], cps=kw["platform_cps"], version=2)
        channels.set_cached_pricing(cfg)
        return cfg

    monkeypatch.setattr(channels, "save_pricing", save_pricing)
    return fake


async def test_auto_buy_buys_one_block_within_budget_then_approves(db, fake_vobiz):
    channels.set_cached_pricing(_pricing(capacity=3))
    await _numbers(db, A, 3)
    await _policy(db, approvalMode="auto", autoBuy=True, autoBuyMonthlyBudgetInr="5000")
    decision = await capacity_policy.decide_number_purchase(B)
    assert decision["approved"] is True and decision["reason"] == "auto_bought"
    assert fake_vobiz.bought == [("concurrent_calls", 10)]
    assert (await channels.load_pricing())["platformCapacity"] == 13
    # The budget is spent: the next shortfall queues for the admin instead of buying again.
    channels.set_cached_pricing(_pricing(capacity=3, version=3))
    decision = await capacity_policy.decide_number_purchase(C)
    assert decision["approved"] is False and decision["reason"] == "needs_capacity:over_budget"
    assert len(fake_vobiz.bought) == 1


async def test_approve_holds_the_channel_and_starts_activation_reject_refunds(db, monkeypatch):
    channels.set_cached_pricing(_pricing(capacity=1))
    async with db() as session:
        p1 = NumberPurchase(tenant_id=A, e164="+918000000001", status="awaiting_approval", provider="vobiz")
        p2 = NumberPurchase(tenant_id=B, e164="+918000000002", status="awaiting_approval", provider="vobiz")
        session.add_all([p1, p2])
        await session.flush()
        session.add_all([ProvisionJob(purchase_id=p1.id, status="held"), ProvisionJob(purchase_id=p2.id, status="held")])
        await session.commit()
    assert [q["e164"] for q in await capacity_policy.queue()] == ["+918000000001", "+918000000002"]
    assert (await capacity_policy.approve(p1.id, actor="admin"))["status"] == "paid"
    async with db() as session:
        job = (await session.execute(select(ProvisionJob).where(ProvisionJob.purchase_id == p1.id))).scalar_one()
    assert job.status == "queued"
    # The only channel is now held by the approved (activating) number.
    with pytest.raises(HTTPException) as exc:
        await capacity_policy.approve(p2.id, actor="admin")
    assert exc.value.detail["error"]["code"] == "needs_capacity" and exc.value.detail["error"]["buy"] == 10

    refunded = []

    async def refund_purchase(purchase_id):
        refunded.append(purchase_id)
        return {"ok": True, "refunded": True}

    monkeypatch.setattr("server.services.saas.number_purchase_admin.refund_purchase", refund_purchase)
    out = await capacity_policy.reject(p2.id, actor="admin", reason="No capacity this week")
    assert out["refunded"] is True and refunded == [p2.id]


# --------------------------------------------------------------------- Vobiz purchases


async def test_purchase_is_one_time_per_request_and_checks_the_price(db, fake_vobiz):
    channels.set_cached_pricing(_pricing(capacity=3))
    with pytest.raises(HTTPException) as exc:
        await capacity_planner.purchase(resource_type="concurrent_calls", quantity=10, request_id="req-00000001",
                                        expected_monthly_cost="3000", actor="admin", reason="Need more lines")
    assert exc.value.detail["error"]["code"] == "quote_changed" and fake_vobiz.bought == []
    first = await capacity_planner.purchase(resource_type="concurrent_calls", quantity=10, request_id="req-00000002",
                                            expected_monthly_cost="4990.00", actor="admin", reason="Need more lines")
    again = await capacity_planner.purchase(resource_type="concurrent_calls", quantity=10, request_id="req-00000002",
                                            expected_monthly_cost="4990.00", actor="admin", reason="Need more lines")
    assert first["ok"] and again["duplicate"] and fake_vobiz.bought == [("concurrent_calls", 10)]
    assert first["applied"]["platformCapacity"] == 13


async def test_unanswered_purchase_blocks_buying_again_until_checked(db, fake_vobiz):
    channels.set_cached_pricing(_pricing(capacity=3))
    fake_vobiz.fail_purchase = {"status": "unknown", "message": "no answer"}
    out = await capacity_planner.purchase(resource_type="cps", quantity=3, request_id="req-00000003",
                                          expected_monthly_cost="4990.00", actor="admin", reason="Faster dialling")
    assert out["purchase"]["status"] == "unknown"
    fake_vobiz.fail_purchase = None
    with pytest.raises(HTTPException) as exc:
        await capacity_planner.purchase(resource_type="cps", quantity=3, request_id="req-00000004",
                                        expected_monthly_cost="4990.00", actor="admin", reason="Faster dialling")
    assert exc.value.detail["error"]["code"] == "purchase_unconfirmed"
    resolved = await capacity_planner.resolve_unknown(uuid.UUID(out["purchase"]["id"]), outcome="failed", actor="admin")
    assert resolved["purchase"]["status"] == "failed"
    ok = await capacity_planner.purchase(resource_type="cps", quantity=3, request_id="req-00000005",
                                         expected_monthly_cost="4990.00", actor="admin", reason="Faster dialling")
    assert ok["ok"] and fake_vobiz.bought == [("cps", 3)]


async def test_overview_reports_held_channels_estimate_and_queue(db, fake_vobiz):
    channels.set_cached_pricing(_pricing(capacity=3, block=10))
    await _numbers(db, A, 2)
    await _numbers(db, B, 1)
    async with db() as session:
        session.add(NumberPurchase(tenant_id=C, e164="+918000000009", status="awaiting_approval", provider="vobiz"))
        await session.commit()
    view = await capacity_planner.overview()
    assert view["concurrency"]["held"] == 3 and view["concurrency"]["freeToHold"] == 0
    assert view["estimate"]["buy"] == 10
    assert view["approvals"][0]["tenantName"] == "Gamma"
    assert view["signals"][0]["level"] == "critical"
    assert {t["name"] for t in view["tenants"]} >= {"Alpha", "Beta"}


# --------------------------------------------------------------------- review fixes


async def test_inbound_reservations_do_not_use_outbound_cps(db):
    channels.set_cached_pricing(_pricing(capacity=10, included=5, cps=1))
    await admission.reserve(A, "inbound-1", provider="vobiz", payload={})  # inbound: no destination
    key, _ = await admission.reserve(B, "out-1", provider="vobiz", payload={"to": "+919000000003"})
    assert key


async def test_an_approved_purchase_still_activating_holds_its_channel(db):
    channels.set_cached_pricing(_pricing(capacity=1))
    async with db() as session:
        session.add(NumberPurchase(tenant_id=A, e164="+918000000011", status="paid", provider="vobiz"))
        await session.commit()
    decision = await capacity_policy.decide_number_purchase(B)
    assert decision["approved"] is False and decision["reason"] == "needs_capacity"
    async with db() as session:
        assert (await session.execute(select(CapacityIncident.kind))).scalars().all() == ["number_blocked"]


async def test_a_second_purchase_is_refused_while_one_is_in_progress(db, fake_vobiz):
    channels.set_cached_pricing(_pricing(capacity=3))
    async with db() as session:
        session.add(VobizCapacityPurchase(request_id="other-admin-click", resource_type="concurrent_calls", quantity=10,
                                          status="pending", actor="admin2", reason="parallel click",
                                          created_at=channels._utcnow(), updated_at=channels._utcnow()))
        await session.commit()
    with pytest.raises(HTTPException) as exc:
        await capacity_planner.purchase(resource_type="concurrent_calls", quantity=10, request_id="req-00000010",
                                        expected_monthly_cost="4990.00", actor="admin", reason="Need more lines")
    assert exc.value.detail["error"]["code"] == "purchase_unconfirmed" and fake_vobiz.bought == []


async def test_capacity_rises_after_a_purchase_even_if_vobiz_still_shows_the_old_limit(db, fake_vobiz, monkeypatch):
    channels.set_cached_pricing(_pricing(capacity=3))

    async def stale_limits(client=None):
        return {"available": True, "concurrentLimit": 3, "cpsLimit": 1}

    async def stale_live(client=None):
        return {"available": True, "maxConcurrent": 3, "concurrentCalls": 0}

    monkeypatch.setattr(vobiz, "fetch_account_limits", stale_limits)
    monkeypatch.setattr(vobiz, "fetch_platform_concurrency", stale_live)
    out = await capacity_planner.purchase(resource_type="concurrent_calls", quantity=10, request_id="req-00000011",
                                          expected_monthly_cost="4990.00", actor="admin", reason="Need more lines")
    assert out["ok"] and out["applied"]["platformCapacity"] == 13


async def test_a_crash_while_buying_leaves_the_purchase_unknown_not_pending(db, fake_vobiz, monkeypatch):
    channels.set_cached_pricing(_pricing(capacity=3))

    async def boom(*_a, **_k):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(vobiz, "purchase_capacity", boom)
    out = await capacity_planner.purchase(resource_type="cps", quantity=3, request_id="req-00000012",
                                          expected_monthly_cost="4990.00", actor="admin", reason="Faster dialling")
    assert out["ok"] is False and out["purchase"]["status"] == "unknown"


async def test_incident_recording_tolerates_a_non_uuid_tenant(db):
    await capacity_incidents.record("carrier_capacity", "dev-session")
    async with db() as session:
        row = (await session.execute(select(CapacityIncident))).scalar_one()
    assert row.tenant_key == "platform" and row.count == 1


# --------------------------------------------------------------------- independent review fixes


async def test_refund_refuses_when_an_approval_landed_in_between(db, monkeypatch):
    from server.services.saas import number_purchase_admin as admin

    monkeypatch.setattr(admin, "get_session_factory", lambda: db)
    async with db() as session:
        p = NumberPurchase(tenant_id=A, e164="+918000000021", status="awaiting_approval", provider="vobiz")
        session.add(p)
        await session.flush()
        session.add(ProvisionJob(purchase_id=p.id, status="held"))
        await session.commit()
    real_bucket = admin._bucket
    approved = []

    def bucket_then_approve(*args):
        out = real_bucket(*args)
        if not approved:  # an admin approves between the refund's read and its lock
            approved.append(True)
            import sqlite3

            con = sqlite3.connect(db.kw["bind"].url.database)
            con.execute("UPDATE number_purchases SET status='paid' WHERE e164='+918000000021'")
            con.commit()
            con.close()
        return out

    monkeypatch.setattr(admin, "_bucket", bucket_then_approve)
    with pytest.raises(admin.PurchaseAdminError) as exc:
        await admin.refund_purchase(p.id)
    assert exc.value.code == "purchase_changed"


async def test_worker_never_provisions_a_refunded_purchase(db, monkeypatch):
    from server.services.saas import provision_worker

    monkeypatch.setattr(provision_worker, "get_session_factory", lambda: db)

    async def no_maintenance():
        return False

    monkeypatch.setattr(provision_worker, "run_number_maintenance_if_due", no_maintenance)
    async with db() as session:
        p = NumberPurchase(tenant_id=A, e164="+918000000022", status="refunded", provider="vobiz")
        session.add(p)
        await session.flush()
        session.add(ProvisionJob(purchase_id=p.id, status="queued", attempts=0,
                                 created_at=channels._utcnow(), updated_at=channels._utcnow()))
        await session.commit()
    assert await provision_worker.process_one_job() is True
    async with db() as session:
        job = (await session.execute(select(ProvisionJob))).scalar_one()
        purchase = await session.get(NumberPurchase, p.id)
    assert job.status == "cancelled" and purchase.status == "refunded"


async def test_auto_buy_budget_caps_the_total_recurring_cost_not_just_30_days(db, fake_vobiz):
    channels.set_cached_pricing(_pricing(capacity=3))
    await _numbers(db, A, 3)
    await _policy(db, approvalMode="auto", autoBuy=True, autoBuyMonthlyBudgetInr="6000")
    async with db() as session:
        session.add(VobizCapacityPurchase(request_id="old-auto-buy", resource_type="concurrent_calls", quantity=10,
                                          monthly_cost="4990.00", status="succeeded", actor="auto-buy", reason="earlier",
                                          created_at=channels._utcnow() - channels.timedelta(days=60),
                                          updated_at=channels._utcnow()))
        await session.commit()
    decision = await capacity_policy.decide_number_purchase(B)
    assert decision["reason"] == "needs_capacity:over_budget" and fake_vobiz.bought == []


async def test_purchases_needing_attention_keep_their_channel_held(db):
    channels.set_cached_pricing(_pricing(capacity=1))
    async with db() as session:
        session.add(NumberPurchase(tenant_id=A, e164="+918000000023", status="needs_attention", provider="vobiz"))
        await session.commit()
        held = await channels.held_by_tenant(session, _pricing())
    assert held[A]["held"] == 1


async def test_unapproved_purchases_are_refunded_after_the_hold(db, monkeypatch):
    refunded = []

    async def refund_purchase(purchase_id):
        refunded.append(purchase_id)
        return {"ok": True, "refunded": True}

    monkeypatch.setattr("server.services.saas.number_purchase_admin.refund_purchase", refund_purchase)
    async with db() as session:
        old = NumberPurchase(tenant_id=A, e164="+918000000024", status="awaiting_approval", provider="vobiz",
                             created_at=channels._utcnow() - channels.timedelta(days=4))
        new = NumberPurchase(tenant_id=B, e164="+918000000025", status="awaiting_approval", provider="vobiz")
        session.add_all([old, new])
        await session.commit()
    assert await capacity_policy.expire_stale_approvals() == 1
    assert refunded == [old.id]
