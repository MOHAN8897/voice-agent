"""Platform number inventory: only numbers the carrier really owns may be listed or sold."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from server.services.saas import number_inventory


def _pn(e164, *, carrier=None, telnyx=None):
    return SimpleNamespace(
        id=uuid.uuid4(), e164=e164, carrier_number_id=carrier, telnyx_number_id=telnyx,
        status="available", released_at=None, agent_id=None, inbound_enabled=False, outbound_enabled=False,
        created_at=datetime.now(timezone.utc),
    )


def test_has_carrier_id_requires_a_real_carrier_reference():
    assert number_inventory.has_carrier_id(_pn("+917965480745", carrier="18d1"))
    assert number_inventory.has_carrier_id(_pn("+13526146416", telnyx="3041"))
    # Leftovers from tests / failed orders: no carrier ever issued an ID.
    assert not number_inventory.has_carrier_id(_pn("+919898296006"))
    assert not number_inventory.has_carrier_id(_pn("+13525550100", telnyx="carrier_platform"))


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class _Session:
    def __init__(self, rows):
        self.rows = rows
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def execute(self, _stmt):
        return _Rows(self.rows)

    async def commit(self):
        self.commits += 1


def _run_reconcile(monkeypatch, rows, owned, *, apply):
    session = _Session(rows)

    async def inv():
        return uuid.uuid4()

    async def carriers():
        return owned

    monkeypatch.setattr(number_inventory, "ensure_platform_inventory_tenant", inv)
    monkeypatch.setattr(number_inventory, "get_session_factory", lambda: (lambda: session))
    monkeypatch.setattr(number_inventory, "_carrier_owned", carriers)
    return asyncio.run(number_inventory.reconcile_inventory_with_carriers(apply=apply)), session


def test_reconcile_preview_lists_unowned_numbers_without_changing_them(monkeypatch):
    real, fake = _pn("+917965480745", carrier="18d1"), _pn("+919898296006")
    result, session = _run_reconcile(monkeypatch, [real, fake], {"vobiz": {"+917965480745"}, "telnyx": set()}, apply=False)
    assert [s["e164"] for s in result["stale"]] == ["+919898296006"]
    assert result["stale"][0]["hasCarrierId"] is False
    assert fake.released_at is None and session.commits == 0


def test_reconcile_apply_soft_releases_only_unowned_numbers(monkeypatch):
    real, fake = _pn("+917965480745", carrier="18d1"), _pn("+919898296006")
    result, session = _run_reconcile(monkeypatch, [real, fake], {"vobiz": {"+917965480745"}, "telnyx": set()}, apply=True)
    assert fake.status == "released" and fake.released_at is not None
    assert real.status == "available" and real.released_at is None
    assert session.commits == 1 and result["applied"] is True


def test_reconcile_never_touches_a_carrier_it_could_not_reach(monkeypatch):
    vobiz_row, telnyx_row = _pn("+917965480745", carrier="18d1"), _pn("+13526146416", telnyx="3041")
    # Vobiz down: its rows must survive even though they are "not in" an empty answer.
    result, _ = _run_reconcile(monkeypatch, [vobiz_row, telnyx_row], {"vobiz": None, "telnyx": {"+13526146416"}}, apply=True)
    assert result["stale"] == [] and result["skippedProviders"] == ["vobiz"]
    assert vobiz_row.released_at is None


def test_inventory_sale_listing_hides_rows_without_a_carrier_id(monkeypatch):
    rows = [_pn("+917965480745", carrier="18d1"), _pn("+919898296006")]

    async def inv():
        return uuid.uuid4()

    monkeypatch.setattr(number_inventory, "ensure_platform_inventory_tenant", inv)
    monkeypatch.setattr(number_inventory, "get_session_factory", lambda: (lambda: _Session(rows)))
    listed = asyncio.run(number_inventory.list_inventory_for_sale(country="IN"))
    assert [r["e164"] for r in listed] == ["+917965480745"]


class _Admin:
    subject = "platform@example.test"
    tenant_id = "00000000-0000-4000-8000-000000000001"
    kind = "dev"

    from server.auth import rbac as _rbac

    role = _rbac.ROLE_PLATFORM_ADMIN


def test_carrier_purchase_rejects_a_mistyped_confirmation_before_any_db_or_carrier_call(monkeypatch):
    import server.routes.dev_admin as dev_admin
    import server.services.telephony as telephony

    monkeypatch.setattr(telephony, "active_telephony_provider", lambda: "vobiz")
    monkeypatch.setattr(dev_admin, "_require_db", lambda: None)
    monkeypatch.setattr(dev_admin, "get_session_factory", lambda: pytest.fail("DB must not be touched"))
    body = dev_admin.DirectCarrierPurchaseBody(
        e164="+917965482188", confirmE164="+917965482100", provider="vobiz", reason="stock for Gujarat",
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(dev_admin.purchase_platform_carrier_number(body, _Admin()))
    assert exc.value.status_code == 400
    assert exc.value.detail["error"]["code"] == "confirmation_mismatch"


def test_carrier_purchase_without_a_workspace_targets_the_inventory():
    from server.routes.dev_admin import DirectCarrierPurchaseBody

    body = DirectCarrierPurchaseBody(e164="+917965482188", provider="vobiz", reason="stock for Gujarat")
    assert body.tenantId is None


class _FakeVobiz:
    """A parent or child Vobiz account holding a set of numbers."""

    def __init__(self, auth_id, owned):
        self.auth_id = auth_id
        self.owned = owned  # shared dict e164 -> owner auth_id
        self.calls = []

    async def list_account_numbers(self, *, search, limit):
        return [{"e164": e, "account_id": a, "id": f"id-{e}", "status": "active"}
                for e, a in self.owned.items() if e == search and a == self.auth_id]

    async def ensure_default_application(self, *, name, app_id):
        return app_id or "app-1"

    async def assign_number_to_subaccount(self, *, e164, sub_auth_id):
        self.calls.append(("assign", e164, sub_auth_id))
        self.owned[e164] = sub_auth_id

    async def _request(self, method, path, **kw):
        self.calls.append((method, path, kw.get("json")))


def _transfer_env(monkeypatch, owned):
    from server.services.saas import voice_kyc_service as kyc
    import server.services.vobiz_client as vc

    parent, child = _FakeVobiz("PARENT", owned), _FakeVobiz("CHILD", owned)

    async def approved(*_a, **_k):
        return None

    async def child_client(_tid):
        return child

    class _Acct:
        application_id = None

    class _Sess:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def get(self, *_a, **_k):
            return _Acct()

        async def commit(self):
            pass

    monkeypatch.setattr(kyc, "assert_voice_kyc_approved", approved)
    monkeypatch.setattr(kyc, "vobiz_client_for_tenant", child_client)
    monkeypatch.setattr(kyc, "get_session_factory", lambda: (lambda: _Sess()))
    monkeypatch.setattr(vc, "VobizClient", lambda: parent)
    return kyc, parent, child


def test_assigning_a_pool_number_moves_it_to_the_tenant_sub_account(monkeypatch):
    owned = {"+917965480745": "PARENT"}
    kyc, parent, child = _transfer_env(monkeypatch, owned)
    number_id = asyncio.run(kyc.transfer_parent_number_to_tenant(uuid.uuid4(), "+917965480745"))
    assert number_id == "id-+917965480745"
    assert owned["+917965480745"] == "CHILD"
    assert ("assign", "+917965480745", "CHILD") in parent.calls
    # Inbound calls are routed to the tenant's application.
    assert any(c[0] == "POST" and c[2] == {"app_id": "app-1"} for c in child.calls)


def test_transfer_is_a_no_op_when_the_tenant_already_owns_the_number(monkeypatch):
    owned = {"+917965480745": "CHILD"}
    kyc, parent, _ = _transfer_env(monkeypatch, owned)
    assert asyncio.run(kyc.transfer_parent_number_to_tenant(uuid.uuid4(), "+917965480745")) == "id-+917965480745"
    assert parent.calls == []


def test_transfer_refuses_a_number_the_platform_does_not_own(monkeypatch):
    owned = {"+917965480745": "SOMEONE_ELSE"}
    kyc, parent, _ = _transfer_env(monkeypatch, owned)
    with pytest.raises(kyc.VoiceKycError, match="number_not_on_platform_account"):
        asyncio.run(kyc.transfer_parent_number_to_tenant(uuid.uuid4(), "+917965480745"))
    assert parent.calls == []
