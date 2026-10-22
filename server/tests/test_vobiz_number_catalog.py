"""Tenant number catalog regressions for live Vobiz inventory isolation."""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from server.routes import app_telephony
from server.services.saas.tenant_guard import SubscriberPrincipal


class _ScalarRows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _ScalarRows(self._rows)


class _Session:
    def __init__(self, rows_by_query):
        self._rows_by_query = rows_by_query
        self._query_index = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def execute(self, _statement):
        rows = self._rows_by_query[self._query_index]
        self._query_index += 1
        return _Result(rows)


class _SessionFactory:
    def __init__(self, rows_by_query):
        self._rows_by_query = rows_by_query

    def __call__(self):
        return _Session(self._rows_by_query)


def _configure_catalog_route(
    monkeypatch,
    *,
    search,
    db_numbers=(),
    reserved_numbers=(),
    db_available=True,
):
    monkeypatch.setattr(app_telephony, "require_subscriber_permission", lambda *_args: None)
    factory = (
        _SessionFactory([list(db_numbers), list(reserved_numbers)])
        if db_available
        else None
    )
    monkeypatch.setattr(app_telephony, "get_session_factory", lambda: factory)
    monkeypatch.setattr(
        "server.services.saas.number_inventory.ensure_platform_inventory_tenant",
        _ensure_inventory_tenant,
    )
    monkeypatch.setattr(
        "server.services.saas.billing_rates.load_current_rates",
        _load_rates,
    )
    monkeypatch.setattr(
        "server.services.saas.platform_admins.is_platform_admin_email",
        lambda _email: False,
    )
    monkeypatch.setattr(
        "server.services.telephony.active_telephony_provider",
        lambda: "vobiz",
    )
    monkeypatch.setattr(
        "server.services.vobiz_client.VobizClient.search_available_numbers",
        search,
    )
    monkeypatch.setattr(
        "server.services.vobiz_client.VobizClient.__init__",
        lambda self: setattr(self, "cfg", {"auth_id": "MA_TEST", "auth_token": "unit-test-token"}),
    )

    async def fail_if_local_pool_is_used(**_kwargs):
        raise AssertionError("Vobiz tenant inventory must not use the local platform pool")

    monkeypatch.setattr(
        "server.services.saas.number_inventory.list_inventory_for_sale",
        fail_if_local_pool_is_used,
    )


async def _ensure_inventory_tenant():
    return uuid.uuid4()


async def _load_rates():
    return {"did_monthly_usd_cents": 400, "did_monthly_inr_paise": 40000}


@pytest.mark.asyncio
async def test_tenant_catalog_only_returns_live_unassigned_unowned_numbers(monkeypatch):
    async def provider_search(_client, *, country, limit):
        assert (country, limit) == ("IN", 100)
        return [
            {"e164": "+919876543210", "status": "active", "country": "IN", "auth_id": None},
            {"e164": "+919876543211", "status": "active", "country": "IN", "auth_id": None},
            {"e164": "+919876543212", "status": "active", "country": "IN", "auth_id": None, "is_trial_number": True},
            {"e164": "+919876543213", "status": "active", "country": "IN", "auth_id": "SA_OTHER"},
            {"e164": "+919876543214", "status": "inactive", "country": "IN", "auth_id": None},
        ]

    _configure_catalog_route(
        monkeypatch,
        search=provider_search,
        db_numbers=["+919876543210"],
        reserved_numbers=["+919876543211"],
    )
    principal = SubscriberPrincipal(uuid.uuid4(), uuid.uuid4(), "owner", "buyer@example.test")

    result = await app_telephony.search_numbers(country="IN", principal=principal)

    assert [row["e164"] for row in result["numbers"]] == []
    assert result["activeProvider"] == "direct_voice"


@pytest.mark.asyncio
async def test_tenant_catalog_returns_only_provider_inventory_and_masks_provider_fields(monkeypatch):
    async def provider_search(_client, *, country, limit):
        assert (country, limit) == ("IN", 100)
        return [
            {
                "e164": "+919876543210",
                "status": "ACTIVE",
                "country": "IN",
                "auth_id": None,
                "account_id": "MA_PRIVATE",
                "id": "carrier-private-id",
            }
        ]

    _configure_catalog_route(monkeypatch, search=provider_search)
    principal = SubscriberPrincipal(uuid.uuid4(), uuid.uuid4(), "owner", "buyer@example.test")

    result = await app_telephony.search_numbers(country="IN", principal=principal)

    assert len(result["numbers"]) == 1
    row = result["numbers"][0]
    assert row["e164"] == "+919876543210"
    assert row["provider"] == "direct_voice"
    assert not {"auth_id", "account_id", "id"}.intersection(row)


@pytest.mark.asyncio
async def test_tenant_catalog_fails_closed_when_provider_inventory_is_unavailable(monkeypatch):
    async def provider_failure(_client, **_kwargs):
        raise RuntimeError("provider request failed")

    _configure_catalog_route(monkeypatch, search=provider_failure)
    principal = SubscriberPrincipal(uuid.uuid4(), uuid.uuid4(), "owner", "buyer@example.test")

    with pytest.raises(HTTPException) as caught:
        await app_telephony.search_numbers(country="IN", principal=principal)

    assert caught.value.status_code == 502
    assert "temporarily unavailable" in caught.value.detail["error"]["message"]


@pytest.mark.asyncio
async def test_tenant_catalog_fails_closed_when_db_is_unavailable(monkeypatch):
    async def provider_search(_client, **_kwargs):
        return [{"e164": "+919876543210", "status": "active", "auth_id": None}]

    _configure_catalog_route(monkeypatch, search=provider_search, db_available=False)
    principal = SubscriberPrincipal(uuid.uuid4(), uuid.uuid4(), "owner", "buyer@example.test")

    with pytest.raises(HTTPException) as caught:
        await app_telephony.search_numbers(country="IN", principal=principal)

    assert caught.value.status_code == 503
