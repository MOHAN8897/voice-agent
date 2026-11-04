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


def test_tenant_numbers_are_bought_on_the_main_account_after_kyc(monkeypatch):
    from server.services.saas import voice_kyc_service as kyc
    import server.services.vobiz_client as vc

    calls = []

    async def approved(tenant_id, *, action):
        calls.append(("kyc", tenant_id, action))

    class _Parent:
        async def provision_ordered_number(self, e164):
            calls.append(("parent_order", e164))
            return {"phone_number_id": "vobiz-id-1"}

    async def no_child(_tid):
        raise AssertionError("the tenant sub-account must not be used to buy numbers")

    monkeypatch.setattr(kyc, "assert_voice_kyc_approved", approved)
    monkeypatch.setattr(kyc, "vobiz_client_for_tenant", no_child)
    monkeypatch.setattr(vc, "VobizClient", lambda: _Parent())
    tid = uuid.uuid4()
    assert asyncio.run(kyc.provision_tenant_number(tid, "+918064262252")) == {"phone_number_id": "vobiz-id-1"}
    # KYC is checked first, then the order goes to the main account.
    assert calls == [("kyc", tid, "activate a phone number"), ("parent_order", "+918064262252")]


def test_tenant_number_purchase_stops_when_kyc_is_not_approved(monkeypatch):
    from server.services.saas import voice_kyc_service as kyc
    import server.services.vobiz_client as vc

    async def refused(_tid, *, action):
        raise HTTPException(status_code=403, detail="voice_kyc_required")

    monkeypatch.setattr(kyc, "assert_voice_kyc_approved", refused)
    monkeypatch.setattr(vc, "VobizClient", lambda: pytest.fail("no order without KYC"))
    with pytest.raises(HTTPException):
        asyncio.run(kyc.provision_tenant_number(uuid.uuid4(), "+918064262252"))


def test_inventory_sale_listing_only_shows_the_active_carrier(monkeypatch):
    rows = [_pn("+917965480745", carrier="18d1"), _pn("+13526146416", telnyx="3041")]

    async def inv():
        return uuid.uuid4()

    monkeypatch.setattr(number_inventory, "ensure_platform_inventory_tenant", inv)
    monkeypatch.setattr(number_inventory, "get_session_factory", lambda: (lambda: _Session(rows)))
    listed = asyncio.run(number_inventory.list_inventory_for_sale(provider="vobiz"))
    assert [r["e164"] for r in listed] == ["+917965480745"]
