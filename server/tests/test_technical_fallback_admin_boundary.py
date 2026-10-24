"""Outage configuration belongs to platform operators, including its API data."""
from __future__ import annotations

import io
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.auth import rbac
from server.auth.dependencies import require_dev_session
from server.auth.subscriber_dependencies import require_subscriber_jwt, require_subscriber_jwt_if_enabled
from server.brain.agent_service import AgentService
from server.routes import agents, app_agents, dev_admin
from server.services.saas.tenant_guard import SubscriberPrincipal


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(agents.router)
    app.include_router(app_agents.router)
    app.include_router(dev_admin.router)
    app.dependency_overrides[require_subscriber_jwt_if_enabled] = lambda: None
    with TestClient(app, base_url="http://localhost") as test_client:
        yield test_client


def test_agent_serialization_keeps_recording_disclosure_and_excludes_outage_policy():
    row = SimpleNamespace(
        agent_id=uuid.uuid4(), tenant_id=uuid.uuid4(), name="Assistant", status="active",
        active_compiled_brain_version=None, default_tier="medium", languages=["te-IN"],
        memory_schema="compact_v1", environment="development", voice_settings={},
        recording_disclosure_enabled=True, recording_disclosure_text="This call is recorded.",
        technical_fallback_promise_callback=False, technical_fallback_text="Internal note",
    )
    payload = AgentService._row_to_dict(row)
    assert payload["recording_disclosure_enabled"] is True
    assert payload["recording_disclosure_text"] == "This call is recorded."
    assert not any("technical_fallback" in key for key in payload)
    assert not any("technical_fallback" in key for key in AgentService._default_agent_dict("agent-a"))
    assert row.technical_fallback_text == "Internal note"


def test_replayed_employee_build_does_not_expose_cached_outage_settings(client, monkeypatch):
    principal = SubscriberPrincipal(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(),
                                    role=rbac.ROLE_CUSTOMER_ADMIN, email="tenant@example.test")
    client.app.dependency_overrides[require_subscriber_jwt] = lambda: principal
    monkeypatch.setattr(app_agents.platform_languages, "is_enabled", lambda language: True)
    cached = {"ok": True, "agent": {"agent_id": "agent-a", "technical_fallback_text": "Old internal note",
                                   "technical_fallback_promise_callback": False}}
    monkeypatch.setattr(app_agents.agent_service, "claim_build_request", AsyncMock(return_value={
        "created": False, "state": "completed", "agent": {"agent_id": "agent-a"}, "response": cached,
    }))
    response = client.post("/api/app/agents/build-employee", json={
        "brief": "Handle customer questions", "language": "en-IN", "requestId": str(uuid.uuid4()),
    })
    assert response.status_code == 200
    assert response.json()["agent"] == {"agent_id": "agent-a"}
    assert cached["agent"]["technical_fallback_text"] == "Old internal note"


@pytest.mark.parametrize("method,path,body", [
    ("GET", "/api/agents", None),
    ("GET", "/api/agents/agent-a", None),
    ("POST", "/api/agents", {"name": "Assistant"}),
    ("PATCH", "/api/agents/agent-a", {"name": "Updated"}),
    ("PUT", "/api/agents/agent-a", {"name": "Updated"}),
])
def test_subscriber_agent_responses_exclude_platform_outage_settings(client, monkeypatch, method, path, body):
    internal = {
        "agent_id": "agent-a", "name": "Assistant",
        "recording_disclosure_enabled": True,
        "technical_fallback_promise_callback": False,
        "technical_fallback_text": "Internal note",
        "technicalFallbackPromiseCallback": False,
        "technicalFallbackText": "Internal note",
    }
    for name in ("get_agent", "create_agent", "patch_agent"):
        monkeypatch.setattr(agents.agent_service, name, AsyncMock(return_value=internal))
    monkeypatch.setattr(agents.agent_service, "list_agents", AsyncMock(return_value=[internal]))
    response = client.request(method, path, json=body)
    assert response.status_code == 200
    payload = response.json()
    public = payload["agents"][0] if "agents" in payload else payload["agent"]
    assert public == {"agent_id": "agent-a", "name": "Assistant", "recording_disclosure_enabled": True}
    # Response redaction must not mutate shared runtime configuration.
    assert internal["technical_fallback_text"] == "Internal note"


def test_subscriber_patch_cannot_change_platform_outage_settings(client, monkeypatch):
    patch = AsyncMock(return_value={"agent_id": "agent-a"})
    monkeypatch.setattr(agents.agent_service, "patch_agent", patch)
    response = client.patch("/api/agents/agent-a", json={
        "technicalFallbackPromiseCallback": False,
        "technicalFallbackText": "Changed by subscriber",
        "technical_fallback_text": "Changed by subscriber",
    })
    assert response.status_code == 200
    assert patch.await_args.args[1] == {}


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/agents/agent-a/fallback-clips"),
    ("PUT", "/api/agents/agent-a/fallback-clips/en-IN/call_back"),
    ("DELETE", "/api/agents/agent-a/fallback-clips/en-IN/call_back"),
])
def test_subscriber_has_no_clip_management_routes(client, method, path):
    assert client.request(method, path).status_code == 404


@pytest.mark.parametrize("method,suffix", [
    ("GET", ""), ("PATCH", ""),
    ("PUT", "/clips/en-IN/call_back"),
    ("DELETE", "/clips/en-IN/call_back"),
    ("GET", "/clips/en-IN/call_back/audio"),
])
def test_admin_outage_routes_require_dev_session(client, method, suffix):
    response = client.request(method, f"/api/dev/admin/agents/{uuid.uuid4()}/technical-fallback{suffix}",
                              files={"file": ("clip.wav", io.BytesIO(b"not-a-wave"), "audio/wav")} if method == "PUT" else None,
                              json={} if method == "PATCH" else None)
    assert response.status_code == 401


@pytest.mark.parametrize("role", [rbac.ROLE_CUSTOMER_ADMIN, rbac.ROLE_CUSTOMER_VIEWER])
def test_customer_roles_cannot_load_admin_outage_settings(client, monkeypatch, role):
    client.app.dependency_overrides[require_dev_session] = lambda: SimpleNamespace(role=role)
    storage = AsyncMock()
    monkeypatch.setattr(dev_admin, "_admin_agent_tenant", storage)
    response = client.get(f"/api/dev/admin/agents/{uuid.uuid4()}/technical-fallback")
    assert response.status_code == 403
    storage.assert_not_awaited()


def test_platform_admin_reads_persisted_agent_policy_and_owned_clips(client, monkeypatch):
    from server.services import fallback_clip_store

    agent_id, tenant_id = uuid.uuid4(), uuid.uuid4()
    agent = SimpleNamespace(agent_id=agent_id, tenant_id=tenant_id, name="Assistant", languages=["te-IN"],
                            technical_fallback_promise_callback=False, technical_fallback_text="Operator note")
    client.app.dependency_overrides[require_dev_session] = lambda: SimpleNamespace(role=rbac.ROLE_PLATFORM_ADMIN)
    monkeypatch.setattr(dev_admin, "_admin_agent_tenant", AsyncMock(return_value=(agent, tenant_id)))
    clips = AsyncMock(return_value=[{"language": "te-IN", "variant": "call_back", "durationMs": 2000}])
    monkeypatch.setattr(fallback_clip_store, "list_clips", clips)
    response = client.get(f"/api/dev/admin/agents/{agent_id}/technical-fallback")
    assert response.status_code == 200
    payload = response.json()
    assert payload["promiseCallback"] is False
    assert payload["transcript"] == "Operator note"
    assert payload["languages"][0] == "te-IN"
    assert set(payload["defaults"]["te-IN"]) == {"callback_promise", "call_back", "disclosure"}
    assert payload["clips"][0]["language"] == "te-IN"
    clips.assert_awaited_once_with(tenant_id=str(tenant_id), agent_id=str(agent_id))


def test_admin_preview_rejects_invalid_language_without_database_query(client, monkeypatch):
    agent_id, tenant_id = uuid.uuid4(), uuid.uuid4()
    client.app.dependency_overrides[require_dev_session] = lambda: SimpleNamespace(role=rbac.ROLE_PLATFORM_ADMIN)
    monkeypatch.setattr(dev_admin, "_admin_agent_tenant", AsyncMock(return_value=(SimpleNamespace(agent_id=agent_id), tenant_id)))
    response = client.get(f"/api/dev/admin/agents/{agent_id}/technical-fallback/clips/not_a_locale/call_back/audio")
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "invalid_fallback_clip"


def test_platform_admin_saves_policy_on_locked_agent_row_and_records_audit(client, monkeypatch):
    agent_id, tenant_id = uuid.uuid4(), uuid.uuid4()
    agent = SimpleNamespace(agent_id=agent_id, tenant_id=tenant_id,
                            technical_fallback_promise_callback=True, technical_fallback_text="Previous")
    db = SimpleNamespace(get=AsyncMock(return_value=agent), commit=AsyncMock(), refresh=AsyncMock())

    class SessionContext:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *args):
            return False

    client.app.dependency_overrides[require_dev_session] = lambda: SimpleNamespace(
        role=rbac.ROLE_PLATFORM_ADMIN, subject="operator")
    monkeypatch.setattr(dev_admin, "_require_db", lambda: None)
    monkeypatch.setattr(dev_admin, "get_session_factory", lambda: SessionContext)
    audit = AsyncMock()
    monkeypatch.setattr(dev_admin, "record_admin_action", audit)
    response = client.patch(f"/api/dev/admin/agents/{agent_id}/technical-fallback", json={
        "promiseCallback": False, "transcript": "  Recorded apology  ",
    })
    assert response.status_code == 200
    assert response.json()["promiseCallback"] is False
    assert agent.technical_fallback_text == "Recorded apology"
    db.get.assert_awaited_once_with(dev_admin.Agent, agent_id, with_for_update=True)
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(agent)
    assert audit.await_args.kwargs["action"] == "agent.technical_fallback.update"
    assert audit.await_args.kwargs["tenant_id"] == tenant_id
