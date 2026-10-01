"""Refresh-token rotation: replay policy for the parallel-request race.

Refresh tokens are single-use. The console syncs a workspace as several parallel
requests and they do not all observe a rotated cookie at the same instant, so the
same token gets legitimately presented twice within milliseconds. `refresh` used to
reject any second presentation, which logged the user out mid-sync and surfaced as a
single resource failing with "Your session expired" while its siblings succeeded
(this account had accumulated 157 refresh tokens).

Policy under test:
  - first presentation            -> rotate, revoke the presented one
  - replay inside the grace window -> the race: re-issue in the same family
  - replay after the window       -> real reuse: burn the whole family, reject
"""
from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from server.db.models.entities import Tenant
from server.db.models.saas_models import RefreshToken, User
from server.services.saas import auth_service


def _utcnow():
    return datetime.now(timezone.utc)


class _FakeResult:
    def __init__(self, *, one=None, rows=None, scalar=None):
        self._one = one
        self._rows = rows or []
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._one

    def all(self):
        return self._rows

    def scalar(self):
        return self._scalar


class _FakeSession:
    """Records statements well enough for refresh()'s three query shapes."""

    def __init__(self, token_row, user, membership_tenant):
        self.token_row = token_row
        self.user = user
        self.membership_tenant = membership_tenant
        self.added = []
        self.commits = 0
        self.family_revocations = []

    async def execute(self, stmt):
        text = str(stmt)
        if "UPDATE refresh_tokens" in text:
            self.family_revocations.append(text)
            return _FakeResult(scalar=0)
        if "FROM refresh_tokens" in text and "revoked_at IS NULL" not in text:
            # The lookup by hash.
            return _FakeResult(one=self.token_row)
        if "FROM tenant_memberships" in text:
            return _FakeResult(rows=[(self._membership(), self.membership_tenant)])
        return _FakeResult()

    def _membership(self):
        from server.db.models.saas_models import TenantMembership

        return TenantMembership(
            user_id=self.user.user_id,
            tenant_id=self.membership_tenant.tenant_id,
            role="customer_admin",
            created_at=_utcnow(),
        )

    async def get(self, _model, _pk):
        return self.user

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


@pytest.fixture
def harness(monkeypatch):
    def build(*, revoked_seconds_ago=None, expires_in_days=7, tenant_status="active"):
        user = User(
            user_id=uuid.uuid4(),
            email="someone@example.com",
            status="active",
            email_verified_at=_utcnow(),
            password_hash="x",
        )
        tenant = Tenant(tenant_id=uuid.uuid4(), name="ws", status=tenant_status)
        row = RefreshToken(
            id=uuid.uuid4(),
            user_id=user.user_id,
            token_hash=hashlib.sha256(b"tok").hexdigest(),
            family_id=uuid.uuid4(),
            expires_at=_utcnow() + timedelta(days=expires_in_days),
            revoked_at=(_utcnow() - timedelta(seconds=revoked_seconds_ago)) if revoked_seconds_ago else None,
            created_at=_utcnow(),
        )
        session = _FakeSession(row, user, tenant)

        async def _no_wallet(*_a, **_k):
            return None

        # get_session_factory() returns a session *maker*; refresh() then calls it
        # and uses the result as an async context manager.
        monkeypatch.setattr(auth_service, "get_session_factory", lambda: (lambda: _AsyncCtx(session)))
        monkeypatch.setattr(auth_service, "_seed_admin_wallet", _no_wallet)
        return session, row, tenant

    return build


class _AsyncCtx:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *_exc):
        return False


def _refresh(token="tok"):
    return asyncio.run(auth_service.refresh(token))


def test_first_presentation_rotates_and_revokes(harness):
    session, row, _tenant = harness()
    result = _refresh()
    assert result["refreshToken"]
    assert row.revoked_at is not None
    assert len(session.added) == 1
    # Rotation continues the same family so reuse detection can see the chain.
    assert session.added[0].family_id == row.family_id


def test_race_replay_inside_grace_window_is_re_issued(harness):
    """The bug: a parallel request presenting the just-consumed token."""
    session, row, _tenant = harness(revoked_seconds_ago=2)
    result = _refresh()
    assert result["refreshToken"]
    assert len(session.family_revocations) == 0
    assert session.added[0].family_id == row.family_id


def test_reuse_after_grace_window_burns_the_family(harness):
    """Too late to be the race, so a leaked token must not keep working."""
    session, _row, _tenant = harness(
        revoked_seconds_ago=auth_service.REFRESH_REUSE_GRACE_SECONDS + 60
    )
    with pytest.raises(ValueError, match="invalid_refresh"):
        _refresh()
    assert len(session.family_revocations) == 1
    assert session.added == []


def test_expired_token_is_rejected(harness):
    harness(expires_in_days=-1)
    with pytest.raises(ValueError, match="invalid_refresh"):
        _refresh()