"""Auth, tenant isolation, and reviewed-revision publication regressions."""
from __future__ import annotations

import copy
import importlib
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from server.auth.instructions_access import InstructionsAccess, require_instructions_access
from server.auth.session import create_session_token
from server.brain.agent_service import agent_service
from server.brain.business_brain_store import business_brain_store, draft_revision
from server.brain.compiled_brain_artifact import assemble_unified_brain
from server.brain.compiled_brain_service import compiled_brain_service
from server.config.env import get_settings
from server.routes.agents_business_brain import router as brain_router
from server.routes.instructions import router as instructions_router
from server.services.saas.tenant_guard import SubscriberPrincipal
from server.utils.errors import AppError


@pytest.fixture
def api():
    app = FastAPI()
    app.include_router(instructions_router)
    app.include_router(brain_router)
    return app


@pytest.mark.parametrize(("method", "path", "body"), [
    ("GET", "/api/instructions", None),
    ("GET", "/api/instructions/default", None),
    ("GET", "/api/instructions/live-prompt-preview", None),
    ("POST", "/api/instructions", {"agentBrief": "A helpful assistant"}),
    ("DELETE", "/api/instructions", None),
    ("POST", "/api/instructions/extract-spec", {"agentBrief": "A helpful assistant", "language_code": "en-IN"}),
    ("POST", "/api/instructions/compile-from-spec", {"spec": {}}),
])
def test_all_instruction_routes_fail_closed_without_auth(api, method, path, body):
    assert TestClient(api).request(method, path, json=body).status_code == 401


def test_signed_dev_access_keeps_scratch_sessions_and_enforces_csrf(api):
    client = TestClient(api)
    client.cookies.set("dev_session", create_session_token("dev", "test-developer", None, "developer"))
    client.cookies.set("dev_csrf", "test-csrf")
    assert client.get("/api/instructions?sessionId=local-scratch").status_code == 200
    assert client.delete("/api/instructions?sessionId=local-scratch").status_code == 403
    assert client.delete("/api/instructions?sessionId=local-scratch", headers={"X-CSRF-Token": "test-csrf"}).status_code == 200


@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
def test_subscriber_cannot_address_other_tenant_instruction_session(api, monkeypatch, method):
    import server.auth.instructions_access as access_module
    principal = SubscriberPrincipal(uuid.uuid4(), uuid.uuid4(), "customer_admin", "synthetic@example.invalid")
    monkeypatch.setattr(access_module, "require_subscriber_jwt", AsyncMock(return_value=principal))
    denied = AsyncMock(side_effect=HTTPException(status_code=404, detail="Agent not found"))
    monkeypatch.setattr(access_module, "load_agent_for_tenant", denied)
    agent_id = uuid.uuid4()
    response = TestClient(api).request(method, "/api/instructions", params={"sessionId": f"test-studio:{agent_id}"},
        headers={"Authorization": "Bearer synthetic"}, json={"sessionId": f"test-studio:{agent_id}", "agentBrief": "A helpful assistant"} if method == "POST" else None)
    assert response.status_code == 404
    denied.assert_awaited_once_with(str(agent_id), principal.tenant_id)


def test_subscriber_cannot_access_global_legacy_session(api):
    api.dependency_overrides[require_instructions_access] = lambda: InstructionsAccess(uuid.uuid4(), "customer_admin")
    assert TestClient(api).get("/api/instructions?sessionId=default").status_code == 404


def test_app_cookie_cannot_use_scratch_session(api):
    client = TestClient(api)
    client.cookies.set("app_session", create_session_token("app", "synthetic", get_settings().default_tenant_id, "customer_admin"))
    assert client.get("/api/instructions?sessionId=default").status_code == 404


def test_spoofed_dev_cookie_and_bad_bearer_do_not_bypass_auth(api):
    client = TestClient(api)
    client.cookies.set("dev_session", "forged-developer-session")
    assert client.get("/api/instructions?sessionId=default").status_code == 401
    assert client.get("/api/instructions?sessionId=default", headers={"Authorization": "Bearer invalid"}).status_code in (401, 503)


@pytest.mark.asyncio
async def test_stale_draft_cannot_overwrite_newer_content():
    agent = await agent_service.create_agent(name="Revision regression", languages=["en-IN"])
    aid = agent["agent_id"]
    original = await business_brain_store.ensure_default_sections(aid)
    revision = draft_revision(original)
    changed = copy.deepcopy(original)
    changed[0]["raw_text"] = "A new reviewed identity"
    saved = await business_brain_store.save_draft_sections(aid, changed, expected_revision=revision)
    with pytest.raises(AppError, match="another editor") as caught:
        await business_brain_store.save_draft_sections(aid, original, expected_revision=revision)
    assert caught.value.status_code == 409
    assert await business_brain_store.get_sections(aid) == saved


@pytest.mark.asyncio
async def test_revision_includes_disabled_configuration_and_cannot_mutate_store_by_reference():
    aid = str(uuid.uuid4())
    sections = [{"type": "custom", "title": "saas_voice_config", "raw_text": '{"speed":1}', "enabled": False}]
    saved = await business_brain_store.save_draft_sections(aid, sections)
    read = await business_brain_store.get_sections(aid)
    read[0]["raw_text"] = '{"speed":1.2}'
    assert draft_revision(read) != draft_revision(saved)
    assert (await business_brain_store.get_sections(aid))[0]["raw_text"] == '{"speed":1}'


@pytest.mark.asyncio
async def test_edit_during_optimizer_prevents_publication(monkeypatch):
    service_module = importlib.import_module("server.brain.compiled_brain_service")
    from server.brain.business_prompt_optimizer import OptimizerResult
    agent = await agent_service.create_agent(name="Publish race", languages=["en-IN"])
    aid = agent["agent_id"]
    initial = await business_brain_store.ensure_default_sections(aid)
    async def optimize(raw, **kwargs):
        edited = copy.deepcopy(initial)
        edited[0]["raw_text"] = "Concurrent new identity"
        await business_brain_store.save_draft_sections(aid, edited)
        return OptimizerResult(optimized_business_prompt=raw)
    monkeypatch.setattr(service_module, "optimize_business_prompt", optimize)
    with pytest.raises(AppError) as caught:
        await compiled_brain_service.publish_agent_brain(aid, expected_revision=draft_revision(initial))
    assert caught.value.status_code == 409
    assert await business_brain_store.get_versions(aid) == []


@pytest.mark.asyncio
async def test_publish_pins_exact_compiled_artifact_and_business_version():
    agent = await agent_service.create_agent(name="Immutable publication", languages=["en-IN"])
    aid = agent["agent_id"]
    sections = await business_brain_store.ensure_default_sections(aid)
    artifact = assemble_unified_brain(language="en-IN", script="Represent a lunar garden and answer only supplied facts.")
    first = await compiled_brain_service.publish_agent_brain(aid, sections=sections, optimized_prompt=artifact, optimizer_report={"saas_build": True})
    assert first["compiled_text"] == artifact
    changed = copy.deepcopy(sections)
    changed[0]["raw_text"] = "New identity for second approved artifact"
    second_artifact = assemble_unified_brain(language="en-IN", script="Represent an orbital bakery.")
    await compiled_brain_service.publish_agent_brain(aid, sections=changed, optimized_prompt=second_artifact)
    pinned = await compiled_brain_service.compile_for_agent(aid, business_version_id=first["business_version"])
    assert pinned["business_version"] == first["business_version"]
    assert pinned["compiled_text"] == artifact
    assert (await business_brain_store.get_latest_published(aid))["optimized_prompt"] == second_artifact


@pytest.mark.asyncio
async def test_http_draft_and_publish_require_reviewed_revision(api):
    agent = await agent_service.create_agent(name="HTTP revision", languages=["en-IN"])
    aid = agent["agent_id"]
    client = TestClient(api)
    client.cookies.set("dev_session", create_session_token("dev", "synthetic", None, "developer"))
    client.cookies.set("dev_csrf", "synthetic-csrf")
    client.headers["X-CSRF-Token"] = "synthetic-csrf"
    base = f"/api/agents/{aid}/business-brain"
    draft = client.get(base).json()["draft"]
    assert client.put(base + "/draft", json={"sections": draft["sections"]}).status_code == 422
    assert client.post(base + "/publish").status_code == 422
    changed = copy.deepcopy(draft["sections"])
    changed[0]["raw_text"] = "Updated identity for the lunar garden"
    saved = client.put(base + "/draft", json={"sections": changed, "expected_revision": draft["revision"]})
    assert saved.status_code == 200, saved.text
    assert client.post(base + "/publish", json={"expected_revision": draft["revision"]}).status_code == 409
    assert client.post(base + "/publish", json={"expected_revision": saved.json()["revision"]}).status_code == 200
