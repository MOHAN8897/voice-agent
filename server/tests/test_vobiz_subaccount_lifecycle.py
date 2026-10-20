"""Offline lifecycle tests: real SQLAlchemy persistence, fake external provider.

SQLite checks persistence and isolation; PostgreSQL locking is checked separately
in the generated statements/migration. No live tenant or carrier state is used.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from server.db.models.entities import Base, Tenant
from server.db.models.phase5_models import PhoneNumber
from server.db.models.saas_models import (
    NumberPurchase,
    NumberReservation,
    ProvisionJob,
    User,
    VobizSubaccount,
)
from server.services.saas import voice_kyc_service as svc
from server.services.vobiz_client import VobizApiError

TID = UUID(int=11)
OTHER = UUID(int=12)
PHONE = "+14155550100"


@compiles(JSONB, "sqlite")
def _sqlite_json(_type, _compiler, **_kw):
    return "JSON"


@pytest.fixture
async def db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [Tenant, User, VobizSubaccount, PhoneNumber, NumberPurchase, NumberReservation, ProvisionJob]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[m.__table__ for m in tables]))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(svc, "get_session_factory", lambda: factory)
    monkeypatch.setattr(svc, "get_settings", lambda: SimpleNamespace(
        vobiz_subaccount_encryption_key=key, voxly_frontend_url="https://console.example.test",
        app_environment="development",
    ))
    key = Fernet.generate_key().decode()
    async with factory() as session:
        session.add_all([Tenant(tenant_id=TID, name="Test tenant", status="active"),
                         Tenant(tenant_id=OTHER, name="Other test tenant", status="active")])
        await session.commit()
    yield factory
    await engine.dispose()


@pytest.fixture
def carrier(monkeypatch):
    from server.services import vobiz_client
    parent = SimpleNamespace(auth_id="MA_test", cfg={"auth_token": "test-parent-secret"}, configured=True)
    parent.create_customer_subaccount = AsyncMock(return_value={
        "sub_account": {"auth_id": "SA_test"},
        "auth_credentials": {"auth_id": "SA_test", "auth_token": "test-child-secret"},
    })
    parent.get_customer_subaccount = AsyncMock(return_value={
        "auth_id": "SA_test", "parent_auth_id": "MA_test", "enabled": True, "is_active": True,
    })
    parent.get_customer_kyc_status = AsyncMock(return_value={
        "sub_account_id": "SA_test", "kyc_mode": "customer_use", "business_type": "llp",
        "overall_status": "pending", "kyc_calls_blocked": True, "verifications": {"pan": "pending"},
    })
    parent.create_customer_kyc_session = AsyncMock(return_value={
        "account_auth_id": "SA_test", "session_id": str(uuid4()),
        "widget_url": "https://kyc.vobiz.ai/verify?token=test-only",
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
    })
    child = SimpleNamespace(auth_id="SA_test", cfg={}, configured=True,
                            ensure_default_application=AsyncMock(return_value="child-app"),
                            place_number_order=AsyncMock(return_value={"id": "real-number-id"}),
                            release_owned_number=AsyncMock(return_value={}),
                            list_account_numbers=AsyncMock(return_value=[]))
    def client(cfg=None):
        if cfg is None:
            return parent
        assert cfg["auth_id"] == "SA_test" and cfg["auth_token"] == "test-child-secret"
        child.cfg = cfg
        return child
    monkeypatch.setattr(vobiz_client, "VobizClient", client)
    monkeypatch.setattr("server.config.urls.public_api_base", lambda: "https://api.example.test")
    return parent, child


async def onboard():
    return await svc.ensure_customer_subaccount(tenant_id=TID, email="owner@example.test", legal_name="Example LLP", business_type="llp")


async def approve(parent):
    parent.get_customer_kyc_status.return_value.update(overall_status="verified", kyc_calls_blocked=False)
    return await svc.refresh_kyc_status(TID, force=True)


async def test_single_account_persists_and_identity_is_locked(db, carrier):
    parent, _ = carrier
    await onboard()
    await onboard()
    parent.create_customer_subaccount.assert_awaited_once()
    async with db() as session:
        row = await session.get(VobizSubaccount, TID)
        assert row.parent_auth_id == "MA_test"
        assert row.encrypted_auth_token != "test-child-secret"
        assert svc.decrypt_subaccount_token(TID, row.encrypted_auth_token) == "test-child-secret"
    with pytest.raises(svc.VoiceKycError, match="voice_identity_locked"):
        await svc.ensure_customer_subaccount(tenant_id=TID, email="owner@example.test", legal_name="Different LLP", business_type="llp")


@pytest.mark.parametrize("status", [None, 408, 409, 429, 500])
async def test_ambiguous_creation_does_not_create_another_account(db, carrier, status):
    parent, _ = carrier
    parent.create_customer_subaccount.side_effect = VobizApiError("test-only", status=status)
    for _ in range(2):
        with pytest.raises(svc.VoiceKycError):
            await onboard()
    parent.create_customer_subaccount.assert_awaited_once()
    async with db() as session:
        assert (await session.get(VobizSubaccount, TID)).provisioning_status == "provisioning_unknown"


async def test_subaccount_creation_recovers_from_email_conflict_via_alias(db, carrier):
    parent, _ = carrier
    calls = []
    async def create_sub(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise VobizApiError("Email is already in use", status=409, body="Email 'owner@example.test' is already in use")
        return {
            "sub_account": {"auth_id": "SA_test"},
            "auth_credentials": {"auth_id": "SA_test", "auth_token": "test-child-secret"},
        }
    parent.create_customer_subaccount.side_effect = create_sub
    row = await onboard()
    assert row.auth_id == "SA_test"
    assert len(calls) == 2
    assert calls[0]["email"] == "owner@example.test"
    assert "+voice-" in calls[1]["email"]



async def test_masked_credentials_are_never_accepted_or_recreated(db, carrier):
    parent, _ = carrier
    parent.create_customer_subaccount.return_value["auth_credentials"]["auth_token"] = "<redacted>"
    with pytest.raises(svc.VoiceKycError):
        await onboard()
    async with db() as session:
        row = await session.get(VobizSubaccount, TID)
        assert row.provisioning_status == "credentials_lost" and row.encrypted_auth_token is None


async def test_authoritative_status_revocation_disabled_and_parent_change(db, carrier):
    parent, _ = carrier
    await onboard()
    assert not (await svc.refresh_kyc_status(TID))["approved"]
    assert (await approve(parent))["approved"]
    parent.get_customer_subaccount.return_value["enabled"] = False
    assert not (await svc.refresh_kyc_status(TID, force=True))["approved"]
    parent.get_customer_subaccount.return_value["enabled"] = True
    parent.get_customer_kyc_status.return_value["kyc_calls_blocked"] = True
    assert not (await svc.refresh_kyc_status(TID, force=True))["approved"]
    parent.auth_id = "MA_changed"
    with pytest.raises(svc.VoiceKycError):
        await svc.refresh_kyc_status(TID, force=True)
    with pytest.raises(svc.VoiceKycError):
        await svc.vobiz_client_for_tenant(TID)


async def test_hosted_session_resumes_and_webhook_is_only_a_refresh_hint(db, carrier):
    parent, _ = carrier
    args = dict(tenant_id=TID, email="owner@example.test", legal_name="Example LLP", business_type="llp", return_url="https://console.example.test/#dashboard/settings")
    first = await svc.start_kyc_session(**args)
    second = await svc.start_kyc_session(**args)
    assert first["sessionUrl"] == second["sessionUrl"]
    parent.create_customer_kyc_session.assert_awaited_once()
    assert parent.create_customer_kyc_session.await_args.kwargs["webhook_url"] == "https://api.example.test/api/webhooks/voice-kyc"
    async with db() as session:
        row = await session.get(VobizSubaccount, TID)
        assert "https://" not in row.encrypted_kyc_url
        session_id = row.kyc_session_id
    payload = {"event": "kyc.completed", "session_id": session_id, "account_auth_id": "SA_test"}
    assert (await svc.apply_voice_webhook({**payload, "account_auth_id": "SA_other"}))["ignored"]
    await svc.apply_voice_webhook(payload)
    assert not (await svc.refresh_kyc_status(TID))["approved"]  # callback alone cannot approve
    await approve(parent)
    await svc.apply_voice_webhook(payload)  # replay is safe
    assert (await svc.refresh_kyc_status(TID))["approved"]


@pytest.mark.parametrize("url", ["https://evil.example/", "https://console.example.test.evil/", "https://x@console.example.test/", "http://console.example.test/"])
async def test_redirects_are_bound_to_console(db, url):
    with pytest.raises(svc.VoiceKycError):
        svc._trusted_return_url(url)


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:5173/#dashboard/phone-numbers",
    "http://localhost:5173/#dashboard/phone-numbers",
    "http://localhost:3000/#dashboard/settings",
])
async def test_development_console_allows_loopback_kyc_return(db, url):
    assert svc._trusted_return_url(url) == url


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8000/",
    "http://localhost:5174/",
    "http://localhost.evil:5173/",
])
async def test_development_console_rejects_untrusted_loopback_redirects(db, url):
    with pytest.raises(svc.VoiceKycError, match="invalid_voice_kyc_return_url"):
        svc._trusted_return_url(url)


async def test_production_console_rejects_loopback_kyc_return(db, monkeypatch):
    monkeypatch.setattr(svc, "get_settings", lambda: SimpleNamespace(
        voxly_frontend_url="https://console.example.test", app_environment="production",
    ))
    with pytest.raises(svc.VoiceKycError, match="invalid_voice_kyc_return_url"):
        svc._trusted_return_url("http://127.0.0.1:5173/#dashboard/settings")


@pytest.mark.parametrize("url", [
    "https://www.dialtact.com/#dashboard/phone-numbers",
    "https://dialtact.com/#dashboard/phone-numbers",
    "https://app.dialtact.com/#dashboard/phone-numbers",
])
async def test_production_console_accepts_trusted_dialtact_origins(db, monkeypatch, url):
    monkeypatch.setattr(svc, "get_settings", lambda: SimpleNamespace(
        voxly_frontend_url="https://app-dev.dialtact.com", app_environment="production",
    ))
    assert svc._trusted_return_url(url) == url


@pytest.mark.parametrize("url", [
    "https://dialtact.com.attacker.example/#dashboard/phone-numbers",
    "https://dialtact.attacker.example/#dashboard/phone-numbers",
    "https://www.dialtact.com:444/#dashboard/phone-numbers",
])
async def test_production_console_rejects_untrusted_dialtact_like_origins(db, monkeypatch, url):
    monkeypatch.setattr(svc, "get_settings", lambda: SimpleNamespace(
        voxly_frontend_url="https://app-dev.dialtact.com", app_environment="production",
    ))
    with pytest.raises(svc.VoiceKycError, match="invalid_voice_kyc_return_url"):
        svc._trusted_return_url(url)


async def test_direct_child_purchase_sets_inbound_app_first(db, carrier):
    parent, child = carrier
    await onboard()
    await approve(parent)
    async def purchase(_e164):
        child.ensure_default_application.assert_awaited_once()
        async with db() as session:
            assert (await session.get(VobizSubaccount, TID)).application_id == "child-app"
        return {"id": "real-number-id"}
    child.place_number_order.side_effect = purchase
    assert (await svc.provision_tenant_number(TID, PHONE))["phone_number_id"] == "real-number-id"


async def test_foreign_or_missing_number_never_falls_back_to_parent(db, carrier):
    parent, child = carrier
    await onboard()
    async with db() as session:
        session.add(PhoneNumber(tenant_id=TID, e164=PHONE, status="active", carrier_number_id="real-number-id",
                                vobiz_account_scope="tenant", vobiz_account_tenant_id=TID))
        await session.commit()
    client, scope = await svc.vobiz_client_for_number(TID, PHONE)
    assert client is child and scope == "tenant"
    with pytest.raises(svc.VoiceKycError, match="voice_number_not_owned"):
        await svc.vobiz_client_for_number(OTHER, PHONE)
    assert await svc.vobiz_client_for_call({"tenant_id": str(TID), "vobiz_account_scope": "platform"}) is parent
    assert await svc.vobiz_client_for_call({"tenant_id": str(TID), "vobiz_account_scope": "tenant"}) is child
    with pytest.raises(svc.VoiceKycError, match="voice_number_account_unknown"):
        await svc.vobiz_client_for_call({"tenant_id": str(TID)})


def test_customer_cannot_become_platform_inventory_by_renaming_workspace():
    from server.services.saas.number_inventory import is_platform_inventory_tenant
    assert not is_platform_inventory_tenant(SimpleNamespace(name="Platform inventory", plan="free"))
    assert is_platform_inventory_tenant(SimpleNamespace(name="Platform inventory", plan="platform"))


async def test_webhook_hmac_and_payload_limits(db, carrier, monkeypatch):
    import hashlib
    import hmac

    from server.routes.app_kyc import router
    app = FastAPI()
    app.include_router(router)
    apply = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(svc, "apply_voice_webhook", apply)
    raw = b'{"event":"kyc.completed","account_auth_id":"SA_test"}'
    signature = "sha256=" + hmac.new(b"test-parent-secret", raw, hashlib.sha256).hexdigest()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test.local") as client:
        assert (await client.post("/api/webhooks/voice-kyc", content=raw)).status_code == 401
        assert (await client.post("/api/webhooks/voice-kyc", content=raw+b" ", headers={"X-Vobiz-Signature": signature})).status_code == 401
        assert (await client.post("/api/webhooks/voice-kyc", content=raw, headers={"X-Vobiz-Signature": signature})).status_code == 200
        assert (await client.post("/api/webhooks/voice-kyc", content=b"x"*65537)).status_code == 413
    apply.assert_awaited_once()


async def test_worker_uses_persisted_provider_and_recovers_interrupted_job(db, monkeypatch):
    from server.services.saas import activity_log, provision_worker
    monkeypatch.setattr(provision_worker, "get_session_factory", lambda: db)
    monkeypatch.setattr(activity_log, "record_event", AsyncMock())
    provision = AsyncMock(return_value={"phone_number_id": "real-number-id"})
    monkeypatch.setattr(svc, "provision_tenant_number", provision)
    monkeypatch.setattr("server.services.telephony.active_telephony_provider", lambda: "telnyx")
    async with db() as session:
        purchase = NumberPurchase(tenant_id=TID, e164=PHONE, status="provisioning", provider="vobiz")
        session.add(purchase)
        await session.flush()
        session.add(ProvisionJob(purchase_id=purchase.id, status="running", attempts=1,
                                 updated_at=datetime.now(timezone.utc)-timedelta(minutes=11)))
        await session.commit()
        pid = purchase.id
    assert await provision_worker.process_one_job()
    provision.assert_awaited_once_with(TID, PHONE)
    async with db() as session:
        purchase = await session.get(NumberPurchase, pid)
        phone = await session.get(PhoneNumber, purchase.phone_number_id)
        assert purchase.status == "active" and phone.vobiz_account_tenant_id == TID
        assert phone.carrier_number_id == "real-number-id"
    assert not await provision_worker.process_one_job()


async def test_customer_number_release_never_enters_shared_inventory(db, carrier, monkeypatch):
    from server.services.saas import number_inventory
    _, child = carrier
    await onboard()
    monkeypatch.setattr(number_inventory, "get_session_factory", lambda: db)
    monkeypatch.setattr(number_inventory, "ensure_platform_inventory_tenant", AsyncMock(return_value=OTHER))
    async with db() as session:
        phone = PhoneNumber(tenant_id=TID, e164=PHONE, status="active", carrier_number_id="real-number-id",
                            vobiz_account_scope="tenant", vobiz_account_tenant_id=TID)
        session.add(phone)
        await session.commit()
        nid = phone.id
    result = await number_inventory.move_to_inventory(number_id=nid)
    assert result["status"] == "released" and not result["available"]
    child.release_owned_number.assert_awaited_once_with(PHONE)
    async with db() as session:
        phone = await session.get(PhoneNumber, nid)
        assert phone.tenant_id == TID and phone.released_at and not phone.inbound_enabled


@pytest.mark.parametrize("change", ["wrong_account", "wrong_mode", "missing_gate", "wrong_business"])
async def test_malformed_provider_status_fails_closed(db, carrier, change):
    parent, _ = carrier
    await onboard()
    await approve(parent)
    fields = {"wrong_account": ("sub_account_id", "SA_other"), "wrong_mode": ("kyc_mode", "personal_use"),
              "missing_gate": ("kyc_calls_blocked", None), "wrong_business": ("business_type", "individual")}
    field, value = fields[change]
    parent.get_customer_kyc_status.return_value[field] = value
    with pytest.raises(svc.VoiceKycError):
        await svc.refresh_kyc_status(TID, force=True)


async def test_provider_outage_blocks_purchase_even_after_prior_approval(db, carrier):
    from fastapi import HTTPException
    parent, _ = carrier
    await onboard()
    await approve(parent)
    parent.get_customer_kyc_status.side_effect = TimeoutError()
    with pytest.raises(HTTPException) as exc:
        await svc.assert_voice_kyc_approved(TID, action="place a phone call")
    assert exc.value.status_code == 503


@pytest.mark.parametrize("field,value", [("widget_url", "https://evil.example/"), ("widget_url", "https://x@kyc.vobiz.ai/"),
                                         ("account_auth_id", "SA_other"), ("expires_at", "2020-01-01T00:00:00Z")])
async def test_invalid_hosted_session_is_never_returned(db, carrier, field, value):
    parent, _ = carrier
    parent.create_customer_kyc_session.return_value[field] = value
    with pytest.raises(svc.VoiceKycError, match="voice_kyc_session_failed"):
        await svc.start_kyc_session(tenant_id=TID, email="owner@example.test", legal_name="Example LLP", business_type="llp", return_url=None)


async def test_inbound_transfer_is_denied_before_kyc_passes(db, carrier, monkeypatch):
    from starlette.requests import Request

    from server.routes import vobiz
    from server.services.saas import telephony_profile
    await onboard()
    monkeypatch.setattr("server.db.connection.get_session_factory", lambda: db)
    monkeypatch.setattr(vobiz, "_parse_vobiz_payload", AsyncMock(return_value={
        "CallUUID": "kyc-inbound-test", "To": PHONE, "Direction": "inbound",
    }))
    monkeypatch.setattr(vobiz, "_verify_vobiz_request", AsyncMock())  # signature checks covered independently
    monkeypatch.setattr(telephony_profile, "profile_for_number", AsyncMock(return_value={
        "agent_id": str(UUID(int=101)), "tenant_id": str(TID), "vobiz_account_scope": "tenant",
        "vobiz_account_tenant_id": str(TID),
    }))
    policy = AsyncMock(side_effect=AssertionError("must not reach transfer policy"))
    monkeypatch.setattr(telephony_profile, "evaluate_inbound_policy", policy)
    request = Request({"type": "http", "path": "/api/vobiz/answer", "query_string": b"", "headers": []})
    response = await vobiz.vobiz_answer(request)
    assert b"<Hangup" in response.body and b"<Dial" not in response.body and b"<Stream" not in response.body
    policy.assert_not_called()


async def test_teardown_retains_ownership_when_provider_release_is_pending(db, carrier, monkeypatch):
    from server.services.saas import number_inventory, teardown_worker
    async with db() as session:
        phone = PhoneNumber(tenant_id=TID, e164=PHONE, status="active", carrier_number_id="real-number-id", vobiz_account_scope="tenant")
        session.add(phone)
        await session.commit()
    monkeypatch.setattr(number_inventory, "move_to_inventory", AsyncMock(return_value={"status": "release_pending"}))
    with pytest.raises(RuntimeError, match="still pending"):
        await teardown_worker._stage_carrier_numbers(db, TID)
    async with db() as session:
        phone = (await session.execute(select(PhoneNumber).where(PhoneNumber.tenant_id == TID))).scalar_one()
        assert phone.released_at is None


async def test_kyc_session_rejects_unverified_email_before_creating_provider_state(db, carrier, monkeypatch):
    from fastapi import HTTPException

    from server.routes import app_kyc
    from server.services.saas.tenant_guard import SubscriberPrincipal
    uid = uuid4()
    async with db() as session:
        session.add(User(user_id=uid, email="owner@example.test", password_hash="test-only"))
        await session.commit()
    monkeypatch.setattr("server.db.connection.get_session_factory", lambda: db)
    app_kyc._voice_session_limiter.reset()
    principal = SubscriberPrincipal(uid, TID, "customer_admin", "owner@example.test")
    with pytest.raises(HTTPException) as exc:
        await app_kyc.create_voice_kyc_session(app_kyc.VoiceKycSessionBody(legal_name="Example LLP", business_type="llp"), principal)
    assert exc.value.status_code == 403
    carrier[0].create_customer_subaccount.assert_not_awaited()


async def test_kyc_session_endpoint_uses_local_development_console_return(db, carrier, monkeypatch):
    from server.routes import app_kyc
    from server.services.saas.tenant_guard import SubscriberPrincipal

    parent, _ = carrier
    uid = uuid4()
    async with db() as session:
        session.add(User(
            user_id=uid, email="owner@example.test", password_hash="test-only",
            email_verified_at=datetime.now(timezone.utc),
        ))
        await session.commit()
    monkeypatch.setattr("server.db.connection.get_session_factory", lambda: db)
    monkeypatch.setattr("server.services.telephony.active_telephony_provider", lambda: "vobiz")
    monkeypatch.setattr("server.config.urls.public_api_base", lambda: "https://api.example.test")
    app_kyc._voice_session_limiter.reset()
    principal = SubscriberPrincipal(uid, TID, "customer_admin", "owner@example.test")
    return_url = "http://127.0.0.1:5173/#dashboard/phone-numbers"

    result = await app_kyc.create_voice_kyc_session(
        app_kyc.VoiceKycSessionBody(
            legal_name="Example LLP", business_type="llp", return_url=return_url,
        ),
        principal,
    )

    assert result["sessionUrl"].startswith("https://kyc.vobiz.ai/")
    assert parent.create_customer_kyc_session.await_args.kwargs["redirect_url"] == return_url
    assert result["approved"] is False and result["callsBlocked"] is True


@pytest.mark.parametrize("provider,expected_calls,error_code", [(None, 0, "purchase_provider_unknown"), ("vobiz", 1, "provider_confirmation_pending")])
async def test_unknown_provider_or_ambiguous_purchase_never_uses_another_carrier_or_refunds(db, monkeypatch, provider, expected_calls, error_code):
    from server.services.saas import activity_log, billing_wallet_service, provision_worker
    monkeypatch.setattr(provision_worker, "get_session_factory", lambda: db)
    monkeypatch.setattr(activity_log, "record_event", AsyncMock())
    provision = AsyncMock(side_effect=TimeoutError())
    refund = AsyncMock()
    monkeypatch.setattr(svc, "provision_tenant_number", provision)
    monkeypatch.setattr(billing_wallet_service, "refund_did_purchase", refund)
    async with db() as session:
        purchase = NumberPurchase(tenant_id=TID, e164=PHONE, status="paid", provider=provider)
        session.add(purchase)
        await session.flush()
        session.add(ProvisionJob(purchase_id=purchase.id, status="queued", attempts=4))
        session.add(NumberReservation(tenant_id=TID, purchase_id=purchase.id, e164=PHONE,
                                     expires_at=datetime.now(timezone.utc)-timedelta(minutes=1)))
        await session.commit()
        pid = purchase.id
    await provision_worker.process_one_job()
    assert provision.await_count == expected_calls
    refund.assert_not_awaited()
    async with db() as session:
        assert (await session.get(NumberPurchase, pid)).status == "needs_attention"
        job = (await session.execute(select(ProvisionJob).where(ProvisionJob.purchase_id == pid))).scalar_one()
        assert job.last_error["code"] == error_code
        assert (await session.execute(select(NumberReservation).where(NumberReservation.tenant_id == TID))).scalar_one()


async def test_number_release_rechecks_tenant_ownership_inside_lock(db, monkeypatch):
    from fastapi import HTTPException

    from server.services.saas import number_inventory
    monkeypatch.setattr(number_inventory, "get_session_factory", lambda: db)
    monkeypatch.setattr(number_inventory, "ensure_platform_inventory_tenant", AsyncMock(return_value=OTHER))
    async with db() as session:
        phone = PhoneNumber(tenant_id=TID, e164=PHONE, status="active", carrier_number_id="real-id", vobiz_account_scope="tenant")
        session.add(phone)
        await session.commit()
        nid = phone.id
    with pytest.raises(HTTPException) as exc:
        await number_inventory.move_to_inventory(number_id=nid, expected_tenant_id=OTHER)
    assert exc.value.status_code == 404


async def test_hosted_kyc_uses_polling_without_submitting_an_insecure_callback(db, carrier, monkeypatch):
    monkeypatch.setattr("server.config.urls.public_api_base", lambda: "http://localhost:8000")
    result = await svc.start_kyc_session(tenant_id=TID, email="owner@example.test", legal_name="Example LLP", business_type="llp", return_url=None)
    assert result["sessionUrl"].startswith("https://kyc.vobiz.ai/")
    assert carrier[0].create_customer_kyc_session.await_args.kwargs["webhook_url"] is None
    assert result["approved"] is False and result["callsBlocked"] is True


async def test_failed_document_creates_a_new_session_instead_of_reusing_old_link(db, carrier):
    parent, _ = carrier
    args = dict(tenant_id=TID, email="owner@example.test", legal_name="Example LLP", business_type="llp", return_url=None)
    await svc.start_kyc_session(**args)
    parent.get_customer_kyc_status.return_value.update(overall_status="failed", kyc_calls_blocked=True)
    await svc.start_kyc_session(**args)
    assert parent.create_customer_subaccount.await_count == 1
    assert parent.create_customer_kyc_session.await_count == 2
