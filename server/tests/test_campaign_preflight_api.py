from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi.testclient import TestClient


def test_preflight_uses_published_script_and_hides_platform_sections(monkeypatch):
    from server.app import app
    from server.auth.api_tenant import ApiTenantContext, require_api_tenant
    from server.services.saas.campaign_script import compiled_brain_service

    context = ApiTenantContext(tenant_id=uuid4(), role="customer_admin", subject=str(uuid4()), subscriber=False)
    agent = {"active_compiled_brain_version": "cb_preflight"}
    monkeypatch.setattr("server.services.saas.call_callback_service.resolve_workspace_agent", AsyncMock(return_value=agent))
    monkeypatch.setattr(compiled_brain_service, "get_snapshot", AsyncMock(return_value={"compiled_text":
        "--- PLATFORM CORE ---\nInternal platform rule.\n--- CALLING SCRIPT ---\nHello {{contact.full_name | there}}.\n--- CALL END POLICY ---\nInternal platform policy."}))
    app.dependency_overrides[require_api_tenant] = lambda: context
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/api/campaigns/validate-variables", json={"agentId": str(uuid4()), "contacts": [{"phone": "+12025550101", "full_name": "A. Sai Kumar"}]})
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] and data["scriptVersion"] == "cb_preflight"
        assert data["previews"][0]["renderedText"] == "Hello A. Sai Kumar."
        assert "Internal platform" not in data["previews"][0]["renderedText"]
    finally:
        app.dependency_overrides.pop(require_api_tenant, None)
