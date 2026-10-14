"""Tests for dev admin tenants multi-action management, deletion, restore, and bulk operations."""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from server.auth import rbac
from server.auth.session import SessionData
from server.routes.dev_admin import (
    TenantBulkActionBody,
    TenantDeleteBody,
    bulk_tenant_actions,
    delete_tenant,
    restore_tenant,
)


@pytest.fixture
def dev_admin_session():
    return SessionData(
        kind="dev",
        subject="admin@dialtact.ai",
        tenant_id="00000000-0000-4000-8000-000000000001",
        role=rbac.ROLE_PLATFORM_ADMIN,
        issued_at=int(time.time()),
    )


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


@pytest.mark.asyncio
async def test_delete_tenant_with_release_and_revoke(dev_admin_session):
    tid = uuid.uuid4()
    mock_tenant = AsyncMock()
    mock_tenant.tenant_id = tid
    mock_tenant.name = "Test Tenant Deletion"
    mock_tenant.status = "active"
    mock_tenant.deleted_at = None

    mock_db = AsyncMock()
    mock_db.get.return_value = mock_tenant

    # Active numbers query result
    mock_num_scalar = MagicMock()
    mock_num_scalar.all.return_value = []
    mock_num_result = MagicMock()
    mock_num_result.scalars.return_value = mock_num_scalar
    mock_num_result.scalar_one.return_value = 0

    # Members query result
    mock_mem_scalar = MagicMock()
    mock_mem_scalar.all.return_value = [uuid.uuid4()]
    mock_mem_result = MagicMock()
    mock_mem_result.scalars.return_value = mock_mem_scalar

    # Update rowcount
    mock_update_result = MagicMock()
    mock_update_result.rowcount = 1

    mock_db.execute = AsyncMock(side_effect=[
        mock_num_result,  # release numbers check
        mock_num_result,  # active numbers count check
        mock_mem_result,  # member ids for revoke
        mock_update_result,  # token revoke update
    ])

    factory = MockSessionFactory(mock_db)

    with patch("server.routes.dev_admin.get_session_factory", return_value=factory), \
         patch("server.routes.dev_admin.record_admin_action", new=AsyncMock()) as mock_audit:
        body = TenantDeleteBody(
            force=False,
            releaseNumbers=True,
            revokeSessions=True,
            note="Decommissioning tenant workspace",
        )
        res = await delete_tenant(
            tenant_id=str(tid),
            body=body,
            session=dev_admin_session,
        )

        assert res["ok"] is True
        assert mock_tenant.status == "deleted"
        assert mock_tenant.deleted_at is not None
        mock_db.commit.assert_awaited()
        mock_audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_restore_tenant(dev_admin_session):
    tid = uuid.uuid4()
    mock_tenant = AsyncMock()
    mock_tenant.tenant_id = tid
    mock_tenant.status = "cancelled"
    mock_tenant.deleted_at = datetime.now(timezone.utc)

    mock_db = AsyncMock()
    mock_db.get.return_value = mock_tenant

    factory = MockSessionFactory(mock_db)

    with patch("server.routes.dev_admin.get_session_factory", return_value=factory), \
         patch("server.routes.dev_admin.record_admin_action", new=AsyncMock()) as mock_audit:
        res = await restore_tenant(
            tenant_id=str(tid),
            note="Restoring by customer request",
            session=dev_admin_session,
        )

        assert res["ok"] is True
        assert mock_tenant.status == "active"
        assert mock_tenant.deleted_at is None
        mock_db.commit.assert_awaited()
        mock_audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_bulk_tenant_actions_change_plan(dev_admin_session):
    tid1 = uuid.uuid4()
    tid2 = uuid.uuid4()

    mock_t1 = AsyncMock()
    mock_t1.tenant_id = tid1
    mock_t1.plan = "starter"

    mock_t2 = AsyncMock()
    mock_t2.tenant_id = tid2
    mock_t2.plan = "starter"

    mock_db = AsyncMock()
    mock_db.get.side_effect = [mock_t1, mock_t2]

    factory = MockSessionFactory(mock_db)

    with patch("server.routes.dev_admin.get_session_factory", return_value=factory), \
         patch("server.routes.dev_admin.record_admin_action", new=AsyncMock()):
        body = TenantBulkActionBody(
            action="change_plan",
            tenantIds=[str(tid1), str(tid2)],
            plan="enterprise",
            note="Bulk upgrading high volume tenants",
        )
        res = await bulk_tenant_actions(body=body, session=dev_admin_session)

        assert res["ok"] is True
        assert len(res["processed"]) == 2
        assert mock_t1.plan == "enterprise"
        assert mock_t2.plan == "enterprise"


@pytest.mark.asyncio
async def test_bulk_tenant_actions_invalid_action(dev_admin_session):
    body = TenantBulkActionBody(
        action="invalid_action",
        tenantIds=[str(uuid.uuid4())],
        note="Test invalid",
    )
    with patch("server.routes.dev_admin.get_session_factory", return_value=MockSessionFactory(AsyncMock())):
        with pytest.raises(HTTPException) as exc:
            await bulk_tenant_actions(body=body, session=dev_admin_session)
        assert exc.value.status_code == 400
        assert "Invalid bulk action" in exc.value.detail
