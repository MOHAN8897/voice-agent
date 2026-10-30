"""Admin team (Roles & access): stored platform admins, safeguards, revocation, audit.

SQLite stands in for Postgres (JSONB becomes JSON for the test only). Every
account and password here is a fixture created by the test; nothing touches real
admin accounts or env credentials.
"""
from __future__ import annotations

import contextlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import JSON, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from server.auth import admin_sessions, rbac
from server.auth.admin_roles import ADMIN_ROLES, PERMISSION_INFO, describe_roles
from server.auth.session import cookie_names, create_session_token, parse_session_token
from server.config.env import get_settings
from server.db.models.phase5_models import AuditLog
from server.db.models.platform_admin_models import PlatformAdminAccount
from server.db.models.saas_models import User
from server.services.saas import activity_log, admin_accounts
from server.tests.conftest import DEV_TEST_BASE_URL

TABLES = [PlatformAdminAccount, AuditLog, User]
CSRF = "fixture-csrf-token"
GOOD_PASSWORD = "Fixture-Passphrase-7391"


@pytest.fixture
async def db(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DEV_PORTAL_USERNAME", "fixture-owner")
    monkeypatch.setenv("DEV_PORTAL_PASSWORD", "fixture-owner-password-1")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    get_settings.cache_clear()
    changed = [(c, c.type) for m in TABLES for c in m.__table__.columns if isinstance(c.type, JSONB)]
    for c, _ in changed:
        c.type = JSON()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'admins.db'}")
    try:
        async with engine.begin() as conn:
            for m in TABLES:
                await conn.run_sync(lambda sync, t=m.__table__: t.create(sync))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(admin_accounts, "get_session_factory", lambda: factory)
        monkeypatch.setattr(activity_log, "get_session_factory", lambda: factory)
        admin_sessions.clear_snapshot_for_tests()
        await admin_sessions.refresh(force=True)
        yield factory
    finally:
        admin_sessions.clear_snapshot_for_tests()
        await engine.dispose()
        for c, original in changed:
            c.type = original
        get_settings.cache_clear()


def _client(token: str | None) -> AsyncClient:
    import server.app as app_mod

    client = AsyncClient(transport=ASGITransport(app=app_mod.app), base_url=DEV_TEST_BASE_URL)
    names = cookie_names()
    if token:
        client.cookies.set(names["dev"], token)
    client.cookies.set(names["dev_csrf"], CSRF)
    client.headers["X-CSRF-Token"] = CSRF
    return client


def _owner() -> AsyncClient:
    """The env-configured built-in login (a super admin)."""
    return _client(create_session_token("dev", "fixture-owner", None, rbac.ROLE_SUPER_ADMIN))


async def _invite(client: AsyncClient, email: str, role: str = rbac.ROLE_SUPER_ADMIN, username: str | None = None):
    res = await client.post(
        "/api/dev/admin/team/invite",
        json={"email": email, "fullName": "Fixture Person", "username": username, "role": role, "reason": "fixture onboarding"},
    )
    assert res.status_code == 200, res.text
    return res.json()


def _token_from(link: dict) -> str:
    return link["path"].split("token=", 1)[1]


async def _activate(client: AsyncClient, email: str, role: str = rbac.ROLE_SUPER_ADMIN, username: str | None = None):
    body = await _invite(client, email, role, username)
    accepted = await client.post(
        "/api/dev/admin-invite/accept", json={"token": _token_from(body["link"]), "password": GOOD_PASSWORD}
    )
    assert accepted.status_code == 200, accepted.text
    return body["admin"]


@contextlib.asynccontextmanager
async def _using(client: AsyncClient):
    try:
        yield client
    finally:
        await client.aclose()


async def _sign_in(username: str) -> AsyncClient:
    client = _client(None)
    res = await client.post("/api/dev/login", json={"username": username, "password": GOOD_PASSWORD})
    assert res.json().get("ok") is True, res.text
    client.headers["X-CSRF-Token"] = res.json()["csrf_token"]
    return client


async def _audit_rows(factory, action: str | None = None):
    async with factory() as s:
        stmt = select(AuditLog).where(AuditLog.resource_type == "platform_admin")
        if action:
            stmt = stmt.where(AuditLog.action == action)
        return (await s.execute(stmt)).scalars().all()


# --------------------------------------------------------------------------- catalogue


def test_every_permission_has_plain_language_description():
    assert set(rbac._PERMISSIONS) <= set(PERMISSION_INFO)
    catalogue = describe_roles()
    assert catalogue["customRolesSupported"] is False
    keys = [r["key"] for r in catalogue["roles"]]
    assert keys[0] == rbac.ROLE_SUPER_ADMIN
    assert {r["key"] for r in ADMIN_ROLES if r["assignable"]} >= {rbac.ROLE_SUPER_ADMIN, rbac.ROLE_SUPPORT_AGENT}


def test_only_super_admin_manages_admins_and_legacy_roles_keep_access():
    assert rbac.role_has_permission(rbac.ROLE_SUPER_ADMIN, rbac.PERMISSION_MANAGE_ADMINS)
    for role in (rbac.ROLE_ADMINISTRATOR, rbac.ROLE_DEVELOPER, rbac.ROLE_PLATFORM_ADMIN, rbac.ROLE_SUPPORT_AGENT):
        assert not rbac.role_has_permission(role, rbac.PERMISSION_MANAGE_ADMINS)
    # Existing roles keep every permission they had; super admin holds all of them.
    for name, allowed in rbac._PERMISSIONS.items():
        if rbac.ROLE_DEVELOPER in allowed:
            assert rbac.ROLE_SUPER_ADMIN in allowed, name
    assert rbac.role_has_permission(rbac.ROLE_DEVELOPER, "dev.admin.tenants")
    # Narrow roles stay narrow.
    assert not rbac.role_has_permission(rbac.ROLE_SUPPORT_AGENT, "dev.admin.billing")
    assert not rbac.role_has_permission(rbac.ROLE_SUPPORT_AGENT, "dev.stack.write")
    assert not rbac.role_has_permission(rbac.ROLE_STACK_ENGINEER, "dev.admin.users")


def test_builtin_legacy_session_is_upgraded_to_super_admin(monkeypatch):
    monkeypatch.setenv("DEV_PORTAL_USERNAME", "fixture-owner")
    monkeypatch.setenv("DEV_PORTAL_PASSWORD", "fixture-owner-password-1")
    get_settings.cache_clear()
    try:
        legacy = parse_session_token(create_session_token("dev", "fixture-owner", None, "developer"), "dev")
        assert legacy is not None and legacy.role == rbac.ROLE_SUPER_ADMIN
        other = parse_session_token(create_session_token("dev", "synthetic-test-developer", None, "developer"), "dev")
        assert other is not None and other.role == "developer"
    finally:
        get_settings.cache_clear()


# --------------------------------------------------------------------------- permission enforcement


async def test_non_manager_gets_403_on_every_management_endpoint(db):
    token = create_session_token("dev", "fixture-administrator", None, rbac.ROLE_ADMINISTRATOR)
    async with _client(token) as client:
        assert (await client.get("/api/dev/admin/team")).status_code == 403
        assert (await client.get("/api/dev/admin/team/activity")).status_code == 403
        res = await client.post(
            "/api/dev/admin/team/invite",
            json={"email": "x@example.test", "role": "super_admin", "reason": "should fail"},
        )
        assert res.status_code == 403
        assert (await client.post(f"/api/dev/admin/team/{uuid.uuid4()}/remove", json={"reason": "nope nope"})).status_code == 403
        roles = await client.get("/api/dev/admin/team/roles")
        assert roles.status_code == 200
        assert roles.json()["me"]["canManageAdmins"] is False


async def test_builtin_login_still_works_and_is_super_admin(db):
    async with _client(None) as client:
        bad = await client.post("/api/dev/login", json={"username": "fixture-owner", "password": "wrong"})
        assert bad.json()["ok"] is False
        ok = await client.post("/api/dev/login", json={"username": "Fixture-Owner", "password": "fixture-owner-password-1"})
        assert ok.json()["ok"] is True and ok.json()["role"] == rbac.ROLE_SUPER_ADMIN
        client.headers["X-CSRF-Token"] = ok.json()["csrf_token"]
        listed = await client.get("/api/dev/admin/team")
        assert listed.status_code == 200
        assert listed.json()["builtin"] == {
            "configured": True, "username": "fixture-owner", "role": "super_admin", "isSelf": True
        }
        assert listed.json()["store"]["ready"] is True


# --------------------------------------------------------------------------- invite flow


async def test_invite_needs_reason_and_valid_role(db):
    async with _owner() as client:
        res = await client.post(
            "/api/dev/admin/team/invite", json={"email": "a@example.test", "role": "super_admin", "reason": "x"}
        )
        assert res.status_code == 400 and res.json()["detail"]["error"]["code"] == "reason_required"
        res = await client.post(
            "/api/dev/admin/team/invite", json={"email": "a@example.test", "role": "developer", "reason": "legacy role"}
        )
        assert res.status_code == 400 and res.json()["detail"]["error"]["code"] == "invalid_role"
        res = await client.post(
            "/api/dev/admin/team/invite",
            json={"email": "a@example.test", "username": "fixture-owner", "role": "support_agent", "reason": "reserved name"},
        )
        assert res.status_code == 409


async def test_invite_accept_sign_in_and_audit(db):
    async with _owner() as client:
        body = await _invite(client, "Priya@Example.test", rbac.ROLE_SUPPORT_AGENT)
        admin, link = body["admin"], body["link"]
        assert admin["status"] == "invited" and admin["username"] == "priya" and admin["email"] == "priya@example.test"
        assert link["emailed"] is False and link["purpose"] == "invite"
        raw = _token_from(link)
        async with db() as s:
            stored = (await s.execute(select(PlatformAdminAccount))).scalar_one()
            assert stored.invite_token_hash and stored.invite_token_hash != raw and raw not in stored.invite_token_hash
            assert stored.password_hash == ""

        # The link cannot be used to sign in before a password exists.
        assert (await client.post("/api/dev/login", json={"username": "priya", "password": GOOD_PASSWORD})).json()["ok"] is False

        info = await client.post("/api/dev/admin-invite/inspect", json={"token": raw})
        assert info.status_code == 200 and info.json()["username"] == "priya"
        weak = await client.post("/api/dev/admin-invite/accept", json={"token": raw, "password": "short"})
        assert weak.status_code == 400
        weak = await client.post("/api/dev/admin-invite/accept", json={"token": raw, "password": "priya-is-my-password"})
        assert weak.status_code == 400
        ok = await client.post("/api/dev/admin-invite/accept", json={"token": raw, "password": GOOD_PASSWORD})
        assert ok.status_code == 200
        # Single use.
        again = await client.post("/api/dev/admin-invite/accept", json={"token": raw, "password": GOOD_PASSWORD})
        assert again.status_code == 400

    async with _using(await _sign_in("priya@example.test")) as priya:
        me = await priya.get("/api/auth/dev-me")
        assert me.status_code == 200 and me.json()["role"] == rbac.ROLE_SUPPORT_AGENT and me.json()["subject"] == "priya"
        assert (await priya.get("/api/dev/admin/team")).status_code == 403

    actions = {r.action for r in await _audit_rows(db)}
    assert {"platform_admin.invite", "platform_admin.invite_accepted"} <= actions
    invite_row = (await _audit_rows(db, "platform_admin.invite"))[0]
    assert invite_row.actor == "fixture-owner" and invite_row.payload["reason"] == "fixture onboarding"
    assert raw not in str(invite_row.payload)


async def test_expired_link_is_refused(db):
    async with _owner() as client:
        body = await _invite(client, "late@example.test", rbac.ROLE_BILLING_ADMIN)
        async with db() as s:
            acct = (await s.execute(select(PlatformAdminAccount))).scalar_one()
            acct.invite_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            await s.commit()
        res = await client.post(
            "/api/dev/admin-invite/accept", json={"token": _token_from(body["link"]), "password": GOOD_PASSWORD}
        )
        assert res.status_code == 410
        listed = (await client.get("/api/dev/admin/team")).json()["admins"]
        assert listed[0]["link"]["state"] == "expired"
        resent = await client.post(
            f"/api/dev/admin/team/{body['admin']['id']}/resend-invite", json={"reason": "new link please"}
        )
        assert resent.status_code == 200
        ok = await client.post(
            "/api/dev/admin-invite/accept", json={"token": _token_from(resent.json()["link"]), "password": GOOD_PASSWORD}
        )
        assert ok.status_code == 200


# --------------------------------------------------------------------------- safeguards


async def test_cannot_change_yourself(db):
    async with _owner() as owner:
        alice = await _activate(owner, "alice@example.test")
    async with _using(await _sign_in("alice")) as client:
        for path, body in (
            ("suspend", {"reason": "self harm", "confirm": "alice"}),
            ("remove", {"reason": "self harm", "confirm": "alice"}),
            ("role", {"reason": "self harm", "confirm": "alice", "role": "support_agent"}),
            ("reset-password", {"reason": "self harm", "confirm": "alice"}),
        ):
            res = await client.post(f"/api/dev/admin/team/{alice['id']}/{path}", json=body)
            assert res.status_code == 403, path
            assert res.json()["detail"]["error"]["code"] == "self_change"


async def test_last_super_admin_cannot_be_demoted_suspended_or_removed(db):
    async with _owner() as owner:
        alice = await _activate(owner, "alice@example.test")
        for path, body in (
            ("role", {"reason": "demote last", "confirm": "alice", "role": "administrator"}),
            ("suspend", {"reason": "suspend last", "confirm": "alice"}),
            ("remove", {"reason": "remove last", "confirm": "alice"}),
        ):
            res = await owner.post(f"/api/dev/admin/team/{alice['id']}/{path}", json=body)
            assert res.status_code == 409, path
            assert res.json()["detail"]["error"]["code"] == "last_super_admin"
        listed = (await owner.get("/api/dev/admin/team")).json()["admins"]
        assert listed[0]["isLastSuperAdmin"] is True

        await _activate(owner, "bob@example.test")
        # Typed confirmation is required for super-admin role changes.
        no_confirm = await owner.post(
            f"/api/dev/admin/team/{alice['id']}/role", json={"reason": "step down", "role": "administrator"}
        )
        assert no_confirm.status_code == 400 and no_confirm.json()["detail"]["error"]["code"] == "confirmation_required"
        ok = await owner.post(
            f"/api/dev/admin/team/{alice['id']}/role",
            json={"reason": "step down", "role": "administrator", "confirm": "ALICE"},
        )
        assert ok.status_code == 200 and ok.json()["admin"]["role"] == "administrator"
    row = (await _audit_rows(db, "platform_admin.role_changed"))[0]
    assert row.payload["from"] == "super_admin" and row.payload["to"] == "administrator"


# --------------------------------------------------------------------------- revocation


async def test_suspend_role_change_and_sign_out_take_effect_on_live_sessions(db):
    async with _owner() as owner:
        await _activate(owner, "alice@example.test")
        carol = await _activate(owner, "carol@example.test", rbac.ROLE_SUPER_ADMIN)
        async with _using(await _sign_in("carol")) as session:
            assert (await session.get("/api/dev/admin/team")).status_code == 200

            # Demotion applies to the cookie she already holds.
            await owner.post(
                f"/api/dev/admin/team/{carol['id']}/role",
                json={"reason": "least privilege", "role": "support_agent", "confirm": "carol"},
            )
            assert (await session.get("/api/dev/admin/team")).status_code == 403
            assert (await session.get("/api/auth/dev-me")).json()["role"] == "support_agent"

            # Sign out everywhere ends the session.
            res = await owner.post(f"/api/dev/admin/team/{carol['id']}/sign-out", json={"reason": "lost laptop"})
            assert res.status_code == 200
            assert (await session.get("/api/auth/dev-me")).status_code == 401

        async with _using(await _sign_in("carol")) as session:
            missing = await owner.post(f"/api/dev/admin/team/{carol['id']}/suspend", json={"reason": "left the company"})
            assert missing.status_code == 400  # typed confirmation required
            res = await owner.post(
                f"/api/dev/admin/team/{carol['id']}/suspend", json={"reason": "left the company", "confirm": "carol"}
            )
            assert res.status_code == 200 and res.json()["admin"]["status"] == "suspended"
            assert (await session.get("/api/auth/dev-me")).status_code == 401
        blocked = await _client(None).post("/api/dev/login", json={"username": "carol", "password": GOOD_PASSWORD})
        assert blocked.json()["ok"] is False

        res = await owner.post(f"/api/dev/admin/team/{carol['id']}/reactivate", json={"reason": "came back"})
        assert res.status_code == 200 and res.json()["admin"]["status"] == "active"
        session = await _sign_in("carol")
        await session.aclose()


async def test_reset_password_revokes_and_issues_one_time_link(db):
    async with _owner() as owner:
        await _activate(owner, "alice@example.test")
        dan = await _activate(owner, "dan@example.test", rbac.ROLE_STACK_ENGINEER)
        async with _using(await _sign_in("dan")) as session:
            res = await owner.post(
                f"/api/dev/admin/team/{dan['id']}/reset-password", json={"reason": "suspected leak", "confirm": "dan"}
            )
            assert res.status_code == 200
            link = res.json()["link"]
            assert link["purpose"] == "reset"
            # No password is ever generated or returned; only the one-time link.
            assert GOOD_PASSWORD not in res.text and "tempPassword" not in res.text
            assert (await session.get("/api/auth/dev-me")).status_code == 401
        old = await _client(None).post("/api/dev/login", json={"username": "dan", "password": GOOD_PASSWORD})
        assert old.json()["ok"] is False
        new_password = GOOD_PASSWORD + "-new"
        ok = await owner.post("/api/dev/admin-invite/accept", json={"token": _token_from(link), "password": new_password})
        assert ok.status_code == 200
        res = await _client(None).post("/api/dev/login", json={"username": "dan", "password": new_password})
        assert res.json()["ok"] is True


async def test_remove_frees_identity_and_activity_lists_events(db):
    async with _owner() as owner:
        await _activate(owner, "alice@example.test")
        erin = await _activate(owner, "erin@example.test", rbac.ROLE_SUPPORT_AGENT)
        res = await owner.post(f"/api/dev/admin/team/{erin['id']}/remove", json={"reason": "offboarded", "confirm": "nope"})
        assert res.status_code == 400
        res = await owner.post(f"/api/dev/admin/team/{erin['id']}/remove", json={"reason": "offboarded", "confirm": "erin"})
        assert res.status_code == 200
        listed = (await owner.get("/api/dev/admin/team")).json()["admins"]
        assert [a["username"] for a in listed] == ["alice"]
        assert (await _client(None).post("/api/dev/login", json={"username": "erin", "password": GOOD_PASSWORD})).json()["ok"] is False
        # Email and username can be reused after removal.
        await _invite(owner, "erin@example.test", rbac.ROLE_SUPPORT_AGENT)

        activity = (await owner.get("/api/dev/admin/team/activity")).json()
        actions = [e["action"] for e in activity["entries"]]
        assert "platform_admin.removed" in actions
        removed = next(e for e in activity["entries"] if e["action"] == "platform_admin.removed")
        assert removed["payload"]["email"] == "erin@example.test" and removed["payload"]["reason"] == "offboarded"
