from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from server.services.telnyx_provisioning import provision_ordered_number
from server.services.vobiz_client import VobizClient


@pytest.mark.asyncio
async def test_telnyx_provisioning_uses_the_ordered_number_id(monkeypatch):
    phone = "+14155550100"

    class _Client:
        async def place_number_order(self, _phone):
            return {
                "phone_numbers": [
                    {"phone_number": "+14155550101", "id": "other-number-id"},
                    {"phone_number": phone, "id": "requested-number-id"},
                ]
            }

    async def no_op(_client):
        return None

    async def applied(_client, phone_id):
        assert phone_id == "requested-number-id"
        return {"ok": True}

    monkeypatch.setattr("server.services.telnyx_provisioning.ensure_call_control_application", no_op)
    monkeypatch.setattr("server.services.telnyx_provisioning.apply_standard_phone_number_settings", applied)

    result = await provision_ordered_number(_Client(), phone)

    assert result["phone_number_id"] == "requested-number-id"


@pytest.mark.asyncio
async def test_vobiz_provisioning_preserves_returned_number_id_without_logging_provider_details(
    monkeypatch,
    caplog,
):
    client = object.__new__(VobizClient)
    client.cfg = {"app_id": "test-app-id", "auth_id": "test-auth-id"}

    async def ordered(_phone):
        return {"id": "provider-returned-number-id", "status": "active"}

    async def failed_app_link(_method, path, **_kwargs):
        raise RuntimeError(f"link failed for {path} phone=+14155550100 token=test-secret")

    monkeypatch.setattr(client, "place_number_order", ordered)
    monkeypatch.setattr(client, "_request", failed_app_link)

    with caplog.at_level(logging.DEBUG, logger="server.services.vobiz_client"):
        result = await VobizClient.provision_ordered_number(client, "+14155550100")

    assert result["phone_number_id"] == "provider-returned-number-id"
    assert "+14155550100" not in caplog.text
    assert "test-auth-id" not in caplog.text
    assert "test-secret" not in caplog.text


@pytest.mark.asyncio
async def test_vobiz_number_search_and_balance_do_not_log_provider_errors(monkeypatch, caplog):
    client = object.__new__(VobizClient)
    client.cfg = {"auth_id": "test-auth-id"}

    async def failed_request(_method, path, **_kwargs):
        raise RuntimeError(f"failed path={path} phone=+14155550100 token=test-secret")

    monkeypatch.setattr(client, "_request", failed_request)
    monkeypatch.setattr(
        "server.config.env.get_settings",
        lambda: SimpleNamespace(environment="production"),
    )

    with caplog.at_level(logging.DEBUG, logger="server.services.vobiz_client"):
        assert await client.list_account_numbers() == []
        balance = await client.get_balance()

    assert balance["error"] == "RuntimeError"
    assert "+14155550100" not in caplog.text
    assert "test-auth-id" not in caplog.text
    assert "test-secret" not in caplog.text
