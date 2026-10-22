"""Session tenant selection — a session must never be issued against a dead workspace.

Regression cover for the console-wide "Some console data could not be loaded from
the API / Not found" banner: `refresh` used to take an arbitrary membership
(`limit(1)` with no ORDER BY) and issue a token for whichever tenant came back,
while the request guard rejected soft-deleted tenants with 404. A user holding
both a live workspace and a soft-deleted one therefore got a token that failed every
single request — yet /auth/me still answered 200, so the console looked signed in
with an empty workspace and no way to say why.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from server.db.models.entities import Tenant
from server.db.models.saas_models import TenantMembership
from server.services.saas.tenant_guard import (
    assert_session_tenant,
    resolve_usable_tenant,
    tenant_is_usable,
)


def _tenant(status: str = "active", deleted: bool = False) -> Tenant:
    return Tenant(
        tenant_id=uuid.uuid4(),
        name="ws",
        status=status,
        deleted_at=datetime.now(timezone.utc) if deleted else None,
    )


def _membership(tenant: Tenant, user_id: uuid.UUID, created_at: datetime) -> TenantMembership:
    return TenantMembership(
        user_id=user_id,
        tenant_id=tenant.tenant_id,
        role="customer_admin",
        created_at=created_at,
    )


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """Stands in for AsyncSession: resolve_usable_tenant only needs execute().all()."""

    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        return _FakeResult(self._rows)


def test_tenant_is_usable_rejects_every_dead_shape():
    assert tenant_is_usable(_tenant("active")) is True
    assert tenant_is_usable(None) is False
    # dev_admin.delete_tenant sets status='cancelled' AND stamps deleted_at.
    assert tenant_is_usable(_tenant("cancelled")) is False
    assert tenant_is_usable(_tenant("active", deleted=True)) is False
    for status in ("suspended", "deleted", "pending_deletion"):
        assert tenant_is_usable(_tenant(status)) is False


def test_resolve_skips_soft_deleted_tenant():
    """The bug: the deleted tenant was selected and every request 404'd on it."""
    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    dead = _tenant("cancelled", deleted=True)
    live = _tenant("active")
    # Dead tenant is returned first — which is exactly what Postgres handed back for
    # this account, so ordering alone cannot save it; only the lifecycle filter can.
    rows = [
        (_membership(dead, user_id, now), dead),
        (_membership(live, user_id, now - timedelta(days=30)), live),
    ]
    picked = asyncio.run(resolve_usable_tenant(_FakeSession(rows), user_id))
    assert picked is not None
    assert picked[1].tenant_id == live.tenant_id


def test_resolve_is_stable_regardless_of_row_order():
    """Same memberships, different DB order → same tenant. No arbitrary picks."""
    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    dead = _tenant("cancelled", deleted=True)
    live = _tenant("active")
    rows = [
        (_membership(dead, user_id, now), dead),
        (_membership(live, user_id, now - timedelta(days=30)), live),
    ]
    picks = {
        asyncio.run(resolve_usable_tenant(_FakeSession(order), user_id))[1].tenant_id
        for order in (rows, list(reversed(rows)))
    }
    assert picks == {live.tenant_id}


def test_resolve_returns_none_when_every_tenant_is_closed():
    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    rows = [
        (_membership(t, user_id, now), t)
        for t in (_tenant("cancelled", deleted=True), _tenant("suspended"))
    ]
    assert asyncio.run(resolve_usable_tenant(_FakeSession(rows), user_id)) is None


class _GetSession(_FakeSession):
    """Also serves session.get(Tenant, ...), which assert_session_tenant uses."""

    def __init__(self, rows, tenants):
        super().__init__(rows)
        self._tenants = tenants

    async def get(self, _model, tenant_id):
        return self._tenants.get(tenant_id)


def _dead_tenant_session(user_id, *, surviving_workspace: bool):
    now = datetime.now(timezone.utc)
    dead = _tenant("cancelled", deleted=True)
    rows = [(_membership(dead, user_id, now), dead)]
    if surviving_workspace:
        rows.append((_membership(_tenant("active"), user_id, now), _tenant("active")))
    return _GetSession(rows, {dead.tenant_id: dead})


def test_stale_session_recovers_onto_the_surviving_workspace():
    """
    A token minted before its workspace was deleted, where the user still has a live
    one, must answer 401 — not 404. 404 left the console showing every resource as
    "Not found" behind a Retry button that could not help, because the client only
    re-establishes a session on 401.
    """
    user_id = uuid.uuid4()
    session = _dead_tenant_session(user_id, surviving_workspace=True)
    dead_tenant_id = next(iter(session._tenants))

    async def run():
        with pytest.raises(HTTPException) as exc:
            await assert_session_tenant(session, user_id, dead_tenant_id)
        return exc.value

    err = asyncio.run(run())
    assert err.status_code == 401
    assert "workspace" in err.detail["error"]["message"].lower()


def test_deleted_workspace_with_no_survivor_stays_404():
    """Nothing to fall back to, so the tenant must still not be confirmed to exist."""
    user_id = uuid.uuid4()
    dead = _dead_tenant_session(user_id, surviving_workspace=False)
    dead_tenant_id = next(iter(dead._tenants))

    async def run():
        with pytest.raises(HTTPException) as exc:
            await assert_session_tenant(dead, user_id, dead_tenant_id)
        return exc.value

    err = asyncio.run(run())
    assert err.status_code == 404