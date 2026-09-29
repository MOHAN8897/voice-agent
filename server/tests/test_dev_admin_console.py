"""Tests for the admin console endpoints the SaaS maintenance UI depends on.

The frontend renders these verbatim, so the contract matters: a field rename or a
missing key would blank a panel or, worse, show a plausible wrong number.
"""
from __future__ import annotations

import pytest

from server.auth import rbac


def test_access_serves_the_enforcement_matrix_not_a_copy():
    """The permission screen must read the same table the API authorizes against."""
    from server.routes.dev_admin import admin_access

    class _Session:
        subject = "dev"
        role = rbac.ROLE_DEVELOPER
        tenant_id = "00000000-0000-4000-8000-000000000001"
        kind = "dev"

    out = __import__("asyncio").run(admin_access(_Session()))

    assert set(out) == {
        "roles",
        "permissions",
        "currentRole",
        "currentSubject",
        "currentPermissions",
    }
    # Every served permission must exist in the real RBAC table, and vice versa.
    assert {p["name"] for p in out["permissions"]} == set(rbac._PERMISSIONS)
    for perm in out["permissions"]:
        assert set(perm["roles"]) == set(rbac._PERMISSIONS[perm["name"]])
        assert perm["devOnly"] == perm["name"].startswith("dev.")
    assert out["roles"] == sorted(out["roles"])
    assert out["permissions"] == sorted(out["permissions"], key=lambda p: p["name"])


def test_access_reports_the_callers_own_permissions():
    """The screen highlights the current role; that must be derived, not hard-coded."""
    from server.routes.dev_admin import admin_access

    class _PlatformAdmin:
        subject = "root@example.com"
        role = rbac.ROLE_PLATFORM_ADMIN
        tenant_id = "00000000-0000-4000-8000-000000000001"
        kind = "dev"

    out = __import__("asyncio").run(admin_access(_PlatformAdmin()))
    assert out["currentRole"] == rbac.ROLE_PLATFORM_ADMIN
    assert out["currentSubject"] == "root@example.com"
    expected = sorted(
        name for name, allowed in rbac._PERMISSIONS.items()
        if rbac.ROLE_PLATFORM_ADMIN in allowed
    )
    assert out["currentPermissions"] == expected
    # app.admin is administrator/platform_admin only; a developer must not be
    # told it holds it, and vice versa.
    assert "app.admin" in expected


def test_access_denies_a_role_without_admin_permission():
    from fastapi import HTTPException

    from server.routes.dev_admin import admin_access

    class _Viewer:
        subject = "v"
        role = rbac.ROLE_CUSTOMER_VIEWER
        tenant_id = "00000000-0000-4000-8000-000000000001"
        kind = "dev"

    with pytest.raises(HTTPException) as exc:
        __import__("asyncio").run(admin_access(_Viewer()))
    assert exc.value.status_code == 403


def test_analytics_returns_only_real_columns():
    """Every documented key must be present, or a panel renders blank."""
    from server.routes.dev_admin import admin_analytics
    import server.routes.dev_admin as mod
    from server.db.connection import init_db, get_session_factory

    class _Session:
        subject = "dev"
        role = rbac.ROLE_DEVELOPER
        tenant_id = "00000000-0000-4000-8000-000000000001"
        kind = "dev"

    if not __import__("asyncio").run(init_db()) or get_session_factory() is None:
        pytest.skip("DATABASE_URL not configured")

    out = __import__("asyncio").run(mod.admin_analytics(days=30, session=_Session()))

    assert {
        "windowDays",
        "since",
        "totals",
        "callsByDay",
        "callsByStatus",
        "callsByDirection",
        "topUpsByDay",
        "topTenantsByCalls",
    } <= set(out)
    assert {
        "calls",
        "seconds",
        "missedCalls",
        "tenants",
        "tenantsActive",
        "users",
        "activeNumbers",
        "failedPurchases",
        "walletBalanceCents",
    } == set(out["totals"])
    for d in out["callsByDay"]:
        assert {"date", "calls", "seconds"} == set(d)
    for t in out["topTenantsByCalls"]:
        assert {"name", "calls"} == set(t)


def test_analytics_window_is_honoured():
    from server.db.connection import init_db, get_session_factory
    from server.routes.dev_admin import admin_analytics

    class _Session:
        subject = "dev"
        role = rbac.ROLE_DEVELOPER
        tenant_id = "00000000-0000-4000-8000-000000000001"
        kind = "dev"

    if not __import__("asyncio").run(init_db()) or get_session_factory() is None:
        pytest.skip("DATABASE_URL not configured")

    out = __import__("asyncio").run(admin_analytics(days=7, session=_Session()))
    assert out["windowDays"] == 7


def test_analytics_window_is_bounded():
    """An unbounded window would scan the whole call table on every page load."""
    from server.db.connection import init_db, get_session_factory
    from server.routes.dev_admin import admin_analytics

    class _Session:
        subject = "dev"
        role = rbac.ROLE_DEVELOPER
        tenant_id = "00000000-0000-4000-8000-000000000001"
        kind = "dev"

    if not __import__("asyncio").run(init_db()) or get_session_factory() is None:
        pytest.skip("DATABASE_URL not configured")

    # FastAPI validates Query bounds at the edge, so an over-long window is a 422
    # before the handler runs. Prove the bound exists rather than trusting it.
    import asyncio

    from fastapi import Query

    ann = admin_analytics.__annotations__.get("days")
    assert "Query" in str(ann) or hasattr(ann, "__metadata__")
    meta = getattr(ann, "__metadata__", ())
    bounds = [m for m in meta if isinstance(m, type(Query(default=30, ge=1, le=365)))]
    assert bounds, "days must stay bounded"
    assert bounds[0].ge == 1 and bounds[0].le == 365

    # And a valid window must work.
    out = asyncio.run(admin_analytics(days=365, session=_Session()))
    assert out["windowDays"] == 365
