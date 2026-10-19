"""Regression tests for wallet-funded number purchase safety."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from server.db.models.entities import Tenant
from server.db.models.phase5_models import PhoneNumber
from server.db.models.saas_models import NumberPurchase, NumberReservation, ProvisionJob, User
from server.services.saas import billing_wallet_service, number_purchase_service
from server.services.saas.provision_worker import (
    _phone_number_status,
    _provider_number_id,
    _queued_job_statement,
)
from server.services.saas.tenant_guard import SubscriberPrincipal


class _ScalarResult:
    def __init__(self, value=None):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _PurchaseSession:
    def __init__(self, *, tenant_id, user, tenant, phone, active_count=0, pending_count=0):
        self.tenant_id = tenant_id
        self.user = user
        self.tenant = tenant
        self.phone = phone
        self.active_count = active_count
        self.pending_count = pending_count
        self.scalar_calls = 0
        self.added = []
        self.commits = 0
        self.get_calls = []
        self.phone_snapshot = {
            key: getattr(phone, key, None)
            for key in (
                "tenant_id",
                "status",
                "billing_source",
                "agent_id",
                "purchase_id",
                "inbound_enabled",
                "outbound_enabled",
            )
        }

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, _exc, _tb):
        if exc_type is not None:
            for key, value in self.phone_snapshot.items():
                setattr(self.phone, key, value)
        return False

    async def get(self, model, _ident, **kwargs):
        self.get_calls.append((model, kwargs))
        if model is User:
            return self.user
        if model is Tenant:
            return self.tenant
        if model is PhoneNumber:
            return self.phone
        return None

    async def scalar(self, _statement):
        self.scalar_calls += 1
        return self.active_count if self.scalar_calls == 1 else self.pending_count

    async def execute(self, _statement):
        return _ScalarResult()

    def add(self, row):
        self.added.append(row)

    async def flush(self):
        for row in self.added:
            if isinstance(row, NumberPurchase) and row.id is None:
                row.id = uuid.uuid4()

    async def commit(self):
        self.commits += 1


def _settings(*, verify_email=True):
    return SimpleNamespace(
        saas_require_email_verification_for_buy=verify_email,
        number_reservation_ttl_minutes=10,
    )


def _session(
    tenant_id,
    *,
    email_verified=True,
    max_numbers=5,
    active_count=0,
    pending_count=0,
):
    user = SimpleNamespace(
        email_verified_at=datetime.now(timezone.utc) if email_verified else None
    )
    tenant = SimpleNamespace(tenant_id=tenant_id, limits={"max_numbers": max_numbers})
    phone = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        released_at=None,
        status="available",
        billing_source="inventory",
        agent_id=None,
        purchase_id=None,
        inbound_enabled=False,
        outbound_enabled=False,
        telnyx_number_id=None,
    )
    return _PurchaseSession(
        tenant_id=tenant_id,
        user=user,
        tenant=tenant,
        phone=phone,
        active_count=active_count,
        pending_count=pending_count,
    )


@pytest.mark.asyncio
async def test_inventory_purchase_checks_email_verification(monkeypatch):
    tenant_id = uuid.uuid4()
    principal = SubscriberPrincipal(uuid.uuid4(), tenant_id, "owner", "buyer@example.test")
    session = _session(tenant_id, email_verified=False)
    factory = lambda: session
    inventory_tid = uuid.uuid4()

    async def inventory_number(_e164):
        return SimpleNamespace(id=session.phone.id)

    async def inventory_tenant():
        return inventory_tid

    monkeypatch.setattr(number_purchase_service, "get_session_factory", lambda: factory)
    monkeypatch.setattr(number_purchase_service, "get_settings", lambda: _settings())
    monkeypatch.setattr(
        number_purchase_service, "subscriber_workspace_tenant_id", lambda _principal: tenant_id
    )
    monkeypatch.setattr(
        "server.services.saas.number_inventory.get_inventory_number", inventory_number
    )
    monkeypatch.setattr(
        "server.services.saas.number_inventory.ensure_platform_inventory_tenant",
        inventory_tenant,
    )

    with pytest.raises(ValueError, match="verification_required"):
        await number_purchase_service._purchase_from_inventory(
            principal,
            e164="+14155550100",
            country_code="US",
            assign_agent_id=None,
        )

    assert session.commits == 0
    assert not any(model is PhoneNumber for model, _kwargs in session.get_calls)


@pytest.mark.asyncio
async def test_inventory_purchase_respects_zero_number_limit_and_locks_tenant(monkeypatch):
    tenant_id = uuid.uuid4()
    principal = SubscriberPrincipal(uuid.uuid4(), tenant_id, "owner", "buyer@example.test")
    session = _session(tenant_id, max_numbers=0, active_count=0)
    inventory_tid = uuid.uuid4()

    async def inventory_number(_e164):
        return SimpleNamespace(id=session.phone.id)

    async def inventory_tenant():
        return inventory_tid

    monkeypatch.setattr(number_purchase_service, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(number_purchase_service, "get_settings", lambda: _settings())
    monkeypatch.setattr(
        number_purchase_service, "subscriber_workspace_tenant_id", lambda _principal: tenant_id
    )
    monkeypatch.setattr(
        "server.services.saas.number_inventory.get_inventory_number", inventory_number
    )
    monkeypatch.setattr(
        "server.services.saas.number_inventory.ensure_platform_inventory_tenant",
        inventory_tenant,
    )

    with pytest.raises(ValueError, match="number_limit"):
        await number_purchase_service._purchase_from_inventory(
            principal,
            e164="+14155550100",
            country_code="US",
            assign_agent_id=None,
        )

    tenant_reads = [kwargs for model, kwargs in session.get_calls if model is Tenant]
    assert tenant_reads == [{"with_for_update": True}]
    assert session.commits == 0


@pytest.mark.asyncio
async def test_pending_carrier_purchases_count_toward_number_limit():
    tenant_id = uuid.uuid4()
    session = _session(tenant_id, max_numbers=1, active_count=0, pending_count=1)

    with pytest.raises(ValueError, match="number_limit"):
        await number_purchase_service._assert_number_purchase_eligibility(
            session,
            tenant_id=tenant_id,
            user_id=uuid.uuid4(),
            workspace_tenant_id=tenant_id,
            settings=_settings(),
        )

    assert session.scalar_calls == 2
    tenant_reads = [kwargs for model, kwargs in session.get_calls if model is Tenant]
    assert tenant_reads == [{"with_for_update": True}]


@pytest.mark.asyncio
async def test_carrier_balance_warning_does_not_log_phone_number(monkeypatch, caplog):
    from server.services import telephony, telnyx_client

    phone = "+14155550100"

    class _Client:
        async def get_balance(self):
            return {"available_credit": "0.50"}

    monkeypatch.setattr(telephony, "active_telephony_provider", lambda: "telnyx")
    monkeypatch.setattr(telnyx_client, "TelnyxClient", _Client)

    with caplog.at_level("WARNING", logger=number_purchase_service.__name__):
        with pytest.raises(ValueError, match="carrier_balance_exhausted"):
            await number_purchase_service.assert_carrier_can_buy(phone)

    assert phone not in caplog.text


@pytest.mark.asyncio
async def test_inventory_transfer_and_wallet_debit_commit_together(monkeypatch):
    tenant_id = uuid.uuid4()
    inventory_tid = uuid.uuid4()
    principal = SubscriberPrincipal(uuid.uuid4(), tenant_id, "owner", "buyer@example.test")
    session = _session(tenant_id)
    session.phone.tenant_id = inventory_tid
    session.phone_snapshot["tenant_id"] = inventory_tid
    debit_calls = []

    async def inventory_number(_e164):
        return SimpleNamespace(id=session.phone.id)

    async def inventory_tenant():
        return inventory_tid

    async def debit_in_session(db, db_tenant_id, *, user_id, purchase_id):
        assert db is session
        assert db_tenant_id == tenant_id
        assert session.commits == 0
        debit_calls.append((user_id, purchase_id))
        return {"ok": True}

    monkeypatch.setattr(number_purchase_service, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(number_purchase_service, "get_settings", lambda: _settings())
    monkeypatch.setattr(
        number_purchase_service, "subscriber_workspace_tenant_id", lambda _principal: tenant_id
    )
    monkeypatch.setattr(
        "server.services.saas.number_inventory.get_inventory_number", inventory_number
    )
    monkeypatch.setattr(
        "server.services.saas.number_inventory.ensure_platform_inventory_tenant",
        inventory_tenant,
    )
    monkeypatch.setattr(
        billing_wallet_service, "debit_did_purchase_in_session", debit_in_session
    )
    monkeypatch.setattr(
        "server.services.saas.billing_rates.rates_with_derived_inr",
        lambda: {"did_monthly_usd_cents": 400, "did_monthly_inr_paise": 40000},
    )

    result = await number_purchase_service._purchase_from_inventory(
        principal,
        e164="+14155550100",
        country_code="US",
        assign_agent_id=None,
    )

    purchase = next(row for row in session.added if isinstance(row, NumberPurchase))
    assert result["status"] == "provisioned"
    assert session.phone.tenant_id == tenant_id
    assert session.phone.purchase_id == purchase.id
    assert purchase.status == "provisioned"
    assert debit_calls == [(principal.user_id, purchase.id)]
    assert session.commits == 1


@pytest.mark.asyncio
async def test_insufficient_wallet_does_not_commit_inventory_transfer(monkeypatch):
    tenant_id = uuid.uuid4()
    inventory_tid = uuid.uuid4()
    principal = SubscriberPrincipal(uuid.uuid4(), tenant_id, "owner", "buyer@example.test")
    session = _session(tenant_id)
    session.phone.tenant_id = inventory_tid
    session.phone_snapshot["tenant_id"] = inventory_tid

    async def inventory_number(_e164):
        return SimpleNamespace(id=session.phone.id)

    async def inventory_tenant():
        return inventory_tid

    async def insufficient(_db, _tenant_id, *, user_id, purchase_id):
        raise HTTPException(status_code=402, detail="insufficient_balance")

    monkeypatch.setattr(number_purchase_service, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(number_purchase_service, "get_settings", lambda: _settings())
    monkeypatch.setattr(
        number_purchase_service, "subscriber_workspace_tenant_id", lambda _principal: tenant_id
    )
    monkeypatch.setattr(
        "server.services.saas.number_inventory.get_inventory_number", inventory_number
    )
    monkeypatch.setattr(
        "server.services.saas.number_inventory.ensure_platform_inventory_tenant",
        inventory_tenant,
    )
    monkeypatch.setattr(
        billing_wallet_service, "debit_did_purchase_in_session", insufficient
    )

    with pytest.raises(HTTPException) as caught:
        await number_purchase_service._purchase_from_inventory(
            principal,
            e164="+14155550100",
            country_code="US",
            assign_agent_id=None,
        )

    assert caught.value.status_code == 402
    assert session.commits == 0
    assert session.phone.tenant_id == inventory_tid
    assert session.phone.purchase_id is None


@pytest.mark.asyncio
async def test_carrier_purchase_persists_debit_and_job_in_one_transaction(monkeypatch):
    tenant_id = uuid.uuid4()
    principal = SubscriberPrincipal(uuid.uuid4(), tenant_id, "owner", "buyer@example.test")
    session = _session(tenant_id)
    debit_calls = []

    async def no_inventory(*_args, **_kwargs):
        return None

    async def no_op(*_args, **_kwargs):
        return None

    async def inventory_tenant():
        return uuid.uuid4()

    async def debit_in_session(db, db_tenant_id, *, user_id, purchase_id):
        assert db is session
        assert db_tenant_id == tenant_id
        assert session.commits == 0
        assert any(isinstance(row, ProvisionJob) for row in session.added)
        debit_calls.append((user_id, purchase_id))
        return {"ok": True}

    monkeypatch.setattr(number_purchase_service, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(number_purchase_service, "get_settings", lambda: _settings())
    monkeypatch.setattr(number_purchase_service, "_active_reservation_conflict", no_op)
    monkeypatch.setattr("server.services.telephony.active_telephony_provider", lambda: "telnyx")
    monkeypatch.setattr(number_purchase_service, "_purchase_from_inventory", no_inventory)
    monkeypatch.setattr(number_purchase_service, "assert_carrier_can_buy", no_op)
    monkeypatch.setattr(
        number_purchase_service,
        "subscriber_workspace_tenant_id",
        lambda _principal: tenant_id,
    )
    monkeypatch.setattr(
        "server.services.saas.billing_wallet_service.assert_wallet_can_afford_did",
        no_op,
    )
    monkeypatch.setattr(
        "server.services.saas.billing_wallet_service.debit_did_purchase_in_session",
        debit_in_session,
    )
    monkeypatch.setattr(
        "server.services.saas.number_inventory.ensure_platform_inventory_tenant",
        inventory_tenant,
    )
    monkeypatch.setattr(
        "server.services.saas.billing_rates.rates_with_derived_inr",
        lambda: {"did_monthly_usd_cents": 400, "did_monthly_inr_paise": 40000},
    )

    result = await number_purchase_service.purchase_with_wallet(
        principal,
        e164="+14155550100",
        country_code="US",
        assign_agent_id=None,
    )

    purchase = next(row for row in session.added if isinstance(row, NumberPurchase))
    reservation = next(row for row in session.added if isinstance(row, NumberReservation))
    job = next(row for row in session.added if isinstance(row, ProvisionJob))
    assert result["purchaseId"] == str(purchase.id)
    assert reservation.purchase_id == purchase.id
    assert job.purchase_id == purchase.id
    assert purchase.status == "paid"
    assert debit_calls == [(principal.user_id, purchase.id)]
    assert session.commits == 1


@pytest.mark.asyncio
async def test_vobiz_unavailable_number_is_rejected_before_wallet_debit(monkeypatch):
    tenant_id = uuid.uuid4()
    principal = SubscriberPrincipal(uuid.uuid4(), tenant_id, "owner", "buyer@example.test")
    debit_calls = []
    carrier_order_checks = []

    async def no_reservation_conflict(_e164):
        return False

    async def wallet_affordable(_tenant_id):
        return None

    async def debit(*_args, **_kwargs):
        debit_calls.append(True)
        raise AssertionError("wallet must not be debited for unavailable provider inventory")

    async def inventory_unavailable(_e164, _country):
        raise ValueError("number_unavailable")

    async def carrier_check(_e164):
        carrier_order_checks.append(True)

    monkeypatch.setattr(number_purchase_service, "get_settings", lambda: _settings())
    monkeypatch.setattr(number_purchase_service, "get_session_factory", lambda: lambda: None)
    monkeypatch.setattr(number_purchase_service, "_active_reservation_conflict", no_reservation_conflict)
    monkeypatch.setattr(
        "server.services.telephony.active_telephony_provider",
        lambda: "vobiz",
    )
    monkeypatch.setattr(
        "server.services.saas.billing_wallet_service.assert_wallet_can_afford_did",
        wallet_affordable,
    )
    monkeypatch.setattr(
        "server.services.saas.billing_wallet_service.debit_did_purchase_in_session",
        debit,
    )
    monkeypatch.setattr(
        number_purchase_service,
        "_assert_vobiz_inventory_number_available",
        inventory_unavailable,
    )
    monkeypatch.setattr(number_purchase_service, "assert_carrier_can_buy", carrier_check)

    with pytest.raises(ValueError, match="number_unavailable"):
        await number_purchase_service.purchase_with_wallet(
            principal,
            e164="+919876543210",
            country_code="IN",
        )

    assert debit_calls == []
    assert carrier_order_checks == []


def test_provision_worker_claim_uses_skip_locked():
    sql = str(_queued_job_statement().compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE SKIP LOCKED" in sql


def test_provision_worker_uses_only_carrier_returned_number_ids():
    assert _provider_number_id({"phone_number_id": "carrier-real-id"}) == "carrier-real-id"
    assert _provider_number_id({"phone_number_id": None}) is None
    assert _provider_number_id({}) is None
    assert _phone_number_status("carrier-real-id") == "active"
    assert _phone_number_status(None) == "pending"
