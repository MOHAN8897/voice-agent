"""Accounts admin page: server-side lists and bulk actions (fixtures only, no real data)."""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from server.auth import rbac
from server.auth.session import SessionData
from server.routes import dev_admin_accounts as acc

MOD = "server.routes.dev_admin_accounts"
LEGACY = "server.routes.dev_admin"


def _session(role=rbac.ROLE_PLATFORM_ADMIN, subject="admin@dialtact.ai"):
    return SessionData(
        kind="dev",
        subject=subject,
        tenant_id="00000000-0000-4000-8000-000000000001",
        role=role,
        issued_at=int(time.time()),
    )


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


@pytest.fixture(autouse=True)
def _clear_idempotency():
    acc._IDEMPOTENCY.clear()
    yield
    acc._IDEMPOTENCY.clear()


@pytest.fixture
def db_ready():
    with patch(f"{MOD}.get_session_factory", return_value=MagicMock()):
        yield


def _tenant(status="active", plan="starter", name="Acme", deleted=False):
    return SimpleNamespace(
        tenant_id=uuid.uuid4(),
        name=name,
        status=status,
        plan=plan,
        deleted_at=datetime.now(timezone.utc) if deleted else None,
    )


# --------------------------------------------------------------------------- query builders


def test_workspace_query_filters_compile_to_sql():
    rows, count, ids = acc.build_workspaces_query(
        q="acme",
        status="suspended",
        plan="growth",
        kyc="approved",
        has_numbers="yes",
        dial_code="91",
        sort="balance",
        direction="asc",
    )
    sql = _sql(rows)
    assert "tenants.status = 'suspended'" in sql
    assert "tenants.plan = 'growth'" in sql
    assert "vobiz_subaccounts.kyc_status = 'verified'" in sql
    assert "LIKE '+91%%'" in sql or "LIKE '+91%'" in sql
    assert "tenants.deleted_at IS NULL" in sql
    assert "Platform inventory" in sql  # inventory hidden by default
    assert "ASC NULLS LAST" in sql
    assert "count(tenants.tenant_id)" in _sql(count)
    assert "tenants.tenant_id" in _sql(ids)


def test_workspace_query_deleted_status_includes_deleted_rows():
    rows, _c, _i = acc.build_workspaces_query(status="deleted")
    sql = _sql(rows)
    assert "tenants.deleted_at IS NOT NULL" in sql
    assert "tenants.deleted_at IS NULL" not in sql


def test_query_builders_reject_unknown_sort_and_filters():
    with pytest.raises(HTTPException):
        acc.build_workspaces_query(sort="password_hash")
    with pytest.raises(HTTPException):
        acc.build_workspaces_query(kyc="maybe")
    with pytest.raises(HTTPException):
        acc.build_users_query(last_active="yesterday")
    with pytest.raises(HTTPException):
        acc.build_numbers_query(location="moon")
    with pytest.raises(HTTPException):
        acc._dial_code("123456")


def test_users_query_last_active_and_role_scope():
    tid = uuid.uuid4()
    now = datetime(2026, 10, 30, tzinfo=timezone.utc)
    rows, _c, _i = acc.build_users_query(tenant_id=tid, role="customer_admin", last_active="inactive30", now=now)
    sql = _sql(rows)
    assert "tenant_memberships.role = 'customer_admin'" in sql
    assert str(tid) in sql
    assert "last_logins.last_login IS NULL OR last_logins.last_login <" in sql


def test_numbers_query_filters():
    rows, _c, _i = acc.build_numbers_query(
        location="assigned", ownership="customer", pinned="no", provider="telnyx", purchase_status="manual"
    )
    sql = _sql(rows)
    assert "phone_numbers.released_at IS NULL" in sql
    assert "phone_numbers.vobiz_account_scope = 'tenant'" in sql
    assert "phone_numbers.agent_id IS NULL" in sql
    assert "phone_numbers.purchase_id IS NULL" in sql


def test_kyc_state_mapping():
    assert acc.kyc_state(None, None, None) == "not_started"
    assert acc.kyc_state("verified", False, True) == "approved"
    assert acc.kyc_state("verified", True, True) == "in_review"
    assert acc.kyc_state("link_ready", True, False) == "in_review"
    assert acc.kyc_state("failed", True, False) == "declined"


def test_number_provider_attribution():
    assert acc.number_provider(SimpleNamespace(telnyx_number_id="abc", carrier_number_id=None, e164="+15550001")) == "telnyx"
    assert acc.number_provider(SimpleNamespace(telnyx_number_id="carrier_platform", carrier_number_id=None, e164="+15550001")) == "vobiz"
    assert acc.number_provider(SimpleNamespace(telnyx_number_id="abc", carrier_number_id=None, e164="+91800")) == "vobiz"


# --------------------------------------------------------------------------- permissions


@pytest.mark.asyncio
async def test_customer_role_cannot_use_accounts_endpoints(db_ready):
    viewer = _session(role=rbac.ROLE_CUSTOMER_ADMIN)
    body = acc.BulkBody(action="activate", ids=[str(uuid.uuid4())], reason="routine cleanup")
    for fn in (acc.bulk_workspaces, acc.bulk_users, acc.bulk_numbers):
        with pytest.raises(HTTPException) as exc:
            await fn(body=body, session=viewer)
        assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        await acc.accounts_summary(session=viewer)
    assert exc.value.status_code == 403


# --------------------------------------------------------------------------- workspaces bulk


@pytest.mark.asyncio
async def test_workspace_bulk_requires_reason_and_typed_confirmation(db_ready):
    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    with pytest.raises(HTTPException) as exc:
        await acc.bulk_workspaces(body=acc.BulkBody(action="suspend", ids=ids, reason="short", confirm="SUSPEND 2"), session=_session())
    assert "reason" in str(exc.value.detail)
    with pytest.raises(HTTPException) as exc:
        await acc.bulk_workspaces(body=acc.BulkBody(action="delete", ids=ids, reason="customer churned", confirm="DELETE"), session=_session())
    assert "DELETE 2" in str(exc.value.detail)
    assert acc.confirm_phrase("remove_from_workspace", 3) == "REMOVE FROM WORKSPACE 3"


@pytest.mark.asyncio
async def test_workspace_bulk_suspend_skips_reports_and_delegates(db_ready):
    active = _tenant("active")
    already = _tenant("suspended")
    inventory = _tenant("active", plan="platform", name="Platform inventory")
    missing = uuid.uuid4()
    tenants = {t.tenant_id: t for t in (active, already, inventory)}
    ids = [str(active.tenant_id), str(already.tenant_id), str(inventory.tenant_id), str(missing)]
    patch_tenant = AsyncMock(return_value={"ok": True})
    with patch(f"{MOD}._load_tenants", AsyncMock(return_value=tenants)), \
         patch(f"{LEGACY}.patch_tenant", patch_tenant), \
         patch(f"{MOD}.record_admin_action", AsyncMock()) as audit:
        res = await acc.bulk_workspaces(
            body=acc.BulkBody(action="suspend", ids=ids, reason="fraud review hold", confirm="suspend 4", releaseNumbers=False),
            session=_session(),
        )
    assert res["processed"] == [str(active.tenant_id)]
    assert res["skipped"] == [{"id": str(already.tenant_id), "reason": "already suspended"}]
    assert {f["id"] for f in res["failed"]} == {str(inventory.tenant_id), str(missing)}
    patch_tenant.assert_awaited_once()
    sent = patch_tenant.await_args.kwargs["body"]
    assert sent.status == "suspended" and sent.note == "fraud review hold" and sent.releaseNumbers is False
    audit.assert_awaited_once()
    assert audit.await_args.kwargs["action"] == "tenant.bulk.suspend"


@pytest.mark.asyncio
async def test_workspace_bulk_delete_uses_existing_soft_delete_and_is_idempotent(db_ready):
    live = _tenant("active")
    gone = _tenant("deleted", deleted=True)
    tenants = {live.tenant_id: live, gone.tenant_id: gone}
    delete_tenant = AsyncMock(return_value={"ok": True, "releasedNumbers": []})
    body = acc.BulkBody(
        action="delete",
        ids=[str(live.tenant_id), str(gone.tenant_id)],
        reason="duplicate signup workspaces",
        confirm="DELETE 2",
        releaseNumbers=True,
        idempotencyKey="key-1",
    )
    with patch(f"{MOD}._load_tenants", AsyncMock(return_value=tenants)), \
         patch(f"{LEGACY}.delete_tenant", delete_tenant), \
         patch(f"{MOD}.record_admin_action", AsyncMock()):
        first = await acc.bulk_workspaces(body=body, session=_session())
        second = await acc.bulk_workspaces(body=body, session=_session())
    assert first["processed"] == [str(live.tenant_id)]
    assert first["skipped"][0]["reason"] == "already deleted"
    kwargs = delete_tenant.await_args.kwargs
    assert kwargs["hard"] is False and kwargs["release_numbers"] is True and kwargs["note"] == "duplicate signup workspaces"
    assert delete_tenant.await_count == 1  # replayed request did not run again
    assert second["replayed"] is True


@pytest.mark.asyncio
async def test_workspace_bulk_item_failure_does_not_stop_batch(db_ready):
    a, b = _tenant("suspended"), _tenant("past_due")
    calls = AsyncMock(side_effect=[HTTPException(status_code=400, detail="boom"), {"ok": True}])
    with patch(f"{MOD}._load_tenants", AsyncMock(return_value={a.tenant_id: a, b.tenant_id: b})), \
         patch(f"{LEGACY}.patch_tenant", calls), \
         patch(f"{MOD}.record_admin_action", AsyncMock()):
        res = await acc.bulk_workspaces(
            body=acc.BulkBody(action="activate", ids=[str(a.tenant_id), str(b.tenant_id)], reason="payment received"),
            session=_session(),
        )
    assert res["failed"] == [{"id": str(a.tenant_id), "error": "boom"}]
    assert res["processed"] == [str(b.tenant_id)]
    assert res["ok"] is False


# --------------------------------------------------------------------------- users bulk


def _user(email="u@example.com", status="active"):
    return SimpleNamespace(user_id=uuid.uuid4(), email=email, status=status, deleted_at=None)


@pytest.mark.asyncio
async def test_user_bulk_set_role_protects_last_admin(db_ready):
    tid = uuid.uuid4()
    admin, viewer = _user("a@x.com"), _user("v@x.com")
    mems = {
        admin.user_id: SimpleNamespace(role="customer_admin"),
        viewer.user_id: SimpleNamespace(role="customer_viewer"),
    }
    tenant = SimpleNamespace(tenant_id=tid, deleted_at=None)
    set_role = AsyncMock(return_value="customer_viewer")
    with patch(f"{MOD}._load_users", AsyncMock(return_value=({admin.user_id: admin, viewer.user_id: viewer}, mems, 1, tenant))), \
         patch(f"{MOD}._set_membership_role", set_role), \
         patch(f"{MOD}.record_admin_action", AsyncMock()):
        res = await acc.bulk_users(
            body=acc.BulkBody(
                action="set_role", ids=[str(admin.user_id), str(viewer.user_id)], reason="team restructure",
                tenantId=str(tid), role="voice_engineer",
            ),
            session=_session(),
        )
    assert res["processed"] == [str(viewer.user_id)]
    assert "last admin" in res["failed"][0]["error"]
    set_role.assert_awaited_once()


@pytest.mark.asyncio
async def test_user_bulk_add_to_workspace_skips_existing_members(db_ready):
    tid = uuid.uuid4()
    member, outsider = _user("m@x.com"), _user("o@x.com")
    mems = {member.user_id: SimpleNamespace(role="customer_viewer")}
    add = AsyncMock(return_value={"ok": True})
    with patch(f"{MOD}._load_users", AsyncMock(return_value=({member.user_id: member, outsider.user_id: outsider}, mems, 1, SimpleNamespace(deleted_at=None)))), \
         patch(f"{LEGACY}.admin_membership", add), \
         patch(f"{MOD}.record_admin_action", AsyncMock()):
        res = await acc.bulk_users(
            body=acc.BulkBody(
                action="add_to_workspace", ids=[str(member.user_id), str(outsider.user_id)], reason="onboarding the team",
                tenantId=str(tid), role="customer_viewer",
            ),
            session=_session(),
        )
    assert res["processed"] == [str(outsider.user_id)]
    assert res["skipped"][0]["reason"] == "already a member"
    assert add.await_args.kwargs["body"].tenantId == str(tid)


@pytest.mark.asyncio
async def test_user_bulk_suspend_refuses_own_account_and_revokes_sessions(db_ready):
    me, other = _user("admin@dialtact.ai"), _user("x@y.com")
    patch_user = AsyncMock(return_value={"ok": True})
    logout_all = AsyncMock()
    with patch(f"{MOD}._load_users", AsyncMock(return_value=({me.user_id: me, other.user_id: other}, {}, 0, None))), \
         patch(f"{LEGACY}.patch_user", patch_user), \
         patch("server.services.saas.auth_service.logout_all", logout_all), \
         patch(f"{MOD}.record_admin_action", AsyncMock()):
        res = await acc.bulk_users(
            body=acc.BulkBody(action="suspend", ids=[str(me.user_id), str(other.user_id)], reason="abuse investigation", confirm="SUSPEND 2"),
            session=_session(),
        )
    assert res["processed"] == [str(other.user_id)]
    assert "own account" in res["failed"][0]["error"]
    logout_all.assert_awaited_once_with(other.user_id)


# --------------------------------------------------------------------------- numbers bulk


def _number(tenant, *, agent_id=None, status="active", scope=None):
    return SimpleNamespace(
        id=uuid.uuid4(), e164="+15550001", tenant_id=tenant.tenant_id, agent_id=agent_id, status=status,
        released_at=None, telnyx_number_id="tx-1", vobiz_account_scope=scope,
    )


@pytest.mark.asyncio
async def test_number_bulk_assign_workspace_routes_inventory_through_allocate(db_ready):
    target = _tenant("active", name="Target")
    inventory = _tenant("active", plan="platform", name="Platform inventory")
    other = _tenant("active", name="Other")
    inv_num = _number(inventory)
    moved = _number(other, agent_id=uuid.uuid4())
    here = _number(target)
    numbers = {n.id: (n, t) for n, t in ((inv_num, inventory), (moved, other), (here, target))}
    allocate, patch_number = AsyncMock(return_value={"ok": True}), AsyncMock(return_value={"ok": True})
    with patch(f"{MOD}._load_tenants", AsyncMock(return_value={target.tenant_id: target})), \
         patch(f"{MOD}._load_numbers", AsyncMock(return_value=numbers)), \
         patch(f"{LEGACY}.allocate_number", allocate), \
         patch(f"{LEGACY}.patch_number", patch_number), \
         patch(f"{MOD}.record_admin_action", AsyncMock()):
        res = await acc.bulk_numbers(
            body=acc.BulkBody(
                action="assign_workspace", ids=[str(inv_num.id), str(moved.id), str(here.id)],
                reason="customer moved to new workspace", tenantId=str(target.tenant_id),
            ),
            session=_session(),
        )
    assert set(res["processed"]) == {str(inv_num.id), str(moved.id)}
    assert res["skipped"][0]["id"] == str(here.id)
    assert allocate.await_args.kwargs["body"].tenantId == str(target.tenant_id)
    sent = patch_number.await_args.kwargs["body"]
    assert sent.tenantId == str(target.tenant_id) and sent.agentId == ""  # agent pin cleared on move


@pytest.mark.asyncio
async def test_number_bulk_assign_workspace_rejects_inactive_target(db_ready):
    target = _tenant("suspended")
    with patch(f"{MOD}._load_tenants", AsyncMock(return_value={target.tenant_id: target})):
        with pytest.raises(HTTPException) as exc:
            await acc.bulk_numbers(
                body=acc.BulkBody(action="assign_workspace", ids=[str(uuid.uuid4())], reason="moving numbers", tenantId=str(target.tenant_id)),
                session=_session(),
            )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_number_bulk_release_requires_confirmation_and_carrier_failures_surface(db_ready):
    ws = _tenant("active")
    inventory = _tenant("active", plan="platform", name="Platform inventory")
    owned = _number(ws, scope="tenant")
    plain = _number(ws)
    parked = _number(inventory, status="available")
    numbers = {n.id: (n, t) for n, t in ((owned, ws), (plain, ws), (parked, inventory))}
    ids = [str(owned.id), str(plain.id), str(parked.id)]
    with pytest.raises(HTTPException):
        await acc.bulk_numbers(body=acc.BulkBody(action="release", ids=ids, reason="workspace closed down"), session=_session())
    release = AsyncMock(side_effect=[HTTPException(status_code=409, detail="cool-off active"), {"ok": True}])
    with patch(f"{MOD}._load_numbers", AsyncMock(return_value=numbers)), \
         patch(f"{LEGACY}.release_number", release), \
         patch(f"{MOD}.record_admin_action", AsyncMock()):
        res = await acc.bulk_numbers(
            body=acc.BulkBody(action="release", ids=ids, reason="workspace closed down", confirm="RELEASE 3"),
            session=_session(),
        )
    assert res["processed"] == [str(plain.id)]
    assert "cool-off" in res["failed"][0]["error"]
    assert res["skipped"][0]["reason"] == "already in inventory"
    assert release.await_args.kwargs["body"].note == "workspace closed down"


@pytest.mark.asyncio
async def test_number_bulk_assign_agent_requires_same_workspace(db_ready):
    ws, other = _tenant("active"), _tenant("active")
    agent = SimpleNamespace(agent_id=uuid.uuid4(), tenant_id=ws.tenant_id)
    mine, theirs = _number(ws), _number(other)
    numbers = {mine.id: (mine, ws), theirs.id: (theirs, other)}
    patch_number = AsyncMock(return_value={"ok": True})
    with patch(f"{MOD}._load_agent", AsyncMock(return_value=agent)), \
         patch(f"{MOD}._load_numbers", AsyncMock(return_value=numbers)), \
         patch(f"{LEGACY}.patch_number", patch_number), \
         patch(f"{MOD}.record_admin_action", AsyncMock()):
        res = await acc.bulk_numbers(
            body=acc.BulkBody(action="assign_agent", ids=[str(mine.id), str(theirs.id)], reason="route sales line", agentId=str(agent.agent_id)),
            session=_session(),
        )
    assert res["processed"] == [str(mine.id)]
    assert "different workspace" in res["failed"][0]["error"]
    assert patch_number.await_args.kwargs["body"].agentId == str(agent.agent_id)


# --------------------------------------------------------------------------- list endpoint shape


class _Factory:
    def __init__(self, db):
        self.db = db

    def __call__(self):
        db = self.db

        class Ctx:
            async def __aenter__(self):
                return db

            async def __aexit__(self, *a):
                return False

        return Ctx()


@pytest.mark.asyncio
async def test_list_workspaces_shapes_rows_and_ids_only():
    t = SimpleNamespace(
        tenant_id=uuid.uuid4(), name="Acme", status="active", plan="growth", billing_source="self_serve",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc), deleted_at=None, scheduled_purge_at=None,
    )
    wallet = SimpleNamespace(balance_cents=0, balance_inr_paise=19128, currency="inr")
    count_res = MagicMock()
    count_res.scalar_one.return_value = 1
    rows_res = MagicMock()
    rows_res.all.return_value = [(t, wallet, "verified", False, True, 2, 3, 1)]
    ids_res = MagicMock()
    ids_res.scalars.return_value.all.return_value = [t.tenant_id]
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[count_res, rows_res, count_res, ids_res])
    common = dict(
        q="", status="", plan="", kyc="", hasNumbers="", dialCode="", createdFrom="", createdTo="",
        includeDeleted=False, includeInventory=False, minBalanceUsd=None, maxBalanceUsd=None,
        sort="created", dir="desc", limit=25, offset=0,
    )
    with patch(f"{MOD}.get_session_factory", return_value=_Factory(db)), \
         patch(f"{MOD}._fx_rate", AsyncMock(return_value=95.64)):
        page = await acc.list_workspaces(**common, idsOnly=False, session=_session())
        ids = await acc.list_workspaces(**common, idsOnly=True, session=_session())
    item = page["items"][0]
    assert page["total"] == 1
    assert item["walletBalanceUsd"] == 2.0
    assert item["kyc"] == "approved"
    assert (item["numberCount"], item["memberCount"], item["agentCount"]) == (2, 3, 1)
    assert ids == {"ids": [str(t.tenant_id)], "total": 1, "truncated": False}
