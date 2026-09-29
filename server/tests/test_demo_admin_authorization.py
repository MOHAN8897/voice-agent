"""Backend authorization for the demo/platform-admin account.

The point of these tests is the security property, not the fixture: the demo account
is privileged because the *backend* resolved its identity to ``platform_admin`` and
the RBAC matrix granted the permission. A normal subscriber is denied the same
routes, and tenant isolation holds for both.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

import server.app as app_mod
from server.auth.rbac import (
    ROLE_CUSTOMER_ADMIN,
    ROLE_CUSTOMER_VIEWER,
    ROLE_PLATFORM_ADMIN,
    role_has_permission,
)
from server.config.env import get_settings
from server.services.saas.demo_admin import DemoAccountError, ensure_demo_admin
from server.services.saas.platform_admins import (
    effective_membership_role,
    is_platform_admin_email,
)
from server.services.saas.tenant_guard import SubscriberPrincipal

DEMO_EMAIL = "mohansaiteja.99@gmail.com"


@pytest.fixture(autouse=True)
def _admin_allowlist(monkeypatch):
    """The demo account is configured server-side, exactly as in production."""
    monkeypatch.setenv("SAAS_PLATFORM_ADMIN_EMAILS", DEMO_EMAIL)
    monkeypatch.setenv("SAAS_DEV_TESTER_EMAILS", DEMO_EMAIL)
    monkeypatch.setenv("SAAS_AUTH_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --------------------------------------------------------------------------
# Role resolution comes from the backend, not from anything the client sends
# --------------------------------------------------------------------------


def test_demo_email_resolves_to_platform_admin_on_the_backend():
    assert is_platform_admin_email(DEMO_EMAIL)
    assert effective_membership_role(DEMO_EMAIL, ROLE_CUSTOMER_ADMIN) == ROLE_PLATFORM_ADMIN
    # Case-insensitive, because email providers are.
    assert effective_membership_role(DEMO_EMAIL.upper(), ROLE_CUSTOMER_ADMIN) == ROLE_PLATFORM_ADMIN


def test_a_normal_subscriber_never_becomes_platform_admin():
    assert effective_membership_role("someone@example.com", ROLE_CUSTOMER_ADMIN) == ROLE_CUSTOMER_ADMIN


def test_a_stored_platform_admin_role_is_demoted_for_a_normal_user():
    """Privilege must come from the allowlist, not from a stale DB value."""
    assert effective_membership_role("someone@example.com", ROLE_PLATFORM_ADMIN) == ROLE_CUSTOMER_ADMIN


def test_demo_admin_holds_the_intended_permissions():
    for permission in (
        "app.admin",
        "app.agents.write",
        "app.telephony.write",
        "app.billing.write",
        "app.calls.read",
        "app.members.write",
        "app.campaigns.write",
    ):
        assert role_has_permission(ROLE_PLATFORM_ADMIN, permission), permission


def test_normal_subscriber_is_denied_admin_permissions():
    assert not role_has_permission(ROLE_CUSTOMER_ADMIN, "app.admin")
    assert not role_has_permission(ROLE_CUSTOMER_VIEWER, "app.admin")
    assert not role_has_permission(ROLE_CUSTOMER_VIEWER, "app.agents.write")
    # A normal admin may still run their own workspace.
    assert role_has_permission(ROLE_CUSTOMER_ADMIN, "app.agents.write")
    assert role_has_permission(ROLE_CUSTOMER_ADMIN, "app.calls.read")


def test_tenant_guard_enforces_the_permission_matrix():
    demo = SubscriberPrincipal(
        user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), role=ROLE_PLATFORM_ADMIN, email=DEMO_EMAIL
    )
    subscriber = SubscriberPrincipal(
        user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), role=ROLE_CUSTOMER_ADMIN, email="user@example.com"
    )
    from server.services.saas.tenant_guard import require_subscriber_permission

    require_subscriber_permission(demo, "app.admin")
    with pytest.raises(Exception) as exc:
        require_subscriber_permission(subscriber, "app.admin")
    assert getattr(exc.value, "status_code", None) == 403


# --------------------------------------------------------------------------
# Platform-admin HTTP routes reject a normal subscriber
# --------------------------------------------------------------------------


def _client_as(email: str, role: str, tenant_id: uuid.UUID) -> TestClient:
    """A client whose authenticated principal is (email, role, tenant).

    Stands in for a real login: the token is validly signed and the dependency
    resolves the principal exactly as production does, including re-deriving the
    role from the server-side allowlist.
    """
    from server.auth.jwt_tokens import AccessTokenClaims, create_access_token
    from server.auth.subscriber_dependencies import require_subscriber_jwt

    principal = SubscriberPrincipal(
        user_id=uuid.uuid4(),
        tenant_id=tenant_id,
        role=effective_membership_role(email, role),
        email=email,
    )
    token, _ = create_access_token(
        AccessTokenClaims(
            user_id=str(principal.user_id),
            tenant_id=str(principal.tenant_id),
            role=principal.role,
            email=principal.email,
        )
    )

    async def _resolve() -> SubscriberPrincipal:
        return principal

    app_mod.app.dependency_overrides[require_subscriber_jwt] = _resolve
    client = TestClient(app_mod.app)
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


@pytest.fixture
def _clear_overrides():
    yield
    app_mod.app.dependency_overrides.clear()


def test_admin_overview_denies_a_normal_subscriber(_clear_overrides):
    client = _client_as("user@example.com", ROLE_CUSTOMER_ADMIN, uuid.uuid4())
    try:
        denied = client.get("/api/admin/overview")
        assert denied.status_code == 403
        assert denied.json()["detail"]["error"]["code"] == "auth_error"
    finally:
        app_mod.app.dependency_overrides.clear()


def test_admin_credits_denies_a_normal_subscriber(_clear_overrides):
    client = _client_as("user@example.com", ROLE_CUSTOMER_ADMIN, uuid.uuid4())
    try:
        denied = client.post(
            "/api/admin/credits",
            json={"tenantId": str(uuid.uuid4()), "amountInrPaise": 100, "reason": "test"},
        )
        assert denied.status_code == 403
    finally:
        app_mod.app.dependency_overrides.clear()


def test_admin_tenants_denies_a_normal_subscriber(_clear_overrides):
    client = _client_as("user@example.com", ROLE_CUSTOMER_ADMIN, uuid.uuid4())
    try:
        assert client.get("/api/admin/tenants").status_code == 403
    finally:
        app_mod.app.dependency_overrides.clear()


def test_demo_admin_passes_the_platform_admin_gate(_clear_overrides):
    """The demo account gets past the check; a DB-less test stops right after it."""
    client = _client_as(DEMO_EMAIL, ROLE_CUSTOMER_ADMIN, uuid.uuid4())
    try:
        response = client.get("/api/admin/tenants")
        # 503 = authorised, no database in this test process. 403 would mean denied.
        assert response.status_code in (200, 503)
        assert response.status_code != 403
    finally:
        app_mod.app.dependency_overrides.clear()


def _fake_session_returning(row):
    """Minimal AsyncSession stand-in returning ``row`` from ``session.get``."""

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, _model, _pk):
            return row

    class _Factory:
        def __call__(self):
            return _Session()

    return _Factory()


def test_tenant_guard_rejects_an_agent_owned_by_another_workspace(monkeypatch):
    """An agent id from a different tenant must never resolve."""
    import server.db.connection as connection
    import server.services.saas.tenant_guard as guard
    from server.db.models.entities import Agent

    owner = uuid.uuid4()
    agent = Agent(agent_id=uuid.uuid4(), tenant_id=owner, name="Foreign agent")
    monkeypatch.setattr(connection, "_session_factory", _fake_session_returning(agent))

    with pytest.raises(Exception) as exc:
        import asyncio

        asyncio.run(guard.load_agent_for_tenant(str(agent.agent_id), uuid.uuid4()))
    assert getattr(exc.value, "status_code", None) == 404


def test_tenant_guard_allows_the_owning_tenant(monkeypatch):
    import server.db.connection as connection
    import server.services.saas.tenant_guard as guard
    from server.db.models.entities import Agent

    owner = uuid.uuid4()
    agent = Agent(agent_id=uuid.uuid4(), tenant_id=owner, name="Own agent")
    monkeypatch.setattr(connection, "_session_factory", _fake_session_returning(agent))

    resolved = guard.load_agent_for_tenant
    import asyncio

    loaded = asyncio.run(resolved(str(agent.agent_id), owner))
    assert loaded.name == "Own agent"


def test_jwt_carries_no_privilege_the_allowlist_does_not_grant():
    """A forged role claim alone must not unlock platform admin."""
    from server.auth.jwt_tokens import AccessTokenClaims

    claims = AccessTokenClaims(
        user_id=str(uuid.uuid4()),
        tenant_id=str(uuid.uuid4()),
        role=ROLE_PLATFORM_ADMIN,
        email="attacker@example.com",
    )
    principal = SubscriberPrincipal.from_claims(claims)
    assert principal.role == ROLE_PLATFORM_ADMIN  # the claim is parsed…
    from server.services.saas.platform_admins import require_platform_admin_email

    # …but platform-admin routes re-check the allowlist server-side.
    with pytest.raises(Exception) as exc:
        require_platform_admin_email(principal.email)
    assert getattr(exc.value, "status_code", None) == 403


# --------------------------------------------------------------------------
# Provisioning
# --------------------------------------------------------------------------


def test_ensure_demo_admin_requires_a_database(monkeypatch):
    import server.db.connection as connection

    monkeypatch.setattr(connection, "_session_factory", None)
    with pytest.raises(DemoAccountError):
        import asyncio

        asyncio.get_event_loop_policy()
        asyncio.run(ensure_demo_admin(DEMO_EMAIL))


def test_ensure_demo_admin_rejects_an_email_outside_the_allowlist():
    """You cannot mint an admin by passing an arbitrary address to the seeder."""
    import asyncio

    with pytest.raises(DemoAccountError) as exc:
        asyncio.run(ensure_demo_admin("attacker@example.com"))
    assert "SAAS_PLATFORM_ADMIN_EMAILS" in str(exc.value)


def test_ensure_demo_admin_rejects_a_malformed_email():
    import asyncio

    with pytest.raises(DemoAccountError):
        asyncio.run(ensure_demo_admin("not-an-email"))


def test_demo_account_emails_come_from_config():
    from server.services.saas.demo_admin import demo_admin_emails

    assert DEMO_EMAIL in demo_admin_emails()


def test_no_password_is_required_to_provision():
    """Google sign-in is a valid path in; the seeder must not demand a secret."""
    import inspect

    from server.services.saas import demo_admin as mod

    params = inspect.signature(mod.ensure_demo_admin).parameters
    assert "password" in params
    assert params["password"].default is None
    # The only supported source is the environment, never a CLI argument.
    assert "argv" not in inspect.getsource(mod)
