"""Phone-number purchase, renewal, release and sub-account hardening.

Offline: real SQLAlchemy persistence on in-memory SQLite, fake carrier. No real
numbers, wallets or Vobiz accounts are touched.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from server.db.models.entities import Base, Tenant
from server.db.models.phase5_models import PhoneNumber
from server.db.models.saas_models import (
    BillingRateVersion,
    BillingWallet,
    BillingWalletTransaction,
    NumberPurchase,
    NumberReservation,
    ProvisionJob,
    TenantTeardownJob,
    User,
    VobizSubaccount,
)
from server.services.saas import number_purchase_service as nps
from server.services.saas.tenant_guard import SubscriberPrincipal

TID = UUID(int=0xA21)  # hex letters: SQLite NUMERIC affinity mangles all-digit UUIDs
OTHER = UUID(int=0xA22)
PHONE = "+919876543210"
RATES = {
    "did_monthly_usd_cents": 400,
    "did_monthly_usd_micros": 4_000_000,
    "did_monthly_inr_paise": 38_000,
}


@compiles(JSONB, "sqlite")
def _sqlite_json(_type, _compiler, **_kw):
    return "JSON"


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
async def db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [
        Tenant, User, VobizSubaccount, PhoneNumber, NumberPurchase, NumberReservation,
        ProvisionJob, BillingWallet, BillingWalletTransaction, TenantTeardownJob, BillingRateVersion,
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda s: Base.metadata.create_all(s, tables=[m.__table__ for m in tables]))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add_all([
            Tenant(tenant_id=TID, name="Buyer", status="active"),
            Tenant(tenant_id=OTHER, name="Other buyer", status="active"),
        ])
        await session.commit()
    for target in (
        "server.services.saas.number_purchase_service.get_session_factory",
        "server.services.saas.reservation_cleanup.get_session_factory",
        "server.services.saas.number_rental.get_session_factory",
        "server.services.saas.billing_wallet_service.get_session_factory",
        "server.services.saas.number_inventory.get_session_factory",
        "server.services.saas.voice_kyc_service.get_session_factory",
        "server.services.saas.provision_worker.get_session_factory",
    ):
        monkeypatch.setattr(target, lambda: factory)

    async def rates():
        return dict(RATES)

    monkeypatch.setattr("server.services.saas.billing_rates.load_current_rates", rates)
    monkeypatch.setattr("server.services.saas.activity_log.record_event", AsyncMock())
    yield factory
    await engine.dispose()


async def _purchase(factory, *, tenant_id=TID, status="paid", reservation_expired=True, created_at=None):
    async with factory() as session:
        purchase = NumberPurchase(
            tenant_id=tenant_id, e164=PHONE, status=status, provider="vobiz",
            created_at=created_at or _now(),
        )
        session.add(purchase)
        await session.flush()
        session.add(NumberReservation(
            e164=PHONE, tenant_id=tenant_id, purchase_id=purchase.id,
            expires_at=_now() + (timedelta(minutes=-5) if reservation_expired else timedelta(minutes=10)),
        ))
        await session.commit()
        return purchase.id


# --- Reservations / double-sell ------------------------------------------------


async def test_purge_keeps_hold_of_in_flight_purchase_past_ttl(db):
    from server.services.saas.reservation_cleanup import purge_expired_reservations

    await _purchase(db, status="provisioning")
    assert await purge_expired_reservations() == 0
    async with db() as session:
        assert (await session.execute(select(NumberReservation))).scalar_one()


async def test_purge_removes_expired_hold_of_settled_purchase(db):
    from server.services.saas.reservation_cleanup import purge_expired_reservations

    await _purchase(db, status="failed")
    assert await purge_expired_reservations() == 1


async def test_in_flight_purchase_blocks_other_tenant_even_without_reservation(db):
    pid = await _purchase(db, status="needs_attention")
    async with db() as session:
        for row in (await session.execute(select(NumberReservation))).scalars():
            await session.delete(row)
        await session.commit()
    conflict = await nps._active_reservation_conflict(PHONE)
    assert conflict == {"tenant_id": TID, "purchase_id": pid, "status": "needs_attention"}


def _patch_purchase_gates(monkeypatch, debit):
    async def ok(*_a, **_k):
        return None

    monkeypatch.setattr("server.services.saas.billing_wallet_service.assert_wallet_can_afford_did", ok)
    monkeypatch.setattr("server.services.saas.billing_wallet_service.debit_did_purchase_in_session", debit)
    monkeypatch.setattr("server.services.telephony.active_telephony_provider", lambda: "vobiz")
    monkeypatch.setattr("server.services.saas.voice_kyc_service.assert_voice_kyc_approved", ok)
    monkeypatch.setattr(nps, "_assert_vobiz_inventory_number_available", ok)
    monkeypatch.setattr(nps, "assert_carrier_can_buy", ok)


async def test_double_submit_by_same_tenant_replays_without_second_debit(db, monkeypatch):
    pid = await _purchase(db, status="paid", reservation_expired=False)
    debit = AsyncMock(side_effect=AssertionError("must not debit twice"))
    _patch_purchase_gates(monkeypatch, debit)
    principal = SubscriberPrincipal(uuid4(), TID, "owner", "buyer@example.test")
    result = await nps.purchase_with_wallet(principal, e164=PHONE, country_code="IN")
    assert result["purchaseId"] == str(pid) and result["replayed"] is True
    assert result["provisioning"] is True and result["status"] == "paid"
    debit.assert_not_awaited()


async def test_other_tenant_cannot_buy_number_held_by_in_flight_purchase(db, monkeypatch):
    await _purchase(db, status="provisioning")
    debit = AsyncMock(side_effect=AssertionError("must not debit"))
    _patch_purchase_gates(monkeypatch, debit)
    principal = SubscriberPrincipal(uuid4(), OTHER, "owner", "other@example.test")
    with pytest.raises(ValueError, match="number_reserved"):
        await nps.purchase_with_wallet(principal, e164=PHONE, country_code="IN")
    debit.assert_not_awaited()


# --- Price: never sell below carrier cost --------------------------------------


@pytest.mark.parametrize("row,expected", [
    ({"setup_fee": 100, "monthly_fee": 1.0, "currency": "INR"}, False),
    ({"setup_fee": 700, "monthly_fee": 1.0, "currency": "INR"}, True),
    ({"setup_fee": "0", "monthly_fee": "500", "currency": "INR"}, True),
    ({"setup_fee": 0, "monthly_fee": 5, "currency": "USD"}, True),
    ({"setup_fee": 0, "monthly_fee": 1, "currency": "USD"}, False),
    ({"monthly_fee": 999, "currency": "EUR"}, False),
    ({}, False),
])
def test_carrier_charge_guard(row, expected):
    assert nps.carrier_charge_exceeds_retail(row, RATES) is expected


async def test_premium_carrier_number_is_refused_before_debit(db, monkeypatch):
    class _Client:
        async def search_available_numbers(self, **_kw):
            return [{"e164": PHONE, "setup_fee": 5000, "monthly_fee": 1, "currency": "INR"}]

    monkeypatch.setattr("server.services.vobiz_client.VobizClient", _Client)
    # A distinct code so the operator learns the rent is below the carrier price;
    # the tenant copy is the same as "unavailable" (see number_purchase_errors).
    with pytest.raises(ValueError, match="carrier_price_above_retail") as info:
        await nps._assert_vobiz_inventory_number_available(PHONE, "IN")
    assert info.value.context == {"carrierPrice": 5001.0, "retailPrice": 380.0, "currency": "INR"}


# --- Purchase status shown to the tenant ---------------------------------------


async def test_purchase_status_hides_internal_error_and_reports_refund(db):
    pid = await _purchase(db, status="failed")
    async with db() as session:
        session.add(ProvisionJob(purchase_id=pid, status="failed",
                                 last_error={"code": "provider_provision_failed", "error_type": "VobizApiError"}))
        await session.commit()
    row = await nps.get_purchase(pid, TID)
    assert row["lastError"]["code"] == "provider_provision_failed" and row["refunded"] is False
    assert set(row["lastError"]) == {"code", "message"}
    assert "refund is being processed" in row["message"]
    assert "VobizApiError" not in str(row) and "vobiz" not in row["message"].lower()
    async with db() as session:
        session.add(BillingWalletTransaction(tenant_id=TID, amount_cents=400, kind="did_refund",
                                             reference_id=f"did_refund:{pid}"))
        await session.commit()
    refunded_row = await nps.get_purchase(pid, TID)
    assert refunded_row["refunded"] is True
    assert "refunded the charge to your wallet" in refunded_row["message"]
    assert await nps.get_purchase(pid, OTHER) is None


async def test_kyc_revoked_before_provisioning_fails_and_refunds(db, monkeypatch):
    from server.services.saas import billing_wallet_service, provision_worker, voice_kyc_service

    pid = await _purchase(db, status="paid")
    async with db() as session:
        session.add(ProvisionJob(purchase_id=pid, status="queued", attempts=0))
        await session.commit()
    monkeypatch.setattr(voice_kyc_service, "provision_tenant_number",
                        AsyncMock(side_effect=HTTPException(status_code=403, detail="voice_kyc_required")))
    refund = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(billing_wallet_service, "refund_did_purchase", refund)
    assert await provision_worker.process_one_job()
    refund.assert_awaited_once()
    async with db() as session:
        assert (await session.get(NumberPurchase, pid)).status == "failed"
        assert (await session.execute(select(NumberReservation))).scalar_one_or_none() is None


# --- Monthly rental -------------------------------------------------------------


def test_due_period_and_month_clamping():
    from server.services.saas.number_rental import add_months, due_period

    anchor = datetime(2026, 1, 31, 12, tzinfo=timezone.utc)
    assert add_months(anchor, 1) == datetime(2026, 2, 28, 12, tzinfo=timezone.utc)
    assert due_period(anchor, datetime(2026, 2, 28, 11, tzinfo=timezone.utc)) == 0
    assert due_period(anchor, datetime(2026, 2, 28, 12, tzinfo=timezone.utc)) == 1
    assert due_period(anchor, datetime(2026, 5, 1, tzinfo=timezone.utc)) == 3


async def _rented_number(factory, *, purchased_at):
    pid = await _purchase(factory, status="active", created_at=purchased_at)
    async with factory() as session:
        pn = PhoneNumber(tenant_id=TID, e164=PHONE, status="active", purchase_id=pid,
                         billing_source="wallet", inbound_enabled=True, outbound_enabled=True)
        session.add(pn)
        await session.commit()
        return pn.id


async def _set_wallet(factory, cents):
    async with factory() as session:
        wallet = await session.get(BillingWallet, TID)
        if wallet is None:
            wallet = BillingWallet(tenant_id=TID, balance_cents=0, balance_inr_paise=0, currency="usd")
            session.add(wallet)
        wallet.balance_cents = cents
        await session.commit()


async def test_rental_charges_each_period_once_and_suspends_then_restores(db):
    from server.services.saas.number_rental import SUSPENDED_STATUS, renew_due_numbers

    nid = await _rented_number(db, purchased_at=_now() - timedelta(days=40))
    await _set_wallet(db, 1000)
    first = await renew_due_numbers()
    again = await renew_due_numbers()
    assert first["charged"] == 1 and again["charged"] == 0
    async with db() as session:
        txs = (await session.execute(select(BillingWalletTransaction).where(
            BillingWalletTransaction.kind == "did_rental"))).scalars().all()
        assert len(txs) == 1 and txs[0].amount_cents == -400
        assert txs[0].reference_id == f"did_rent:{nid}:1"
        assert (await session.get(BillingWallet, TID)).balance_cents == 600

    # Next period with an empty wallet: suspended, not released, no partial debit.
    later = _now() + timedelta(days=31)
    await _set_wallet(db, 100)
    assert (await renew_due_numbers(now=later))["suspended"] == 1
    async with db() as session:
        pn = await session.get(PhoneNumber, nid)
        assert pn.status == SUSPENDED_STATUS and not pn.inbound_enabled and pn.released_at is None
        assert (await session.get(BillingWallet, TID)).balance_cents == 100

    await _set_wallet(db, 1000)
    assert (await renew_due_numbers(now=later))["restored"] == 1
    async with db() as session:
        pn = await session.get(PhoneNumber, nid)
        assert pn.status == "active" and pn.inbound_enabled and pn.outbound_enabled


async def test_rental_never_back_bills_missed_periods(db):
    from server.services.saas.number_rental import renew_due_numbers

    await _rented_number(db, purchased_at=_now() - timedelta(days=200))
    await _set_wallet(db, 100_000)
    assert (await renew_due_numbers())["charged"] == 1


async def test_rental_skips_first_month(db):
    from server.services.saas.number_rental import renew_due_numbers

    await _rented_number(db, purchased_at=_now() - timedelta(days=3))
    await _set_wallet(db, 1000)
    assert (await renew_due_numbers())["charged"] == 0


# --- Monthly rent price (one admin setting for purchase and renewals) ----------


async def _rate_version(factory, version, *, inr_paise, effective_from, active=False):
    cents = round(inr_paise / 95)
    async with factory() as session:
        session.add(BillingRateVersion(
            version=version, pstn_rate_usd_cents_per_min=5, web_agent_rate_usd_cents_per_min=2,
            did_monthly_usd_cents=cents, did_monthly_usd_micros=cents * 10_000,
            did_monthly_inr_paise=inr_paise, fx_rate_inr=95, effective_from=effective_from,
            created_by="admin@example.test", reason="number rent change", is_active=active,
        ))
        await session.commit()


async def _set_inr_wallet(factory, paise):
    async with factory() as session:
        wallet = await session.get(BillingWallet, TID)
        if wallet is None:
            wallet = BillingWallet(tenant_id=TID, balance_cents=0, balance_inr_paise=0, currency="inr")
            session.add(wallet)
        wallet.balance_inr_paise = paise
        wallet.currency = "inr"
        await session.commit()


async def _rent_rows(factory, kind="did_rental"):
    async with factory() as session:
        return (await session.execute(select(BillingWalletTransaction).where(
            BillingWalletTransaction.kind == kind).order_by(BillingWalletTransaction.created_at))).scalars().all()


async def test_purchase_charges_admin_monthly_rent_and_quotes_renewal(db, monkeypatch):
    from server.services.saas import billing_wallet_service

    real_debit = billing_wallet_service.debit_did_purchase_in_session
    _patch_purchase_gates(monkeypatch, real_debit)
    await _set_inr_wallet(db, 100_000)
    buyer = uuid4()
    async with db() as session:
        session.add(User(user_id=buyer, email="buyer@example.test", password_hash="x", email_verified_at=_now()))
        await session.commit()
    principal = SubscriberPrincipal(buyer, TID, "owner", "buyer@example.test")
    result = await nps.purchase_with_wallet(principal, e164=PHONE, country_code="IN")
    rows = await _rent_rows(db, "did_purchase")
    assert len(rows) == 1 and rows[0].amount_inr_paise == -38_000 and rows[0].amount_cents == 0
    assert result["chargedInr"] == 380.0 and result["didMonthlyInr"] == 380.0
    renews = datetime.fromisoformat(result["renewsOn"])
    assert timedelta(days=27) < renews - _now() < timedelta(days=32)
    async with db() as session:
        assert (await session.get(BillingWallet, TID)).balance_inr_paise == 62_000


async def test_zero_rent_purchase_debits_nothing(db, monkeypatch):
    from server.services.saas.billing_wallet_service import debit_did_purchase_in_session

    async def free():
        return {**RATES, "did_monthly_usd_cents": 0, "did_monthly_usd_micros": 0, "did_monthly_inr_paise": 0}

    monkeypatch.setattr("server.services.saas.billing_rates.load_current_rates", free)
    pid = await _purchase(db)
    async with db() as session:
        out = await debit_did_purchase_in_session(session, TID, user_id=None, purchase_id=pid)
        await session.commit()
    assert out["free"] is True and out["amountInrPaise"] == 0
    assert await _rent_rows(db, "did_purchase") == []


async def test_renewal_charges_price_in_force_on_renewal_date(db):
    from server.services.saas import activity_log
    from server.services.saas.number_rental import renew_due_numbers

    purchased = _now() - timedelta(days=40)  # period 1 began ~10 days ago
    await _rate_version(db, 1, inr_paise=38_000, effective_from=_now() - timedelta(days=400))
    # Saved mid-period (after this period's renewal date): must wait for the next renewal.
    await _rate_version(db, 2, inr_paise=50_000, effective_from=_now() - timedelta(days=5), active=True)
    nid = await _rented_number(db, purchased_at=purchased)
    await _set_inr_wallet(db, 200_000)

    assert (await renew_due_numbers())["charged"] == 1
    rows = await _rent_rows(db)
    assert [r.amount_inr_paise for r in rows] == [-38_000]
    payload = activity_log.record_event.await_args.kwargs["payload"]
    assert payload["rateVersion"] == 1 and payload["amountInrPaise"] == 38_000
    assert payload["reference"] == f"did_rent:{nid}:1"

    # The next renewal is the first to use the new price.
    assert (await renew_due_numbers(now=_now() + timedelta(days=31)))["charged"] == 1
    rows = await _rent_rows(db)
    assert [r.amount_inr_paise for r in rows] == [-38_000, -50_000]
    assert activity_log.record_event.await_args.kwargs["payload"]["rateVersion"] == 2
    async with db() as session:
        assert (await session.get(BillingWallet, TID)).balance_inr_paise == 200_000 - 88_000


async def test_price_change_before_renewal_date_applies_to_that_renewal(db):
    from server.services.saas.number_rental import renew_due_numbers

    await _rate_version(db, 1, inr_paise=38_000, effective_from=_now() - timedelta(days=400))
    await _rate_version(db, 2, inr_paise=45_000, effective_from=_now() - timedelta(days=20), active=True)
    await _rented_number(db, purchased_at=_now() - timedelta(days=40))
    await _set_inr_wallet(db, 200_000)
    assert (await renew_due_numbers())["charged"] == 1
    assert [r.amount_inr_paise for r in await _rent_rows(db)] == [-45_000]


async def test_zero_rent_renewal_debits_nothing_and_restores_line(db):
    from server.services.saas.number_rental import SUSPENDED_STATUS, renew_due_numbers

    await _rate_version(db, 1, inr_paise=0, effective_from=_now() - timedelta(days=400), active=True)
    nid = await _rented_number(db, purchased_at=_now() - timedelta(days=40))
    async with db() as session:
        (await session.get(PhoneNumber, nid)).status = SUSPENDED_STATUS
        await session.commit()
    await _set_inr_wallet(db, 0)
    summary = await renew_due_numbers()
    assert summary["charged"] == 0 and summary["free"] == 1 and summary["restored"] == 1
    assert await _rent_rows(db) == []


async def test_renewal_off_switch(db, monkeypatch):
    from server.services.saas.number_rental import renew_due_numbers

    monkeypatch.setenv("DID_RENTAL_RENEWAL_ENABLED", "false")
    await _rented_number(db, purchased_at=_now() - timedelta(days=40))
    await _set_wallet(db, 1000)
    assert (await renew_due_numbers())["charged"] == 0
    assert await _rent_rows(db) == []


async def test_renewing_number_count_and_next_renewal_date(db):
    from server.services.saas.number_rental import next_renewal_at, renewing_number_count

    await _rented_number(db, purchased_at=_now() - timedelta(days=40))
    assert await renewing_number_count() == 1
    anchor = datetime(2026, 1, 31, 9, tzinfo=timezone.utc)
    assert next_renewal_at(anchor, datetime(2026, 3, 5, tzinfo=timezone.utc)) == datetime(2026, 3, 31, 9, tzinfo=timezone.utc)
    assert next_renewal_at(anchor, anchor) == datetime(2026, 2, 28, 9, tzinfo=timezone.utc)


# --- Release and teardown -------------------------------------------------------


@pytest.fixture
def child_carrier(monkeypatch, db):
    from server.services import vobiz_client

    key = Fernet.generate_key().decode()
    monkeypatch.setattr("server.services.saas.voice_kyc_service.get_settings",
                        lambda: SimpleNamespace(vobiz_subaccount_encryption_key=key))
    parent = SimpleNamespace(auth_id="MA_test", cfg={"auth_token": "test-parent"}, configured=True,
                             delete_customer_subaccount=AsyncMock(return_value={}))
    child = SimpleNamespace(auth_id="SA_test", cfg={}, configured=True,
                            release_owned_number=AsyncMock(return_value={"status": "pending_release"}),
                            list_account_numbers=AsyncMock(return_value=[{"e164": PHONE, "status": "pending_release"}]))

    def client(cfg=None):
        return parent if cfg is None else child

    monkeypatch.setattr(vobiz_client, "VobizClient", client)
    monkeypatch.setattr("server.services.saas.number_inventory.ensure_platform_inventory_tenant",
                        AsyncMock(return_value=OTHER))
    return parent, child, key


async def _subaccount(factory, key):
    from server.services.saas.voice_kyc_service import encrypt_subaccount_token

    async with factory() as session:
        session.add(VobizSubaccount(
            tenant_id=TID, auth_id="SA_test", parent_auth_id="MA_test",
            encrypted_auth_token=encrypt_subaccount_token(TID, "test-child"),
            business_type="llp", account_name="Example LLP", account_email="o@example.test",
            provisioning_status="active", kyc_status="verified", kyc_calls_blocked=False,
            account_enabled=True, verifications={},
        ))
        session.add(PhoneNumber(tenant_id=TID, e164=PHONE, status="active", carrier_number_id="real-id",
                                vobiz_account_scope="tenant", vobiz_account_tenant_id=TID))
        await session.commit()


async def test_pending_release_is_not_deleted_twice_and_finalises_later(db, child_carrier):
    from server.services.saas.number_inventory import reconcile_release_pending_numbers

    _, child, key = child_carrier
    await _subaccount(db, key)
    async with db() as session:
        nid = (await session.execute(select(PhoneNumber.id))).scalar_one()
    from server.services.saas.number_inventory import move_to_inventory

    assert (await move_to_inventory(number_id=nid, expected_tenant_id=TID))["status"] == "release_pending"
    assert await reconcile_release_pending_numbers() == 0
    child.list_account_numbers.return_value = []
    assert await reconcile_release_pending_numbers() == 1
    child.release_owned_number.assert_awaited_once_with(PHONE)
    async with db() as session:
        pn = await session.get(PhoneNumber, nid)
        assert pn.status == "released" and pn.released_at is not None


async def test_subaccount_close_requires_released_numbers_then_wipes_credentials(db, child_carrier):
    from server.services.saas import voice_kyc_service as svc

    parent, _, key = child_carrier
    await _subaccount(db, key)
    with pytest.raises(svc.VoiceKycError, match="voice_numbers_still_owned"):
        await svc.close_customer_subaccount(TID)
    parent.delete_customer_subaccount.assert_not_awaited()
    async with db() as session:
        pn = (await session.execute(select(PhoneNumber))).scalar_one()
        pn.released_at = _now()
        await session.commit()
    assert await svc.close_customer_subaccount(TID) == "deleted"
    parent.delete_customer_subaccount.assert_awaited_once_with("SA_test")
    async with db() as session:
        row = await session.get(VobizSubaccount, TID)
        assert row.encrypted_auth_token is None and row.provisioning_status == "deleted"
    assert await svc.close_customer_subaccount(TID) == "deleted"
    parent.delete_customer_subaccount.assert_awaited_once()


async def test_teardown_requeues_while_carrier_release_is_pending(db, monkeypatch):
    from server.services.saas import teardown_worker

    async with db() as session:
        # Teardown only ever runs for a workspace past its deletion grace period.
        tenant = await session.get(Tenant, TID)
        tenant.status = "pending_deletion"
        job = TenantTeardownJob(tenant_id=TID, status="queued", stage="carrier_numbers")
        session.add(job)
        await session.commit()
        jid = job.job_id
    monkeypatch.setattr(teardown_worker, "get_session_factory", lambda: db)
    monkeypatch.setattr(teardown_worker, "_stage_carrier_numbers",
                        AsyncMock(side_effect=teardown_worker.CarrierReleasePending(1)))
    assert await teardown_worker.process_one_teardown()
    async with db() as session:
        job = await session.get(TenantTeardownJob, jid)
        assert job.status == "queued" and job.last_error["error"] == "carrier_release_pending"
        locked_until = job.locked_until.replace(tzinfo=timezone.utc) if job.locked_until.tzinfo is None else job.locked_until
        assert locked_until > _now() + timedelta(minutes=20)


# --- Inbound line state and webhook authenticity -------------------------------


def test_line_state_gates_inbound():
    from server.services.saas.telephony_profile import number_line_accepts_inbound

    assert number_line_accepts_inbound(None)
    assert number_line_accepts_inbound({"agent_id": "a"})  # legacy profile without line state
    assert number_line_accepts_inbound({"number_status": "active", "number_inbound_enabled": True})
    assert not number_line_accepts_inbound({"number_status": "active", "number_inbound_enabled": False})
    assert not number_line_accepts_inbound({"number_status": "suspended_unpaid", "number_inbound_enabled": True})
    assert not number_line_accepts_inbound({"number_status": "release_pending", "number_inbound_enabled": True})


def _signed_request(path: str, header: str, token: str, nonce: str = "12345"):
    from starlette.requests import Request

    url = "https://api.example.test" + path
    sig = base64.b64encode(hmac.new(token.encode(), f"{url}.{nonce}".encode(), hashlib.sha256).digest()).decode()
    headers = [(header.encode(), sig.encode()), (b"x-vobiz-signature-v3-nonce", nonce.encode())]
    return Request({"type": "http", "method": "POST", "path": path, "query_string": b"", "headers": headers})


async def test_subaccount_callback_accepts_parent_signed_ma_header(monkeypatch):
    from server.routes import vobiz

    monkeypatch.setattr(vobiz, "public_api_base", lambda: "https://api.example.test")
    monkeypatch.setattr(vobiz, "get_settings", lambda: SimpleNamespace(vobiz_auth_token="parent-token", app_environment="production"))
    monkeypatch.setattr("server.services.dev_secrets_store.dev_secrets_store.effective_secret", lambda _k: None)
    monkeypatch.setattr(vobiz, "_vobiz_callback_tenant_id", AsyncMock(return_value=None))
    await vobiz._verify_vobiz_request(_signed_request("/api/vobiz/hangup", "x-vobiz-signature-ma-v3", "parent-token"), {})
    with pytest.raises(HTTPException) as exc:
        await vobiz._verify_vobiz_request(_signed_request("/api/vobiz/hangup", "x-vobiz-signature-ma-v3", "forged"), {})
    assert exc.value.status_code == 401


async def test_malformed_purchase_id_is_404_not_500():
    from server.routes import app_telephony

    principal = SubscriberPrincipal(uuid4(), TID, "owner", "buyer@example.test")
    with pytest.raises(HTTPException) as exc:
        await app_telephony.get_purchase_status("not-a-uuid", principal)
    assert exc.value.status_code == 404
