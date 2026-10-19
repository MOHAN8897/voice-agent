import asyncio
import uuid
from types import SimpleNamespace
from contextlib import asynccontextmanager

import pytest
from fastapi import HTTPException

import server.routes.dev_admin as dev_admin
import server.services.telephony as telephony
import server.services.vobiz_client as vobiz_client
from server.auth import rbac


class _AdminSession:
    subject = "platform@example.test"
    role = rbac.ROLE_PLATFORM_ADMIN
    tenant_id = "00000000-0000-4000-8000-000000000001"
    kind = "dev"


class _Result:
    def scalar_one_or_none(self):
        return None


class _Database:
    def __init__(self, events):
        self.events = events
        self.reservation = None

    async def get(self, model, identity, **_kwargs):
        if model is dev_admin.Tenant:
            return SimpleNamespace(name="Platform inventory", plan="platform")
        if model is dev_admin.PhoneNumber and self.reservation and self.reservation.id == identity:
            return self.reservation
        return None

    async def execute(self, _statement):
        return _Result()

    def add(self, row):
        row.id = row.id or uuid.uuid4()
        self.reservation = row

    async def commit(self):
        self.events.append(f"commit:{self.reservation.status}")

    async def rollback(self):
        return None

    async def refresh(self, _row):
        return None


def _configure_purchase(monkeypatch, *, carrier_error=None):
    events = []
    database = _Database(events)

    @asynccontextmanager
    async def session_context():
        yield database

    def session_factory():
        return session_context()

    class _Carrier:
        async def provision_ordered_number(self, _e164):
            events.append("carrier")
            if carrier_error:
                raise carrier_error
            return {"phone_number_id": "provider-test-id"}

    async def record_admin_action(**_event):
        return None

    monkeypatch.setattr(telephony, "active_telephony_provider", lambda: "vobiz")
    monkeypatch.setattr(dev_admin, "_require_db", lambda: None)
    monkeypatch.setattr(dev_admin, "get_session_factory", lambda: session_factory)
    monkeypatch.setattr(dev_admin, "record_admin_action", record_admin_action)
    monkeypatch.setattr(vobiz_client, "VobizClient", _Carrier)
    return events, database


def _body():
    return dev_admin.DirectCarrierPurchaseBody(
        e164="+15551234567",
        provider="vobiz",
        tenantId="00000000-0000-4000-8000-000000000001",
        reason="approved admin test order",
    )


def test_admin_number_purchase_reserves_before_provider_and_completes(monkeypatch):
    events, database = _configure_purchase(monkeypatch)

    result = asyncio.run(dev_admin.purchase_platform_carrier_number(_body(), _AdminSession()))

    assert events == ["commit:provisioning", "carrier", "commit:active"]
    assert result["status"] == "active"
    assert database.reservation.carrier_number_id == "provider-test-id"


def test_uncertain_provider_failure_keeps_number_reserved_for_reconciliation(monkeypatch):
    events, database = _configure_purchase(monkeypatch, carrier_error=TimeoutError())

    with pytest.raises(HTTPException) as exc:
        asyncio.run(dev_admin.purchase_platform_carrier_number(_body(), _AdminSession()))

    assert exc.value.status_code == 502
    assert events == ["commit:provisioning", "carrier", "commit:provisioning_failed"]
    assert database.reservation.status == "provisioning_failed"
    assert database.reservation.released_at is None
