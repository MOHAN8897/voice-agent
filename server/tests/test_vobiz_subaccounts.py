"""Tenant credential isolation and provider request-shape regressions."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from server.services.saas import voice_kyc_service
from server.services.vobiz_client import VobizApiError, VobizClient


def test_subaccount_token_encryption_is_bound_to_tenant(monkeypatch):
    tenant_id = UUID("b76a5ce7-b412-44c2-a59d-cad174d7c12d")
    other_tenant_id = UUID("bc66b0f2-5b4f-4de7-b253-97b0ebfb8369")
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(
        voice_kyc_service,
        "get_settings",
        lambda: SimpleNamespace(vobiz_subaccount_encryption_key=key),
    )

    encrypted = voice_kyc_service.encrypt_subaccount_token(tenant_id, "sensitive-child-token")

    assert encrypted != "sensitive-child-token"
    assert "sensitive-child-token" not in encrypted
    assert voice_kyc_service.decrypt_subaccount_token(tenant_id, encrypted) == "sensitive-child-token"
    with pytest.raises(voice_kyc_service.VoiceKycError, match="voice_credentials_tenant_mismatch"):
        voice_kyc_service.decrypt_subaccount_token(other_tenant_id, encrypted)


def test_subaccount_token_encryption_fails_closed_without_key(monkeypatch):
    monkeypatch.setattr(
        voice_kyc_service,
        "get_settings",
        lambda: SimpleNamespace(vobiz_subaccount_encryption_key=""),
    )
    with pytest.raises(voice_kyc_service.VoiceKycError, match="voice_kyc_encryption_not_configured"):
        voice_kyc_service.encrypt_subaccount_token(UUID(int=1), "sensitive-child-token")


@pytest.mark.asyncio
async def test_vobiz_subaccount_requests_use_documented_paths_and_no_retries(monkeypatch):
    client = VobizClient(cfg={"auth_id": "parent-id", "auth_token": "parent-secret"})
    request = AsyncMock(return_value={})
    monkeypatch.setattr(client, "_request", request)

    await client.create_customer_subaccount(
        name="Example LLP",
        email="owner@example.test",
        business_type="llp",
        description="Tenant voice account",
    )
    await client.create_customer_kyc_session(
        sub_auth_id="SA_child-id",
        redirect_url="https://console.example.test/phone-numbers",
    )
    await client.get_customer_kyc_status("SA_child-id")
    await client.assign_number_to_subaccount(
        e164="+14155550100",
        sub_auth_id="SA_child-id",
    )

    assert request.await_args_list[0].args == ("POST", "/accounts/parent-id/sub-accounts/")
    assert request.await_args_list[0].kwargs["json"]["kyc_mode"] == "customer_use"
    assert request.await_args_list[0].kwargs["retry"] is False
    assert request.await_args_list[1].args == ("POST", "/sub-accounts/SA_child-id/kyc-sessions")
    assert request.await_args_list[1].kwargs["retry"] is False
    assert request.await_args_list[2].args == ("GET", "/sub-accounts/SA_child-id/kyc/status")
    assert request.await_args_list[3].args == (
        "POST",
        "/account/parent-id/numbers/%2B14155550100/assign-subaccount",
    )
    assert request.await_args_list[3].kwargs["json"] == {"sub_account_id": "SA_child-id"}
    assert request.await_args_list[3].kwargs["retry"] is False


@pytest.mark.asyncio
async def test_vobiz_number_purchase_post_is_not_retried(monkeypatch):
    client = VobizClient(cfg={"auth_id": "parent-id", "auth_token": "parent-secret"})
    request = AsyncMock(side_effect=[
        {"items": [], "total": 0},
        {
            "number": {
                "e164": "+14155550100",
                "account_id": "parent-id",
                "id": "number-id",
                "status": "active",
            }
        },
    ])
    monkeypatch.setattr(client, "_request", request)

    result = await client.place_number_order("+14155550100")

    assert result["id"] == "number-id"
    assert request.await_args_list[1].kwargs["retry"] is False


@pytest.mark.asyncio
async def test_voice_carrier_gate_fails_closed_until_provider_unblocks_calls(monkeypatch):
    tenant_id = UUID("b76a5ce7-b412-44c2-a59d-cad174d7c12d")
    monkeypatch.setattr(
        voice_kyc_service,
        "refresh_kyc_status",
        AsyncMock(return_value={"approved": False, "status": "pending"}),
    )
    with pytest.raises(HTTPException) as error:
        await voice_kyc_service.assert_voice_kyc_approved(tenant_id, action="buy a phone number")
    assert getattr(error.value, "status_code", None) == 403
    assert error.value.detail["error"]["code"] == "voice_kyc_required"

    monkeypatch.setattr(
        voice_kyc_service,
        "refresh_kyc_status",
        AsyncMock(return_value={"approved": True, "status": "verified"}),
    )
    await voice_kyc_service.assert_voice_kyc_approved(tenant_id, action="buy a phone number")


async def test_child_call_does_not_switch_webhook_environment_on_configuration_error(monkeypatch):
    client = VobizClient(cfg={"auth_id": "SA_test", "auth_token": "test-only", "disable_app_id": "true"})
    request = AsyncMock(side_effect=VobizApiError("not a valid URL", status=400))
    monkeypatch.setattr(client, "_request", request)
    with pytest.raises(VobizApiError):
        await client.create_outbound_call(to="+14155550100", from_="+14155550101", answer_url="https://api.dialtact.com/api/vobiz/answer?token=test-only")
    request.assert_awaited_once()
