"""Tests for platform admin tenant management, phone numbers management, and error shielding."""
from __future__ import annotations

import uuid
import pytest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from server.services.saas.tenant_guard import SubscriberPrincipal
from server.routes.app_admin import (
    TenantStatusBody,
    admin_set_tenant_status,
    admin_delete_tenant,
    admin_search_phone_numbers,
)
from server.services.saas.telephony_orchestrator import _sanitize_tenant_dial_error


@pytest.fixture
def admin_principal():
    return SubscriberPrincipal(
        user_id=uuid.uuid4(),
        tenant_id=uuid.UUID("6d3fba56-7109-4812-8eb5-4a0d11f558c6"),
        email="mohansaiteja.99@gmail.com",
        role="platform_admin",
    )


@pytest.mark.asyncio
async def test_protect_primary_workspace_from_blocking(admin_principal, monkeypatch):
    monkeypatch.setenv("SAAS_PLATFORM_ADMIN_EMAILS", "mohansaiteja.99@gmail.com")
    from server.config.env import get_settings
    get_settings.cache_clear()

    # Mock session returning mohan saiteja's workspace
    mock_tenant = AsyncMock()
    mock_tenant.name = "mohan saiteja's Workspace"
    mock_tenant.tenant_id = admin_principal.tenant_id
    mock_tenant.status = "active"

    mock_session = AsyncMock()
    mock_session.get.return_value = mock_tenant

    class MockSessionFactory:
        def __call__(self):
            class Ctx:
                async def __aenter__(self):
                    return mock_session
                async def __aexit__(self, *args):
                    pass
            return Ctx()

    with patch("server.routes.app_admin.get_session_factory", return_value=MockSessionFactory()):
        with pytest.raises(HTTPException) as exc_info:
            await admin_set_tenant_status(
                tenant_id=str(admin_principal.tenant_id),
                body=TenantStatusBody(status="suspended"),
                principal=admin_principal,
            )
        assert exc_info.value.status_code == 400
        assert "protected and cannot be blocked" in exc_info.value.detail["error"]["message"]


@pytest.mark.asyncio
async def test_protect_primary_workspace_from_deletion(admin_principal, monkeypatch):
    monkeypatch.setenv("SAAS_PLATFORM_ADMIN_EMAILS", "mohansaiteja.99@gmail.com")
    from server.config.env import get_settings
    get_settings.cache_clear()

    mock_tenant = AsyncMock()
    mock_tenant.name = "mohan saiteja's Workspace"
    mock_tenant.tenant_id = admin_principal.tenant_id

    mock_session = AsyncMock()
    mock_session.get.return_value = mock_tenant

    class MockSessionFactory:
        def __call__(self):
            class Ctx:
                async def __aenter__(self):
                    return mock_session
                async def __aexit__(self, *args):
                    pass
            return Ctx()

    with patch("server.routes.app_admin.get_session_factory", return_value=MockSessionFactory()):
        with pytest.raises(HTTPException) as exc_info:
            await admin_delete_tenant(
                tenant_id=str(admin_principal.tenant_id),
                principal=admin_principal,
            )
        assert exc_info.value.status_code == 400
        assert "protected and cannot be deleted" in exc_info.value.detail["error"]["message"]


@pytest.mark.asyncio
async def test_admin_search_vobiz_numbers(admin_principal, monkeypatch):
    monkeypatch.setenv("SAAS_PLATFORM_ADMIN_EMAILS", "mohansaiteja.99@gmail.com")
    from server.config.env import get_settings
    get_settings.cache_clear()

    with patch(
        "server.services.vobiz_client.VobizClient.search_available_numbers",
        new=AsyncMock(
            return_value=[
                {"e164": "+16577963237", "country": "US", "type": "local", "provider": "vobiz"}
            ]
        ),
    ):
        result = await admin_search_phone_numbers(
            provider="vobiz",
            country="US",
            principal=admin_principal,
        )
        assert result["provider"] == "vobiz"
        assert len(result["numbers"]) == 1
        assert result["numbers"][0]["e164"] == "+16577963237"
        assert result["numbers"][0]["provider"] == "vobiz"


def test_sanitize_tenant_dial_error():
    # Carrier balance error
    err1 = _sanitize_tenant_dial_error("Telnyx account prepaid credit depleted: balance=0.0")
    assert "Telephony service is temporarily unavailable" in err1

    # Carrier API exception or JSON with timeout
    err2 = _sanitize_tenant_dial_error("Vobiz API 400: {'code': 'carrier_endpoint_timeout_504'}")
    assert "carrier_endpoint_timeout_504" not in err2
    assert "Telephony connection timed out" in err2

    # Generic technical exception
    err3 = _sanitize_tenant_dial_error("HTTPConnectionPool(host='api.telnyx.com'): Max retries exceeded")
    assert "Unable to connect call" in err3
    assert "HTTPConnectionPool" not in err3
