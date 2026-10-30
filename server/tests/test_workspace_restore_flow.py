"""Workspace restore after deletion: the whole sign-out → sign-in → restore journey.

The product owner's report: after deleting a workspace, the sign-in screen says it
can be restored during the 14-day grace period, but signing in again never lets the
owner restore it. These tests drive the real routes against a SQLite stand-in for
Postgres (JSONB/ARRAY become JSON for the test only), with no carrier, email or
Redis: owner deletes → session revoked → sign in again (password with and without
"keep me signed in", Google, refresh cookie under both names) → restore screen data
→ restore, plus the member, idempotency, teardown and expired-grace cases.

Test credentials below are fixtures for this file only.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import JSON, DateTime, select
from sqlalchemy.types import TypeDecorator
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import server.app as app_mod
from server.auth.jwt_tokens import AccessTokenClaims, create_access_token, decode_access_token
from server.auth.passwords import hash_portal_password
from server.config.env import get_settings
from server.db.models.entities import Agent, Call, Tenant
from server.db.models.integration_models import TenantIntegration
from server.db.models.phase5_models import Campaign, PhoneNumber
from server.db.models.saas_models import (
    AuthEvent,
    BillingInvoice,
    BillingWallet,
    EmailVerificationToken,
    RefreshToken,
    TenantExportJob,
    TenantMembership,
    TenantTeardownJob,
    User,
    UserOnboardingSurvey,
)
from server.routes import app_tenant_deletion
from server.services.saas import auth_service, teardown_worker

TABLES = [
    Tenant, Agent, Call, User, TenantMembership, RefreshToken, AuthEvent, TenantTeardownJob,
    PhoneNumber, Campaign, BillingWallet, BillingInvoice, EmailVerificationToken,
    TenantExportJob, TenantIntegration, UserOnboardingSurvey,
]

OWNER_EMAIL = "owner.restore@example.test"
MEMBER_EMAIL = "member.restore@example.test"
GOOGLE_EMAIL = "google.owner@example.test"
TEST_PASSWORD = "fixture-Passw0rd-only"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class _AwareDateTime(TypeDecorator):
    """SQLite drops tzinfo; Postgres timestamptz does not. Hand back aware UTC like Postgres."""

    impl = DateTime
    cache_ok = True

    def process_result_value(self, value, dialect):
        return _aware(value)


@pytest.fixture
async def db(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    changed = [
        (c, c.type)
        for m in TABLES
        for c in m.__table__.columns
        if isinstance(c.type, (ARRAY, JSONB)) or (isinstance(c.type, DateTime) and c.type.timezone)
    ]
    for c, original in changed:
        c.type = _AwareDateTime() if isinstance(original, DateTime) else JSON()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'restore.db'}")
    try:
        async with engine.begin() as conn:
            for m in TABLES:
                await conn.run_sync(lambda sync, t=m.__table__: t.create(sync, checkfirst=True))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        for target in (
            "server.services.saas.auth_service.get_session_factory",
            "server.auth.subscriber_dependencies.get_session_factory",
            "server.routes.app_tenant_deletion.get_session_factory",
            "server.services.saas.teardown_worker.get_session_factory",
        ):
            monkeypatch.setattr(target, lambda: factory)
        settings = get_settings()
        monkeypatch.setattr(settings, "saas_auth_enabled", True)
        monkeypatch.setattr(settings, "database_url", "sqlite+aiosqlite://test-only")
        monkeypatch.setattr(settings, "saas_require_email_verification_for_login", False, raising=False)
        monkeypatch.setattr(settings, "redis_url", None, raising=False)
        # Post-commit side effects of the delete call — nothing to hang up or evict here.
        from server.call.call_store import call_store

        monkeypatch.setattr(call_store, "terminate_tenant_calls", AsyncMock(return_value=0))
        monkeypatch.setattr(app_tenant_deletion, "_send_deletion_scheduled_email_bg", lambda **_: None)
        monkeypatch.setattr(auth_service, "_seed_admin_wallet", AsyncMock(return_value=None))
        app_tenant_deletion._delete_attempts.clear()
        yield factory
    finally:
        app_mod.app.dependency_overrides.clear()
        await engine.dispose()
        for c, original in changed:
            c.type = original
        get_settings.cache_clear()


async def _seed(factory, *, google_only: bool = False) -> dict:
    """An owner, a member, numbers, a running campaign, a funded wallet."""
    tid = uuid.uuid4()
    owner_id, member_id, agent_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    number_live, number_off = uuid.uuid4(), uuid.uuid4()
    campaign_id = uuid.uuid4()
    pw_hash = hash_portal_password(TEST_PASSWORD)
    async with factory() as s:
        s.add(Tenant(tenant_id=tid, name="Acme Restore", status="active", plan="starter", limits={}))
        s.add(User(
            user_id=owner_id,
            email=GOOGLE_EMAIL if google_only else OWNER_EMAIL,
            password_hash=pw_hash,
            full_name="Owner",
            status="active",
            email_verified_at=_now(),
        ))
        s.add(User(user_id=member_id, email=MEMBER_EMAIL, password_hash=pw_hash, full_name="Member",
                   status="active", email_verified_at=_now()))
        s.add(TenantMembership(user_id=owner_id, tenant_id=tid, role="customer_admin", created_at=_now()))
        s.add(TenantMembership(user_id=member_id, tenant_id=tid, role="customer_viewer", created_at=_now()))
        s.add(Agent(agent_id=agent_id, tenant_id=tid, name="Front desk", status="active"))
        s.add(PhoneNumber(id=number_live, tenant_id=tid, e164="+15550000001", status="active",
                          inbound_enabled=True, outbound_enabled=True))
        # Was already inbound-only before deletion; restore must not widen it.
        s.add(PhoneNumber(id=number_off, tenant_id=tid, e164="+15550000002", status="active",
                          inbound_enabled=True, outbound_enabled=False))
        s.add(Campaign(campaign_id=campaign_id, tenant_id=tid, agent_id=agent_id, name="Renewals",
                       status="active"))
        s.add(BillingWallet(tenant_id=tid, balance_cents=1234, balance_inr_paise=50000))
        await s.commit()
    return {
        "tid": tid, "owner_id": owner_id, "member_id": member_id,
        "number_live": number_live, "number_off": number_off, "campaign_id": campaign_id,
    }


def _client() -> TestClient:
    return TestClient(app_mod.app)


def _login(client: TestClient, email: str, *, remember: bool = False):
    return client.post("/api/auth/login", json={"email": email, "password": TEST_PASSWORD, "rememberMe": remember})


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _stale_token(user_id, tenant_id, email, role="customer_admin") -> str:
    """An access token as a silent refresh issues it: no auth_time."""
    token, _ = create_access_token(
        AccessTokenClaims(user_id=str(user_id), tenant_id=str(tenant_id), role=role, email=email)
    )
    return token


async def _owner_deletes(factory, seed) -> None:
    """Owner signs in, deletes the workspace, and is signed out (the real request)."""
    client = _client()
    res = _login(client, OWNER_EMAIL)
    assert res.status_code == 200, res.text
    res = client.post(
        "/api/tenant/delete",
        json={"confirmation_name": "delete", "current_password": TEST_PASSWORD, "forfeit_balance_confirmed": True},
        headers=_bearer(res.json()["accessToken"]),
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "quarantined"


async def _tenant(factory, tid) -> Tenant:
    async with factory() as s:
        return await s.get(Tenant, tid)


async def _jobs(factory, tid) -> list[TenantTeardownJob]:
    async with factory() as s:
        return list((await s.execute(select(TenantTeardownJob).where(TenantTeardownJob.tenant_id == tid))).scalars())


# ---------------------------------------------------------------------------
# Sign-in after deletion
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("remember", [False, True])
async def test_owner_password_sign_in_reaches_restore_screen(db, remember):
    seed = await _seed(db)
    await _owner_deletes(db, seed)

    client = _client()
    res = _login(client, OWNER_EMAIL, remember=remember)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["tenant"]["status"] == "quarantined"
    assert body["tenant"]["scheduledPurgeAt"]
    claims = decode_access_token(body["accessToken"])
    assert claims.auth_time is not None, "an interactive sign-in must stamp auth_time"

    # Any ordinary API is refused with the code the console turns into the restore screen.
    res = client.get("/api/tenant/delete-preflight", headers=_bearer(body["accessToken"]))
    assert res.status_code == 403
    assert res.json()["detail"]["error"] == "tenant_quarantined"

    res = client.get("/api/tenant/restore-status", headers=_bearer(body["accessToken"]))
    assert res.status_code == 200, res.text
    st = res.json()
    assert st["status"] == "quarantined"
    assert st["canRestore"] is True
    assert st["reauthRequired"] is False
    assert st["deletedByYou"] is True
    assert st["inGracePeriod"] is True
    assert 13 <= st["daysRemaining"] <= 14
    assert st["restorePreview"]["agents"] == 1
    assert st["restorePreview"]["phoneNumbers"] == 2
    assert st["restorePreview"]["campaignsPaused"] == 1
    assert st["restorePreview"]["walletBalanceUsd"] == 12.34


async def test_owner_restore_reactivates_everything(db):
    seed = await _seed(db)
    await _owner_deletes(db, seed)

    async with db() as s:
        nums = {n.id: n for n in (await s.execute(select(PhoneNumber))).scalars()}
        assert not any(n.inbound_enabled or n.outbound_enabled for n in nums.values())
        assert (await s.get(Campaign, seed["campaign_id"])).status == "paused"

    client = _client()
    token = _login(client, OWNER_EMAIL).json()["accessToken"]
    res = client.post("/api/tenant/restore", headers=_bearer(token))
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["status"] == "active" and out["alreadyActive"] is False
    assert out["restored"]["phoneNumbers"] == 2
    assert out["restored"]["campaignsPaused"] == 1

    tenant = await _tenant(db, seed["tid"])
    assert tenant.status == "active"
    assert tenant.scheduled_purge_at is None
    assert tenant.restored_at is not None
    assert all(j.status == "cancelled" for j in await _jobs(db, seed["tid"]))
    async with db() as s:
        live = await s.get(PhoneNumber, seed["number_live"])
        off = await s.get(PhoneNumber, seed["number_off"])
        assert (live.inbound_enabled, live.outbound_enabled) == (True, True)
        assert (off.inbound_enabled, off.outbound_enabled) == (True, False)
        # Outbound dialling does not restart behind the owner's back.
        assert (await s.get(Campaign, seed["campaign_id"])).status == "paused"
        wallet = (await s.execute(select(BillingWallet))).scalar_one()
        assert (wallet.balance_cents, wallet.balance_inr_paise) == (1234, 50000)
        events = [e.event_type for e in (await s.execute(select(AuthEvent))).scalars()]
        assert "tenant.quarantined" in events and "tenant.restored" in events

    # The same session now opens the console.
    res = client.get("/api/tenant/delete-preflight", headers=_bearer(token))
    assert res.status_code == 200


async def test_restore_is_idempotent_and_teardown_never_runs(db, monkeypatch):
    seed = await _seed(db)
    await _owner_deletes(db, seed)
    client = _client()
    token = _login(client, OWNER_EMAIL).json()["accessToken"]
    assert client.post("/api/tenant/restore", headers=_bearer(token)).status_code == 200

    again = client.post("/api/tenant/restore", headers=_bearer(token))
    assert again.status_code == 200
    assert again.json()["alreadyActive"] is True
    # Legacy alias used by the old banner behaves the same.
    legacy = client.post("/api/tenant/delete/cancel", headers=_bearer(token))
    assert legacy.status_code == 200 and legacy.json()["alreadyActive"] is True
    async with db() as s:
        restored = [e for e in (await s.execute(select(AuthEvent))).scalars() if e.event_type == "tenant.restored"]
        assert len(restored) == 1

    # Even with the purge date in the past and a stray job left queued, the worker
    # must not touch a restored workspace.
    async with db() as s:
        s.add(TenantTeardownJob(tenant_id=seed["tid"], status="queued", stage="queued", payload={}))
        await s.commit()
    monkeypatch.setattr(teardown_worker, "_stage_integrations", AsyncMock(side_effect=AssertionError("purged")))
    assert await teardown_worker.process_one_teardown() is False
    assert (await _tenant(db, seed["tid"])).status == "active"


async def test_restore_cancels_every_open_teardown_job(db):
    seed = await _seed(db)
    await _owner_deletes(db, seed)
    async with db() as s:  # e.g. a second job from the legacy /api/tenants/delete path
        s.add(TenantTeardownJob(tenant_id=seed["tid"], status="queued", stage="queued", payload={}))
        await s.commit()
    client = _client()
    token = _login(client, OWNER_EMAIL).json()["accessToken"]
    res = client.post("/api/tenant/restore", headers=_bearer(token))
    assert res.status_code == 200, res.text
    assert res.json()["restored"]["teardownJobsCancelled"] == 2
    assert {j.status for j in await _jobs(db, seed["tid"])} == {"cancelled"}


async def test_member_sees_explanation_but_cannot_restore(db):
    seed = await _seed(db)
    await _owner_deletes(db, seed)
    client = _client()
    res = _login(client, MEMBER_EMAIL)
    assert res.status_code == 200, res.text
    token = res.json()["accessToken"]

    st = client.get("/api/tenant/restore-status", headers=_bearer(token)).json()
    assert st["canRestore"] is False
    assert st["restoreBlockedReason"] == "not_owner"
    res = client.post("/api/tenant/restore", headers=_bearer(token))
    assert res.status_code == 403
    assert (await _tenant(db, seed["tid"])).status == "quarantined"


async def test_restore_requires_fresh_authentication(db):
    """A silently refreshed session (no auth_time) must re-enter the password."""
    seed = await _seed(db)
    await _owner_deletes(db, seed)
    token = _stale_token(seed["owner_id"], seed["tid"], OWNER_EMAIL)
    client = _client()

    st = client.get("/api/tenant/restore-status", headers=_bearer(token)).json()
    assert st["reauthRequired"] is True and st["hasPassword"] is True

    res = client.post("/api/tenant/restore", headers=_bearer(token))
    assert res.status_code == 403
    assert res.json()["detail"]["error"] == "reauth_required"
    res = client.post("/api/tenant/restore", headers=_bearer(token), json={"current_password": "wrong-password"})
    assert res.status_code == 400
    assert (await _tenant(db, seed["tid"])).status == "quarantined"

    res = client.post("/api/tenant/restore", headers=_bearer(token), json={"current_password": TEST_PASSWORD})
    assert res.status_code == 200, res.text
    assert (await _tenant(db, seed["tid"])).status == "active"


async def test_impersonation_cannot_restore(db):
    seed = await _seed(db)
    await _owner_deletes(db, seed)
    token, _ = create_access_token(AccessTokenClaims(
        user_id=str(seed["owner_id"]), tenant_id=str(seed["tid"]), role="customer_admin",
        email=OWNER_EMAIL, impersonator="support@example.test", auth_time=int(_now().timestamp()),
    ))
    res = _client().post("/api/tenant/restore", headers=_bearer(token))
    assert res.status_code == 403
    assert (await _tenant(db, seed["tid"])).status == "quarantined"


@pytest.mark.parametrize("cookie_name", ["dialtact_refresh", "voxly_refresh"])
async def test_refresh_cookie_lands_on_restore_screen_but_is_not_fresh(db, cookie_name):
    seed = await _seed(db)
    await _owner_deletes(db, seed)
    signin = _client()
    assert _login(signin, OWNER_EMAIL, remember=True).status_code == 200
    raw_refresh = signin.cookies.get("dialtact_refresh")
    assert raw_refresh

    client = _client()
    client.cookies.set(cookie_name, raw_refresh)
    res = client.post("/api/auth/refresh")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["tenant"]["status"] == "quarantined"
    # The refresh keeps the "keep me signed in" family, but is not a fresh sign-in.
    assert decode_access_token(body["accessToken"]).auth_time is None
    st = client.get("/api/tenant/restore-status", headers=_bearer(body["accessToken"])).json()
    assert st["canRestore"] is True and st["reauthRequired"] is True


async def test_google_sign_in_reaches_restore_and_can_restore(db, monkeypatch):
    seed = await _seed(db, google_only=True)
    # Google owner deletes via a fresh Google session.
    first = await auth_service.login_or_create_oauth_user(email=GOOGLE_EMAIL, full_name="Owner", provider="google")
    client = _client()
    res = client.post(
        "/api/tenant/delete",
        json={"confirmation_name": "delete", "forfeit_balance_confirmed": True},
        headers=_bearer(first["accessToken"]),
    )
    assert res.status_code == 200, res.text

    async def _fake_verify(_id_token):
        return {"email": GOOGLE_EMAIL, "name": "Owner", "email_verified": "true"}

    monkeypatch.setattr("server.services.saas.google_oauth_service.verify_google_id_token", _fake_verify)
    res = client.post("/api/auth/google", json={"idToken": "fixture-id-token"})
    assert res.status_code == 200, res.text
    body = res.json()
    # The same workspace — not a silently created empty one.
    assert body["tenant"]["tenantId"] == str(seed["tid"])
    assert body["tenant"]["status"] == "quarantined"
    assert decode_access_token(body["accessToken"]).auth_time is not None
    res = client.post("/api/tenant/restore", headers=_bearer(body["accessToken"]))
    assert res.status_code == 200, res.text
    assert (await _tenant(db, seed["tid"])).status == "active"


async def test_live_workspace_wins_over_pending_one(db):
    seed = await _seed(db)
    other = uuid.uuid4()
    async with db() as s:
        s.add(Tenant(tenant_id=other, name="Second", status="active", plan="starter", limits={}))
        s.add(TenantMembership(user_id=seed["owner_id"], tenant_id=other, role="customer_admin",
                               created_at=_now() + timedelta(days=1)))
        await s.commit()
    await _owner_deletes(db, seed)
    body = _login(_client(), OWNER_EMAIL).json()
    assert body["tenant"]["tenantId"] == str(other)


# ---------------------------------------------------------------------------
# After the grace period
# ---------------------------------------------------------------------------
async def _expire_grace(factory, tid) -> None:
    async with factory() as s:
        t = await s.get(Tenant, tid)
        t.scheduled_purge_at = _now() - timedelta(minutes=1)
        await s.commit()


async def test_expired_grace_sign_in_explains_workspace_is_gone(db, monkeypatch):
    seed = await _seed(db)
    await _owner_deletes(db, seed)
    stale = _client()
    token = _login(stale, OWNER_EMAIL).json()["accessToken"]
    await _expire_grace(db, seed["tid"])

    res = _login(_client(), OWNER_EMAIL)
    assert res.status_code == 403
    err = res.json()["detail"]["error"]
    assert err["code"] == "workspace_deleted"
    assert "permanently deleted" in err["message"]

    # A session obtained during the grace period can no longer restore.
    res = stale.post("/api/tenant/restore", headers=_bearer(token))
    assert res.status_code == 403
    assert res.json()["detail"]["error"] == "workspace_deleted"
    assert (await _tenant(db, seed["tid"])).status == "quarantined"

    # Google: same answer, and no fresh empty workspace is created behind the user's back.
    with pytest.raises(ValueError, match="workspace_deleted"):
        await auth_service.login_or_create_oauth_user(email=OWNER_EMAIL, full_name="Owner", provider="google")
    async with db() as s:
        assert len((await s.execute(select(Tenant))).scalars().all()) == 1

    # Refresh cookie: explicit code, cookie cleared.
    res = stale.post("/api/auth/refresh")
    assert res.status_code == 401
    assert res.json()["detail"]["error"]["code"] == "workspace_deleted"


async def test_restore_direct_after_expiry_is_410(db):
    seed = await _seed(db)
    await _owner_deletes(db, seed)
    await _expire_grace(db, seed["tid"])
    # Route-level check (bypassing the session guard) still refuses.
    from server.services.saas.tenant_guard import SubscriberPrincipal
    from server.auth.subscriber_dependencies import require_subscriber_jwt

    async def _principal():
        return SubscriberPrincipal(user_id=seed["owner_id"], tenant_id=seed["tid"], role="customer_admin",
                                   email=OWNER_EMAIL, auth_time=int(_now().timestamp()))

    app_mod.app.dependency_overrides[require_subscriber_jwt] = _principal
    res = _client().post("/api/tenant/restore")
    assert res.status_code == 410
    assert res.json()["detail"]["error"] == "grace_period_expired"


async def test_past_due_workspace_is_not_reported_as_deleted(db):
    """Only the deletion lifecycle may say 'quarantined' — the console reads it as deletion."""
    seed = await _seed(db)
    async with db() as s:
        (await s.get(Tenant, seed["tid"])).status = "past_due"
        await s.commit()
    token = _stale_token(seed["owner_id"], seed["tid"], OWNER_EMAIL)
    res = _client().get("/api/tenant/delete-preflight", headers=_bearer(token))
    assert res.status_code == 403
    assert res.json()["detail"]["error"] == "tenant_inactive"


async def test_legacy_tenants_delete_gets_a_grace_period(db):
    seed = await _seed(db)
    await auth_service.delete_tenant(seed["tid"], seed["owner_id"])
    tenant = await _tenant(db, seed["tid"])
    assert tenant.status == "quarantined"
    assert tenant.deleted_at is None
    assert _aware(tenant.scheduled_purge_at) > _now() + timedelta(days=13)
    # The worker must not claim it during the grace period.
    assert await teardown_worker.process_one_teardown() is False
