"""Tests for enhanced user search, filter, and pagination in dev_admin."""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.auth import rbac
from server.auth.session import SessionData
from server.routes import dev_admin


class MockSessionFactory:
    def __init__(self, session_mock):
        self.session_mock = session_mock

    def __call__(self):
        ctx = self

        class Ctx:
            async def __aenter__(self):
                return ctx.session_mock

            async def __aexit__(self, *args):
                pass

        return Ctx()


@pytest.fixture
def dev_admin_session():
    return SessionData(
        kind="dev",
        subject="admin@dialtact.ai",
        tenant_id="00000000-0000-4000-8000-000000000001",
        role=rbac.ROLE_PLATFORM_ADMIN,
        issued_at=int(time.time()),
    )


def _make_user(user_id=None, email="user@example.com", full_name="User Example", status="active"):
    u = MagicMock()
    u.user_id = user_id or uuid.uuid4()
    u.email = email
    u.full_name = full_name
    u.status = status
    u.created_at = datetime.now(timezone.utc)
    return u


def _make_membership(user_id, tenant_id, role="customer_admin"):
    m = MagicMock()
    m.user_id = user_id
    m.tenant_id = tenant_id
    m.role = role
    return m


@pytest.mark.asyncio
async def test_list_users_all(dev_admin_session):
    """Calling list_users returns users with total count, pagination, and workspace details."""
    u1 = _make_user(email="alice@acme.com", full_name="Alice Smith", status="active")
    u2 = _make_user(email="bob@acme.com", full_name="Bob Jones", status="suspended")

    tid = uuid.uuid4()
    m1 = _make_membership(u1.user_id, tid, "customer_admin")
    m2 = _make_membership(u2.user_id, tid, "voice_engineer")

    # 1st execute: count_stmt
    mock_count_res = MagicMock()
    mock_count_res.scalar.return_value = 2

    # 2nd execute: users query
    mock_users_res = MagicMock()
    mock_users_res.scalars.return_value.all.return_value = [u1, u2]

    # 3rd execute: memberships query
    mock_mems_res = MagicMock()
    mock_mems_res.all.return_value = [(m1, "Acme Corp"), (m2, "Acme Corp")]

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[mock_count_res, mock_users_res, mock_mems_res])
    factory = MockSessionFactory(mock_db)

    with patch("server.routes.dev_admin.get_session_factory", return_value=factory):
        res = await dev_admin.list_users(session=dev_admin_session)

        assert "users" in res
        assert "total" in res
        assert res["total"] == 2
        assert len(res["users"]) == 2

        user0 = res["users"][0]
        assert user0["email"] == "alice@acme.com"
        assert user0["role"] == "customer_admin"
        assert user0["tenantName"] == "Acme Corp"
        assert user0["tenantId"] == str(tid)


@pytest.mark.asyncio
async def test_list_users_search_and_status_filter(dev_admin_session):
    """Calling list_users with search query q and status filter."""
    u1 = _make_user(email="alice@acme.com", full_name="Alice Smith", status="active")

    mock_count_res = MagicMock()
    mock_count_res.scalar.return_value = 1

    mock_users_res = MagicMock()
    mock_users_res.scalars.return_value.all.return_value = [u1]

    mock_mems_res = MagicMock()
    mock_mems_res.all.return_value = []

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[mock_count_res, mock_users_res, mock_mems_res])
    factory = MockSessionFactory(mock_db)

    with patch("server.routes.dev_admin.get_session_factory", return_value=factory):
        res = await dev_admin.list_users(q="alice", status="active", session=dev_admin_session)
        assert res["total"] == 1
        assert len(res["users"]) == 1
        assert res["users"][0]["email"] == "alice@acme.com"


@pytest.mark.asyncio
async def test_list_users_invalid_tenant_uuid(dev_admin_session):
    """Calling list_users with an invalid tenant UUID returns empty gracefully."""
    mock_db = AsyncMock()
    factory = MockSessionFactory(mock_db)

    with patch("server.routes.dev_admin.get_session_factory", return_value=factory):
        res = await dev_admin.list_users(tenantId="not-a-valid-uuid", session=dev_admin_session)
        assert res["users"] == []
        assert res["total"] == 0
