from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from server.auth import rbac


class _Session:
    subject = "platform@example.test"
    role = rbac.ROLE_PLATFORM_ADMIN
    tenant_id = "00000000-0000-4000-8000-000000000001"
    kind = "dev"


class _Viewer(_Session):
    role = rbac.ROLE_CUSTOMER_VIEWER


def test_support_admin_permission_is_restricted_to_dev_admin_roles():
    allowed = rbac._PERMISSIONS["dev.admin.support"]
    assert allowed == {rbac.ROLE_ADMINISTRATOR, rbac.ROLE_DEVELOPER, rbac.ROLE_PLATFORM_ADMIN}
    assert rbac.role_has_permission(rbac.ROLE_PLATFORM_ADMIN, "dev.admin.support")
    assert not rbac.role_has_permission(rbac.ROLE_CUSTOMER_ADMIN, "dev.admin.support")
    assert not rbac.role_has_permission(rbac.ROLE_CUSTOMER_VIEWER, "dev.admin.support")


def test_support_and_carrier_admin_routes_deny_tenant_roles_before_service_calls():
    from server.routes.dev_admin import (
        DirectCarrierPurchaseBody,
        list_platform_support_inquiries,
        platform_support_config,
        purchase_platform_carrier_number,
        search_platform_carrier_numbers,
    )

    for operation in (
        lambda: platform_support_config(session=_Viewer()),
        lambda: list_platform_support_inquiries(session=_Viewer()),
        lambda: search_platform_carrier_numbers(session=_Viewer()),
        lambda: purchase_platform_carrier_number(
            DirectCarrierPurchaseBody(
                e164="+15551234567",
                provider="vobiz",
                tenantId="00000000-0000-4000-8000-000000000001",
                reason="approved admin order",
            ),
            _Viewer(),
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(operation())
        assert exc.value.status_code == 403


def test_carrier_search_and_purchase_reject_a_non_active_provider(monkeypatch):
    import server.routes.dev_admin as dev_admin
    import server.services.telephony as telephony

    monkeypatch.setattr(telephony, "active_telephony_provider", lambda: "vobiz")
    monkeypatch.setattr(dev_admin, "_require_db", lambda: pytest.fail("DB must not be touched"))
    body = dev_admin.DirectCarrierPurchaseBody(
        e164="+15551234567",
        provider="telnyx",
        tenantId="00000000-0000-4000-8000-000000000001",
        reason="approved admin order",
    )

    for operation in (
        lambda: dev_admin.search_platform_carrier_numbers(provider="telnyx", session=_Session()),
        lambda: dev_admin.purchase_platform_carrier_number(body, _Session()),
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(operation())
        assert exc.value.status_code == 409
        assert exc.value.detail["error"]["code"] == "inactive_provider"


def test_support_config_update_audit_does_not_store_smtp_password(monkeypatch):
    import server.routes.dev_admin as dev_admin
    import server.services.saas.customer_support_service as support_service

    audit_events: list[dict] = []

    async def fake_update(updates):
        assert updates["smtpPassword"] == "not-a-real-secret"
        return {"smtpHasPassword": True}

    async def fake_audit(**event):
        audit_events.append(event)

    monkeypatch.setattr(support_service, "update_support_config", fake_update)
    monkeypatch.setattr(dev_admin, "record_admin_action", fake_audit)
    body = dev_admin.PlatformSupportConfigBody(smtpPassword="not-a-real-secret")

    response = asyncio.run(dev_admin.update_platform_support_config(body, _Session()))

    assert response == {"ok": True, "config": {"smtpHasPassword": True}}
    assert audit_events[0]["payload"] == {"fields": ["smtpPassword"]}
    assert "not-a-real-secret" not in repr(audit_events)


def test_support_and_carrier_inputs_have_server_side_bounds():
    from server.routes.dev_admin import (
        DirectCarrierPurchaseBody,
        PlatformSmtpTestBody,
        PlatformSupportInquiryPatchBody,
    )

    with pytest.raises(ValidationError):
        PlatformSmtpTestBody(smtpHost="smtp.example.test", smtpPort=70000)
    with pytest.raises(ValidationError):
        PlatformSupportInquiryPatchBody(status="delete_everything")
    with pytest.raises(ValidationError):
        DirectCarrierPurchaseBody(
            e164="+15551234567",
            provider="vobiz",
            tenantId="00000000-0000-4000-8000-000000000001",
            reason="x",
        )


def test_carrier_purchase_returns_client_error_for_invalid_e164(monkeypatch):
    import server.routes.dev_admin as dev_admin
    import server.services.telephony as telephony

    monkeypatch.setattr(telephony, "active_telephony_provider", lambda: "vobiz")
    monkeypatch.setattr(dev_admin, "_require_db", lambda: None)
    body = dev_admin.DirectCarrierPurchaseBody(
        e164="not-a-phone-number",
        provider="vobiz",
        tenantId="00000000-0000-4000-8000-000000000001",
        reason="approved admin order",
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(dev_admin.purchase_platform_carrier_number(body, _Session()))

    assert exc.value.status_code == 400
    assert exc.value.detail == "invalid_e164"
