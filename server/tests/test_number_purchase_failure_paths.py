"""Every number-purchase failure branch: tenant copy, refunds, admin visibility.

Offline only. Vobiz is reproduced from its documented responses (purchase-from-
inventory: 404 "number not found in inventory", 500 "failed to purchase number"
on a failed balance debit); no live sub-account, KYC session or purchase is made.
"""
from __future__ import annotations

import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from server.db.models.phase5_models import AuditLog, PhoneNumber
from server.db.models.saas_models import (
    BillingWalletTransaction,
    NumberPurchase,
    NumberReservation,
    ProvisionJob,
)
from server.routes import app_telephony
from server.services.saas import number_purchase_admin as admin
from server.services.saas import number_purchase_errors as errors
from server.services.saas import number_purchase_service as nps
from server.services.saas.tenant_guard import SubscriberPrincipal
from server.services.vobiz_client import VobizApiError, VobizClient
from server.tests.test_number_purchase_hardening import PHONE, RATES, TID, _now, _purchase
from server.tests.test_number_purchase_hardening import db as _hardening_db  # noqa: F401

PURCHASE_FAILED_BODY = json.dumps({"error": "internal_server_error", "message": "failed to purchase number"})
NOT_IN_INVENTORY_BODY = json.dumps({"error": "not_found", "message": "number not found in inventory"})


@pytest.fixture
async def db(_hardening_db, monkeypatch):  # noqa: F811 - pytest fixture injection
    """The hardening fixture plus the activity-log table the admin page reads."""
    from server.db.models.entities import Base

    engine = _hardening_db.kw["bind"]
    async with engine.begin() as conn:
        await conn.run_sync(lambda s: Base.metadata.create_all(s, tables=[AuditLog.__table__]))
    for target in (
        "server.services.saas.number_purchase_admin.get_session_factory",
    ):
        monkeypatch.setattr(target, lambda: _hardening_db)
    yield _hardening_db


# ------------------------------------------------------------------ tenant copy


VENDOR_WORDS = ("vobiz", "telnyx", "carrier", "provider", "balance at", "http", "_")


@pytest.mark.parametrize("code", sorted(errors.TENANT_REFUSAL_MESSAGES))
def test_tenant_refusal_copy_is_plain_and_says_not_charged(code):
    message = errors.tenant_refusal_message(code)
    lowered = message.lower()
    assert not any(word in lowered for word in VENDOR_WORDS), (code, message)
    assert "not charged" in lowered or "wasn't charged" in lowered, (code, message)


def test_unknown_refusal_code_never_reaches_tenant_raw():
    message = errors.tenant_refusal_message("some_internal_code_xyz")
    assert "some_internal_code_xyz" not in message and "wasn't charged" in message


@pytest.mark.parametrize("status,code,refunded,needle", [
    ("failed", "carrier_balance_exhausted", True, "refunded the charge"),
    ("failed", "number_taken", True, "taken just before"),
    ("failed", "carrier_auth_failed", True, "refunded the charge"),
    ("failed", "provider_provision_failed", False, "refund is being processed"),
    ("needs_attention", "provider_confirmation_pending", None, "payment is safe"),
    ("provisioning", None, None, "activating your number"),
    ("refunded", None, True, "refunded to your wallet"),
])
def test_tenant_purchase_status_copy(status, code, refunded, needle):
    message = errors.tenant_purchase_message(status, code, refunded)
    assert needle in message.lower()
    assert not any(word in message.lower() for word in ("vobiz", "carrier", "_"))


def test_platform_codes_have_actionable_admin_copy():
    item = errors.admin_explanation("carrier_balance_exhausted")
    assert item["scope"] == "platform" and "Vobiz" in item["title"] and "Top up" in item["action"]
    rent = errors.admin_explanation("carrier_price_above_retail")
    assert rent["href"] == "/dev/admin/billing"
    assert errors.admin_explanation("brand_new_code")["code"] == "brand_new_code"


# ------------------------------------------------------------------ buy route mapping


def _buy_body():
    return app_telephony.BuyNumberBody(e164=PHONE, country="IN")


@pytest.mark.parametrize("raised,status,code", [
    (ValueError("insufficient_balance"), 402, "insufficient_balance"),
    (errors.PurchaseRefused("carrier_price_above_retail", carrierPrice=600.0, retailPrice=564.0, currency="INR"), 409, "carrier_price_above_retail"),
    (errors.PurchaseRefused("carrier_balance_exhausted", carrierBalance=481.78, carrierRequired=600.0, currency="INR"), 503, "carrier_balance_exhausted"),
    (ValueError("carrier_inventory_unavailable"), 503, "carrier_inventory_unavailable"),
    (ValueError("carrier_not_configured"), 503, "carrier_not_configured"),
    (ValueError("number_unavailable"), 409, "number_unavailable"),
    (ValueError("number_reserved"), 409, "number_reserved"),
    (RuntimeError("db exploded"), 503, "purchase_temporarily_unavailable"),
])
async def test_buy_route_maps_each_refusal_to_tenant_copy_and_logs_context(monkeypatch, raised, status, code):
    monkeypatch.setattr(app_telephony, "require_subscriber_permission", lambda *_a: None)
    monkeypatch.setattr("server.services.telephony.active_telephony_provider", lambda: "vobiz")
    monkeypatch.setattr(app_telephony, "purchase_with_wallet", AsyncMock(side_effect=raised))
    events = AsyncMock()
    monkeypatch.setattr("server.services.saas.activity_log.record_event", events)
    principal = SubscriberPrincipal(uuid4(), uuid4(), "owner", "buyer@example.test")
    request = SimpleNamespace(headers={}, client=None)

    with pytest.raises(HTTPException) as info:
        await app_telephony.buy_number(_buy_body(), request, principal)

    assert info.value.status_code == status
    error = info.value.detail["error"]
    assert error["code"] == code and error["charged"] is False
    assert error["message"] == errors.tenant_refusal_message(code)
    assert "vobiz" not in error["message"].lower() and "481" not in error["message"]
    logged = events.await_args.kwargs
    assert logged["action"] == "number.purchase.refused"
    assert logged["payload"]["error"] == code
    if isinstance(raised, errors.PurchaseRefused):
        # Operator-only numbers go to the log, never to the tenant.
        assert logged["payload"]["context"] == raised.context
    if code in errors.PLATFORM_CODES:
        assert logged["outcome"] == "error"


async def test_buy_route_rewrites_kyc_gate_copy(monkeypatch):
    monkeypatch.setattr(app_telephony, "require_subscriber_permission", lambda *_a: None)
    monkeypatch.setattr("server.services.telephony.active_telephony_provider", lambda: "vobiz")
    gate = HTTPException(status_code=403, detail={"error": {"code": "voice_kyc_required", "message": "x", "kycStatus": "pending"}})
    monkeypatch.setattr(app_telephony, "purchase_with_wallet", AsyncMock(side_effect=gate))
    monkeypatch.setattr("server.services.saas.activity_log.record_event", AsyncMock())
    principal = SubscriberPrincipal(uuid4(), uuid4(), "owner", "buyer@example.test")
    with pytest.raises(HTTPException) as info:
        await app_telephony.buy_number(_buy_body(), SimpleNamespace(headers={}, client=None), principal)
    err = info.value.detail["error"]
    assert info.value.status_code == 403 and err["kycStatus"] == "pending"
    assert err["message"] == errors.tenant_refusal_message("voice_kyc_required")


async def test_buy_route_rate_limit_uses_tenant_refusal_contract(monkeypatch):
    monkeypatch.setattr(app_telephony, "require_subscriber_permission", lambda *_a: None)
    monkeypatch.setattr("server.services.telephony.active_telephony_provider", lambda: "vobiz")
    monkeypatch.setattr(app_telephony._buy_limiter, "allow", lambda _key: (False, 42))
    buy = AsyncMock()
    monkeypatch.setattr(app_telephony, "purchase_with_wallet", buy)
    principal = SubscriberPrincipal(uuid4(), uuid4(), "owner", "buyer@example.test")
    with pytest.raises(HTTPException) as info:
        await app_telephony.buy_number(_buy_body(), SimpleNamespace(headers={}, client=None), principal)
    err = info.value.detail["error"]
    assert info.value.status_code == 429 and info.value.headers["Retry-After"] == "42"
    assert err == {"code": "rate_limited", "message": errors.tenant_refusal_message("rate_limited"), "charged": False}
    buy.assert_not_awaited()


# ------------------------------------------------------------------ pre-debit carrier gate


class _ParentVobiz:
    """Stands in for the parent VobizClient: read-only balance + inventory."""

    balance: dict = {"ok": True, "balance": 481.78, "currency": "INR"}
    inventory: list = [{"e164": PHONE, "setup_fee": 100, "monthly_fee": 500, "currency": "INR"}]

    def __init__(self, *_a, **_k):
        self.cfg = {"auth_id": "MA_PARENT", "auth_token": "unit-test"}

    async def get_balance(self):
        return dict(self.balance)

    async def search_available_numbers(self, **_kw):
        return [dict(r) for r in self.inventory]


@pytest.fixture
def parent_vobiz(monkeypatch):
    monkeypatch.setattr("server.services.vobiz_client.VobizClient", _ParentVobiz)
    monkeypatch.setattr("server.services.telephony.active_telephony_provider", lambda: "vobiz")
    monkeypatch.setattr("server.services.telephony.provider_configured", lambda _p: True)
    monkeypatch.setattr("server.services.usage_pricing.resolve_fx_rate_inr", lambda: {"rate": 90.0})
    _ParentVobiz.balance = {"ok": True, "balance": 481.78, "currency": "INR"}
    return _ParentVobiz


async def test_low_carrier_balance_refuses_before_debit_using_exact_number_price(parent_vobiz):
    row = {"e164": PHONE, "setup_fee": 100, "monthly_fee": 500, "currency": "INR"}
    # ₹481.78 is above the generic $1 floor but below this number's ₹600.
    with pytest.raises(ValueError, match="carrier_balance_exhausted") as info:
        await nps.assert_carrier_can_buy(PHONE, carrier_row=row)
    assert info.value.context == {"carrierBalance": 481.78, "carrierRequired": 600.0, "currency": "INR"}
    parent_vobiz.balance = {"ok": True, "balance": 1200.0, "currency": "INR"}
    await nps.assert_carrier_can_buy(PHONE, carrier_row=row)


async def test_unreadable_carrier_balance_is_not_reported_as_empty(parent_vobiz):
    # get_balance reports a failed read as balance 0 with a flag; that is unknown,
    # not "out of money".
    parent_vobiz.balance = {"ok": True, "balance": 0.0, "currency": "INR", "fallback": True}
    await nps.assert_carrier_can_buy(PHONE)
    parent_vobiz.balance = {"ok": False, "balance": 0.0, "currency": "INR", "error": "VobizApiError"}
    await nps.assert_carrier_can_buy(PHONE)


async def test_wallet_never_debited_when_carrier_gate_refuses(db, parent_vobiz, monkeypatch):
    debit = AsyncMock(side_effect=AssertionError("must not debit"))
    monkeypatch.setattr("server.services.saas.billing_wallet_service.assert_wallet_can_afford_did", AsyncMock())
    monkeypatch.setattr("server.services.saas.billing_wallet_service.debit_did_purchase_in_session", debit)
    monkeypatch.setattr("server.services.saas.voice_kyc_service.assert_voice_kyc_approved", AsyncMock())
    rates = dict(RATES, did_monthly_inr_paise=70_000)  # rent ₹700 covers the ₹600 price
    monkeypatch.setattr("server.services.saas.billing_rates.load_current_rates", AsyncMock(return_value=rates))
    principal = SubscriberPrincipal(uuid4(), TID, "owner", "buyer@example.test")
    with pytest.raises(ValueError, match="carrier_balance_exhausted"):
        await nps.purchase_with_wallet(principal, e164=PHONE, country_code="IN")
    debit.assert_not_awaited()
    async with db() as session:
        assert (await session.execute(select(NumberPurchase))).first() is None


async def test_catalog_hides_numbers_priced_above_rent(monkeypatch):
    from server.tests.test_vobiz_number_catalog import _configure_catalog_route

    async def provider_search(_client, *, country, limit):
        return [
            {"e164": "+919876500001", "status": "active", "country": "IN", "auth_id": None,
             "setup_fee": 100, "monthly_fee": 500, "currency": "INR"},
            {"e164": "+919876500002", "status": "active", "country": "IN", "auth_id": None,
             "setup_fee": 0, "monthly_fee": 300, "currency": "INR"},
        ]

    _configure_catalog_route(monkeypatch, search=provider_search)  # rent ₹400
    principal = SubscriberPrincipal(uuid4(), uuid4(), "owner", "buyer@example.test")
    result = await app_telephony.search_numbers(country="IN", principal=principal)
    assert [row["e164"] for row in result["numbers"]] == ["+919876500002"]
    assert "hiddenAboveRetail" not in result  # admin-only diagnostic


# ------------------------------------------------------------------ provisioning failures


def _child_client(responses):
    """A real VobizClient whose transport replays documented responses."""
    client = VobizClient(cfg={"auth_id": "SA_CHILD", "auth_token": "unit-test", "app_id": "", "phone_number": ""})

    async def fake_request(method, path, **_kw):
        key = "purchase" if path.endswith("purchase-from-inventory") else "owned"
        result = responses[key]
        if isinstance(result, Exception):
            raise result
        return result

    client._request = fake_request
    return client


async def _queued(db, **kw):
    pid = await _purchase(db, status="paid", **kw)
    async with db() as session:
        session.add(ProvisionJob(purchase_id=pid, status="queued", attempts=0, updated_at=_now() - timedelta(seconds=1)))
        session.add(BillingWalletTransaction(tenant_id=TID, amount_cents=-400, amount_inr_paise=-56_400,
                                             kind="did_purchase", reference_id=f"did:{pid}"))
        await session.commit()
    return pid


@pytest.fixture
def worker(db, monkeypatch):
    from server.services.saas import voice_kyc_service

    state = {"client": None}

    async def provision(_tid, e164):
        result = await state["client"].place_number_order(e164)
        return {"phone_number_id": result["id"]}

    monkeypatch.setattr(voice_kyc_service, "provision_tenant_number", provision)
    refund = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr("server.services.saas.billing_wallet_service.refund_did_purchase", refund)
    state["refund"] = refund
    return state


async def _job(db, pid):
    async with db() as session:
        return (
            await session.get(NumberPurchase, pid),
            (await session.execute(select(ProvisionJob).where(ProvisionJob.purchase_id == pid))).scalar_one(),
        )


async def test_vobiz_500_with_low_parent_balance_fails_and_refunds_at_once(db, worker, parent_vobiz):
    from server.services.saas import provision_worker

    pid = await _queued(db)
    worker["client"] = _child_client({
        "owned": {"items": []},  # reconciliation: the number is not on the account
        "purchase": VobizApiError("Vobiz API 500", status=500, body=PURCHASE_FAILED_BODY),
    })
    assert await provision_worker.process_one_job()
    purchase, job = await _job(db, pid)
    assert purchase.status == "failed" and job.status == "failed"
    assert job.last_error["code"] == "carrier_balance_exhausted"
    assert job.last_error["context"] == {"carrierBalance": 481.78, "currency": "INR", "carrierRequired": 600.0}
    assert job.last_error["refund"] == "done"
    worker["refund"].assert_awaited_once()
    async with db() as session:
        assert (await session.execute(select(NumberReservation))).scalar_one_or_none() is None
    row = await nps.get_purchase(pid, TID)
    assert row["lastError"]["code"] == "carrier_balance_exhausted"
    assert "vobiz" not in row["message"].lower() and "balance" not in row["message"].lower()


async def test_vobiz_500_with_enough_balance_retries_then_refunds(db, worker, parent_vobiz):
    from server.services.saas import provision_worker

    parent_vobiz.balance = {"ok": True, "balance": 5000.0, "currency": "INR"}
    pid = await _queued(db)
    worker["client"] = _child_client({
        "owned": {"items": []},
        "purchase": VobizApiError("Vobiz API 500", status=500, body=PURCHASE_FAILED_BODY),
    })
    assert await provision_worker.process_one_job()
    purchase, job = await _job(db, pid)
    assert purchase.status == "provisioning" and job.status == "queued"
    assert job.last_error["code"] == "carrier_purchase_refused"
    worker["refund"].assert_not_awaited()
    # Two more documented refusals: the third is final and refunded.
    for _ in range(2):
        async with db() as session:
            j = (await session.execute(select(ProvisionJob).where(ProvisionJob.purchase_id == pid))).scalar_one()
            j.updated_at = _now() - timedelta(seconds=1)
            await session.commit()
        assert await provision_worker.process_one_job()
    purchase, job = await _job(db, pid)
    assert purchase.status == "failed" and job.last_error["code"] == "carrier_purchase_refused"
    worker["refund"].assert_awaited_once()


async def test_vobiz_404_number_taken_refunds(db, worker, parent_vobiz):
    from server.services.saas import provision_worker

    pid = await _queued(db)
    worker["client"] = _child_client({
        "owned": {"items": []},
        "purchase": VobizApiError("Vobiz API 404", status=404, body=NOT_IN_INVENTORY_BODY),
    })
    assert await provision_worker.process_one_job()
    purchase, job = await _job(db, pid)
    assert purchase.status == "failed" and job.last_error["code"] == "number_taken"
    worker["refund"].assert_awaited_once()
    row = await nps.get_purchase(pid, TID)
    assert row["refunded"] is False  # refund mocked; the ledger row is what proves it
    assert errors.tenant_purchase_message("failed", "number_taken", True).startswith("This number was taken")


async def test_vobiz_auth_error_refunds_and_flags_platform(db, worker, parent_vobiz):
    from server.services.saas import provision_worker

    pid = await _queued(db)
    worker["client"] = _child_client({
        "owned": {"items": []},
        "purchase": VobizApiError("Vobiz API 401", status=401, body="{}"),
    })
    assert await provision_worker.process_one_job()
    _purchase_row, job = await _job(db, pid)
    assert job.last_error["code"] == "carrier_auth_failed"
    worker["refund"].assert_awaited_once()


async def test_timeout_keeps_money_and_retries_without_refund(db, worker, parent_vobiz):
    from server.services.saas import provision_worker

    pid = await _queued(db)
    worker["client"] = _child_client({
        "owned": {"items": []},
        "purchase": VobizApiError("Vobiz API timeout", status=None),
    })
    assert await provision_worker.process_one_job()
    purchase, job = await _job(db, pid)
    # The order may have happened; never refund an order that might exist.
    assert purchase.status == "provisioning" and job.last_error["code"] == "provider_confirmation_pending"
    worker["refund"].assert_not_awaited()


async def test_timeout_but_number_owned_on_reconcile_completes(db, worker, parent_vobiz):
    from server.services.saas import provision_worker

    pid = await _queued(db)
    worker["client"] = _child_client({
        "owned": {"items": [{"e164": PHONE, "status": "active", "account_id": "SA_CHILD", "id": "num-1",
                             "country": "IN"}]},
        "purchase": VobizApiError("Vobiz API timeout", status=None),
    })
    assert await provision_worker.process_one_job()
    purchase, job = await _job(db, pid)
    assert purchase.status == "active" and job.status == "done"
    worker["refund"].assert_not_awaited()


async def test_failed_refund_is_recorded_for_admin(db, worker, parent_vobiz):
    from server.services.saas import provision_worker

    worker["refund"].side_effect = RuntimeError("wallet down")
    pid = await _queued(db)
    worker["client"] = _child_client({
        "owned": {"items": []},
        "purchase": VobizApiError("Vobiz API 404", status=404, body=NOT_IN_INVENTORY_BODY),
    })
    assert await provision_worker.process_one_job()
    _p, job = await _job(db, pid)
    assert job.last_error["refund"] == "failed"
    listing = await admin.list_admin_purchases()
    item = next(i for i in listing["items"] if i["purchaseId"] == str(pid))
    assert item["status"] == "needs_attention" and item["issue"]["code"] == "refund_failed"
    assert item["refund"]["state"] == "failed" and item["canRefund"] is True and item["canRetry"] is False
    assert (await nps.get_purchase(pid, TID))["message"].startswith("We couldn't activate this number. Your refund is being processed")


# ------------------------------------------------------------------ admin page service


async def test_admin_buckets_money_and_carrier_explanation(db):
    pid = await _purchase(db, status="failed")
    async with db() as session:
        session.add(ProvisionJob(purchase_id=pid, status="failed", attempts=1, last_error={
            "code": "carrier_balance_exhausted", "error_type": "VobizApiError", "providerStatus": 500,
            "context": {"carrierBalance": 481.78, "carrierRequired": 600.0, "currency": "INR"}, "refund": "done",
        }))
        session.add(BillingWalletTransaction(tenant_id=TID, amount_cents=-400, amount_inr_paise=-56_400,
                                             kind="did_purchase", reference_id=f"did:{pid}"))
        session.add(BillingWalletTransaction(tenant_id=TID, amount_cents=400, amount_inr_paise=56_400,
                                             kind="did_refund", reference_id=f"did_refund:{pid}"))
        await session.commit()
    listing = await admin.list_admin_purchases(status="refunded")
    assert listing["total"] == 1 and listing["counts"]["refunded"] == 1
    item = listing["items"][0]
    assert item["tenantName"] == "Buyer" and item["charged"]["inr"] == 564.0
    assert item["refund"]["state"] == "refunded" and item["refund"]["amount"]["inr"] == 564.0
    assert item["issue"]["title"] == "Vobiz account balance is too low to buy numbers"
    assert item["carrier"]["context"]["carrierBalance"] == 481.78
    assert item["canRetry"] is False and item["canRefund"] is False


async def test_admin_refund_guards(db, monkeypatch):
    refund = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr("server.services.saas.billing_wallet_service.refund_did_purchase", refund)
    active = await _purchase(db, status="active")
    with pytest.raises(admin.PurchaseAdminError, match="number_owned"):
        async with db() as session:
            p = await session.get(NumberPurchase, active)
            pn = PhoneNumber(tenant_id=TID, e164=PHONE, status="active")
            session.add(pn)
            await session.flush()
            p.phone_number_id = pn.id
            await session.commit()
        await admin.refund_purchase(active)
    async with db() as session:
        for row in (await session.execute(select(NumberReservation))).scalars():
            await session.delete(row)
        await session.commit()
    running = await _purchase(db, status="provisioning")
    async with db() as session:
        session.add(ProvisionJob(purchase_id=running, status="running", attempts=1))
        await session.commit()
    with pytest.raises(admin.PurchaseAdminError, match="purchase_in_progress"):
        await admin.refund_purchase(running)
    refund.assert_not_awaited()


async def test_admin_refund_of_stuck_purchase_cancels_job_and_refunds_once(db, monkeypatch):
    refund = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr("server.services.saas.billing_wallet_service.refund_did_purchase", refund)
    pid = await _purchase(db, status="needs_attention")
    async with db() as session:
        session.add(ProvisionJob(purchase_id=pid, status="needs_attention", attempts=5))
        session.add(BillingWalletTransaction(tenant_id=TID, amount_cents=-400, amount_inr_paise=-56_400,
                                             kind="did_purchase", reference_id=f"did:{pid}"))
        await session.commit()
    result = await admin.refund_purchase(pid)
    assert result["refunded"] is True
    refund.assert_awaited_once()
    purchase, job = await _job(db, pid)
    assert purchase.status == "refunded" and job.status == "cancelled"
    # A refunded purchase can never be re-provisioned.
    with pytest.raises(admin.PurchaseAdminError, match="purchase_closed"):
        await admin.retry_purchase(pid)


async def test_admin_retry_requeues_needs_attention_with_fresh_attempts(db):
    pid = await _purchase(db, status="needs_attention")
    async with db() as session:
        session.add(ProvisionJob(purchase_id=pid, status="needs_attention", attempts=5))
        await session.commit()
    await admin.retry_purchase(pid)
    purchase, job = await _job(db, pid)
    assert purchase.status == "paid" and job.status == "queued" and job.attempts == 0
    with pytest.raises(admin.PurchaseAdminError, match="purchase_in_progress"):
        await admin.retry_purchase(pid)


async def test_admin_health_flags_rent_below_price_and_low_balance(db, parent_vobiz, monkeypatch):
    admin._inventory_cache.update(at=0.0, value=None)
    rates = dict(RATES, did_monthly_inr_paise=56_400)
    monkeypatch.setattr("server.services.saas.billing_rates.load_current_rates", AsyncMock(return_value=rates))
    async with db() as session:
        session.add(AuditLog(tenant_id=TID, actor="buyer@example.test", action="number.purchase.refused",
                             resource_type="number_purchase", resource_id=PHONE, source="subscriber",
                             outcome="error", severity="error",
                             payload={"error": "carrier_price_above_retail", "e164": PHONE, "httpStatus": 409,
                                      "context": {"carrierPrice": 600.0, "retailPrice": 564.0, "currency": "INR"}}))
        await session.commit()
    health = await admin.purchases_health()
    codes = [a["code"] for a in health["alerts"]]
    assert set(codes[:2]) == {"carrier_price_above_retail", "carrier_balance_exhausted"}
    rent_alert = next(a for a in health["alerts"] if a["code"] == "carrier_price_above_retail")
    assert "₹564.00" in rent_alert["detail"] and "₹600.00" in rent_alert["action"]
    assert rent_alert["affected"]["tenants"] == ["Buyer"] and rent_alert["affected"]["numbers"] == [PHONE]
    bal_alert = next(a for a in health["alerts"] if a["code"] == "carrier_balance_exhausted")
    assert "₹481.78" in bal_alert["detail"] and "Top up" in bal_alert["action"]
    assert health["carrierBalance"] == {"ok": True, "balance": 481.78, "currency": "INR"}
    assert health["inventoryPricing"]["cheapestInr"] == 600.0
    refusals = await admin.list_refusals(platform_only=True)
    assert refusals["items"][0]["issue"]["href"] == "/dev/admin/billing"


# ------------------------------------------------------------------ voice KYC initiation


class _KycParent:
    """Parent Vobiz client reproducing the documented sub-account/KYC responses."""

    session_error: Exception | None = None
    created: list = []

    def __init__(self, *_a, **_k):
        self.cfg = {"auth_id": "MA_PARENT", "auth_token": "unit-test"}
        self.configured = True
        self.auth_id = "MA_PARENT"

    async def create_customer_subaccount(self, **kw):
        _KycParent.created.append(kw)
        return {
            "sub_account": {"auth_id": "SA_TENANT1", "kyc_mode": "customer_use", "kyc_calls_blocked": True},
            "auth_credentials": {"auth_id": "SA_TENANT1", "auth_token": "child-secret"},
        }

    async def get_customer_subaccount(self, sub):
        return {"auth_id": sub, "parent_auth_id": "MA_PARENT", "is_active": True,
                "kyc_calls_blocked": True, "kyc_mode": "customer_use"}

    async def get_customer_kyc_status(self, sub):
        return {"sub_account_id": sub, "kyc_mode": "customer_use", "kyc_status": "pending", "kyc_calls_blocked": True}

    async def create_customer_kyc_session(self, *, sub_auth_id, redirect_url, webhook_url=None):
        if _KycParent.session_error is not None:
            raise _KycParent.session_error
        return {
            "session_id": "7d0f1f9e-5f43-4c8a-9a3e-0f6d2a1b9c11",
            "widget_url": "https://kyc.vobiz.ai/s/7d0f1f9e",
            "account_auth_id": sub_auth_id,
            "expires_at": (_now() + timedelta(hours=1)).isoformat(),
        }


@pytest.fixture
def kyc_parent(db, monkeypatch):
    from cryptography.fernet import Fernet

    from server.services.saas import voice_kyc_service

    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(voice_kyc_service, "get_settings", lambda: SimpleNamespace(
        vobiz_subaccount_encryption_key=key, dialtact_frontend_url="https://app.dialtact.com",
        app_environment="test",
    ))
    monkeypatch.setattr("server.config.urls.public_api_base", lambda: "https://api.example.test")
    monkeypatch.setattr("server.services.vobiz_client.VobizClient", _KycParent)
    _KycParent.session_error = None
    _KycParent.created = []
    return voice_kyc_service


async def test_kyc_start_creates_subaccount_and_returns_hosted_link(kyc_parent):
    result = await kyc_parent.start_kyc_session(
        tenant_id=TID, email="owner@example.test", legal_name="Buyer Pvt Ltd",
        business_type="private_limited", return_url="https://app.dialtact.com/phone-numbers",
    )
    assert result["sessionUrl"] == "https://kyc.vobiz.ai/s/7d0f1f9e"
    assert result["status"] == "pending" and result["approved"] is False and result["callsBlocked"] is True
    assert _KycParent.created[0]["business_type"] == "private_limited"
    assert "child-secret" not in json.dumps(result)


async def test_kyc_session_failure_is_visible_to_admin_and_retryable(kyc_parent):
    _KycParent.session_error = VobizApiError("Vobiz API 500", status=500, body="{}")
    with pytest.raises(kyc_parent.VoiceKycError, match="voice_kyc_session_failed"):
        await kyc_parent.start_kyc_session(
            tenant_id=TID, email="owner@example.test", legal_name="Buyer Pvt Ltd",
            business_type="private_limited", return_url=None,
        )
    rows = await kyc_parent.list_voice_verifications()
    row = next(r for r in rows if r["tenantId"] == str(TID))
    assert row["lastErrorCode"] == "kyc_session_http_500"
    assert "hosted KYC link" in row["lastError"] and row["provisioningStatus"] == "active"
    # The sub-account survived; a retry only creates the link.
    _KycParent.session_error = None
    result = await kyc_parent.start_kyc_session(
        tenant_id=TID, email="owner@example.test", legal_name="Buyer Pvt Ltd",
        business_type="private_limited", return_url=None,
    )
    assert result["sessionUrl"] and len(_KycParent.created) == 1


async def test_unknown_subaccount_result_reads_needs_review_not_not_started(kyc_parent):
    async def lost(self, **_kw):
        raise VobizApiError("Vobiz API timeout", status=None)

    kyc_parent_cls = _KycParent
    original = kyc_parent_cls.create_customer_subaccount
    kyc_parent_cls.create_customer_subaccount = lost
    try:
        with pytest.raises(kyc_parent.VoiceKycError, match="voice_account_needs_review"):
            await kyc_parent.start_kyc_session(
                tenant_id=TID, email="owner@example.test", legal_name="Buyer Pvt Ltd",
                business_type="private_limited", return_url=None,
            )
    finally:
        kyc_parent_cls.create_customer_subaccount = original
    status = await kyc_parent.refresh_kyc_status(TID)
    # Before: "not_started", which offered a Start button that always failed.
    assert status["status"] == "needs_review" and status["approved"] is False
    rows = await kyc_parent.list_voice_verifications()
    assert "Check the Vobiz console" in next(r for r in rows if r["tenantId"] == str(TID))["lastError"]
