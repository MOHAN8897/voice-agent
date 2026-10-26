"""F08 tier/locale readiness and F09 resumable creation regression tests."""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.brain import agent_service as agent_service_module
from server.brain import employee_script_pipeline as pipeline
from server.brain.agent_service import AgentVoiceRevisionConflict
from server.brain.agent_script_compiler import AgentScriptResult
from server.brain.employee_script_pipeline import GenerationStageError
from server.providers.base import LLMConfig
from server.routes import app_agents
from server.services.saas import employee_brain_build, voice_stack_profiles
from server.tests.test_employee_script_pipeline import BRIEF, extraction


MEDIUM_PROFILE = {
    "revision": 91,
    "profile": {"enabled": True, "supportedLanguages": ["en-IN", "te-IN"]},
}


@pytest.fixture
def medium_profile(monkeypatch):
    async def records(_environment, tiers=None):
        return {"medium": MEDIUM_PROFILE} if tiers is None or "medium" in tiers else {}

    monkeypatch.setattr(voice_stack_profiles, "load_profile_records", records)


@pytest.fixture
def creation(monkeypatch):
    principal = SimpleNamespace(tenant_id="workspace-one")
    app = FastAPI()
    app.include_router(app_agents.router)
    app.dependency_overrides[app_agents.require_subscriber_jwt] = lambda: principal
    monkeypatch.setattr(app_agents, "require_subscriber_permission", lambda *_args: None)
    monkeypatch.setattr(app_agents, "subscriber_workspace_tenant_id", lambda _p: "workspace-one")
    monkeypatch.setattr(app_agents.platform_languages, "is_enabled", lambda _lang: True)
    result = AgentScriptResult(agent_script="Approved exact script", agent_name="Meera", platform_call_rules="Only approved facts.")
    artifact = ("Approved exact compiled brain", result, [])
    compile_mock = AsyncMock(return_value=artifact)
    create_mock = AsyncMock(return_value={"agent_id": "new-agent"})
    delete_mock = AsyncMock(return_value={"ok": True})
    publish_mock = AsyncMock(return_value={"script": result.agent_script, "generation": result.to_dict()})
    monkeypatch.setattr(employee_brain_build, "compile_brief_for_employee", compile_mock)
    monkeypatch.setattr(app_agents.agent_service, "create_agent", create_mock)
    monkeypatch.setattr(app_agents.agent_service, "delete_agent", delete_mock)
    monkeypatch.setattr(app_agents, "publish_saas_employee_brain", publish_mock)
    monkeypatch.setattr(agent_service_module, "get_session_factory", lambda: None)
    monkeypatch.setattr(agent_service_module, "_MEM_AGENTS", {})
    monkeypatch.setattr(agent_service_module, "_MEM_BUILD_REQUESTS", {})
    return SimpleNamespace(
        client=TestClient(app), compile=compile_mock, create=create_mock,
        delete=delete_mock, publish=publish_mock, artifact=artifact,
    )


@pytest.mark.asyncio
async def test_unsupported_locale_names_the_supported_choices(medium_profile):
    with pytest.raises(voice_stack_profiles.VoiceProfileError) as failure:
        await voice_stack_profiles.validate_agent_language_for_tier("development", "medium", "hi-IN")

    error = failure.value
    assert error.code == "unsupported_language"
    assert error.status_code == 422
    assert error.details == {"tier": "medium", "supportedLanguages": ["en-IN", "te-IN"]}
    assert "Hindi" in str(error)
    assert "English (India)" in str(error)
    await voice_stack_profiles.validate_agent_language_for_tier("development", "medium", "en-IN")


@pytest.mark.asyncio
async def test_retired_british_english_resolves_to_the_supported_english_pack(medium_profile):
    await voice_stack_profiles.validate_agent_language_for_tier("development", "medium", "en-GB")


def test_creation_rejects_a_locale_the_creation_tier_cannot_serve(creation, medium_profile):
    response = creation.client.post(
        "/api/app/agents/build-employee",
        json={"brief": "Meera answers printer questions.", "language": "hi-IN"},
    )
    assert response.status_code == 422
    error = response.json()["detail"]["error"]
    assert error["code"] == "unsupported_language"
    assert error["supportedLanguages"] == ["en-IN", "te-IN"]
    assert "Hindi" in error["message"]
    creation.compile.assert_not_awaited()
    creation.create.assert_not_awaited()


def test_creation_resolves_retired_british_english_to_indian_english(creation, medium_profile):
    response = creation.client.post(
        "/api/app/agents/build-employee",
        json={"brief": "Meera answers printer questions.", "language": "en-GB"},
    )
    assert response.status_code == 200
    assert creation.compile.await_args.kwargs["language"] == "en-IN"
    assert creation.create.await_args.kwargs["languages"] == ["en-IN"]


def test_creation_still_accepts_a_locale_the_tier_supports(creation, medium_profile):
    response = creation.client.post(
        "/api/app/agents/build-employee",
        json={"brief": "Meera answers printer questions.", "language": "en-IN"},
    )
    assert response.status_code == 200
    creation.compile.assert_awaited_once()


@pytest.mark.asyncio
async def test_language_endpoint_withholds_locales_the_creation_tier_cannot_serve(monkeypatch):
    monkeypatch.setattr(
        voice_stack_profiles, "profile_language_support",
        AsyncMock(return_value={"tier": "medium", "configured": True, "supportedLanguages": ["en-IN", "te-IN"]}),
    )
    monkeypatch.setattr(app_agents.platform_languages, "language_options", lambda: [
        {"code": "en-IN", "label": "English (India)"},
        {"code": "hi-IN", "label": "Hindi"},
        {"code": "te-IN", "label": "Telugu"},
    ])
    result = await app_agents.available_languages()
    assert [option["code"] for option in result["languages"]] == ["en-IN", "te-IN"]
    assert [option["code"] for option in result["unavailableOnTier"]] == ["hi-IN"]
    assert result["default"] == "en-IN"
    assert result["tier"] == "medium"


@pytest.fixture
def memory_service(monkeypatch):
    monkeypatch.setattr(agent_service_module, "get_session_factory", lambda: None)
    monkeypatch.setattr(agent_service_module, "_MEM_AGENTS", {})
    monkeypatch.setattr(agent_service_module, "_MEM_BUILD_REQUESTS", {})
    return agent_service_module.AgentService()


@pytest.mark.asyncio
async def test_saving_an_unsupported_locale_on_an_agent_is_rejected(memory_service, medium_profile):
    agent = await memory_service.create_agent(name="Meera", languages=["en-IN"])
    with pytest.raises(AgentVoiceRevisionConflict) as failure:
        await memory_service.patch_agent(agent["agent_id"], {"languages": ["hi-IN"]}, tenant_id=agent["tenant_id"])
    assert failure.value.code == "unsupported_language"
    assert failure.value.status_code == 422
    unchanged = await memory_service.get_agent(agent["agent_id"], tenant_id=agent["tenant_id"])
    assert unchanged["languages"] == ["en-IN"]
    updated = await memory_service.patch_agent(agent["agent_id"], {"languages": ["te-IN"]}, tenant_id=agent["tenant_id"])
    assert updated["languages"] == ["te-IN"]


@pytest.mark.asyncio
async def test_saving_a_retired_british_agent_stores_the_supported_english_pack(memory_service, medium_profile):
    agent = await memory_service.create_agent(name="Meera", languages=["en-IN"])
    updated = await memory_service.patch_agent(agent["agent_id"], {"languages": ["en-GB"]}, tenant_id=agent["tenant_id"])
    assert updated["languages"] == ["en-IN"]


@pytest.mark.asyncio
async def test_only_an_explicit_retry_reopens_a_retryable_failed_request(memory_service):
    request_id = str(uuid.uuid4())
    tenant_id = "workspace-one"
    claim = await memory_service.claim_build_request(
        request_id=request_id, fingerprint="same", tenant_id=tenant_id, name="Meera", language="en-IN",
    )
    agent_id = claim["agent"]["agent_id"]
    await memory_service.finish_build_request(
        agent_id, tenant_id=tenant_id,
        error={"code": "generation_temporarily_unavailable", "retryable": True}, status_code=503,
    )
    replay = await memory_service.claim_build_request(
        request_id=request_id, fingerprint="same", tenant_id=tenant_id, name="Meera", language="en-IN",
    )
    assert replay["created"] is False and replay.get("resumed") is not True
    assert replay["state"] == "failed"
    resumed = await memory_service.claim_build_request(
        request_id=request_id, fingerprint="same", tenant_id=tenant_id, name="Meera", language="en-IN",
        retry_failed=True,
    )
    assert resumed["created"] is False and resumed["resumed"] is True
    assert resumed["state"] == "building"
    assert resumed["agent"]["agent_id"] == agent_id
    await memory_service.finish_build_request(
        agent_id, tenant_id=tenant_id,
        error={"code": "generation_failed", "retryable": False}, status_code=502,
    )
    permanent = await memory_service.claim_build_request(
        request_id=request_id, fingerprint="same", tenant_id=tenant_id, name="Meera", language="en-IN",
        retry_failed=True,
    )
    assert permanent["state"] == "failed" and permanent.get("resumed") is not True


def test_transient_creation_failure_resumes_the_same_draft(creation):
    request_id = str(uuid.uuid4())
    creation.compile.side_effect = [
        GenerationStageError("write", transient=True, correlation_id="abc123abc123"),
        creation.artifact,
    ]
    payload = {"brief": "Meera answers clinic questions.", "requestId": request_id}
    first = creation.client.post("/api/app/agents/build-employee", json=payload)
    assert first.status_code == 503
    error = first.json()["detail"]["error"]
    assert error["code"] == "generation_temporarily_unavailable"
    assert error["stage"] == "write"
    assert error["retryable"] is True
    assert error["correlationId"] == "abc123abc123"
    assert error["draftRetained"] is True
    draft_id = error["agentId"]

    retry = creation.client.post("/api/app/agents/build-employee", json={**payload, "retryFailed": True})
    assert retry.status_code == 200
    assert retry.json()["agentId"] == draft_id
    creation.create.assert_not_awaited()
    creation.delete.assert_not_awaited()
    creation.publish.assert_awaited_once()


def test_permanent_creation_failure_is_not_replayed_through_retry(creation):
    request_id = str(uuid.uuid4())
    creation.compile.side_effect = GenerationStageError(
        "extract", transient=False, correlation_id="def456def456", reason="ungrounded",
    )
    payload = {"brief": "Meera answers clinic questions.", "requestId": request_id}
    first = creation.client.post("/api/app/agents/build-employee", json=payload)
    assert first.status_code == 422
    assert first.json()["detail"]["error"]["code"] == "generation_needs_review"
    retry = creation.client.post("/api/app/agents/build-employee", json={**payload, "retryFailed": True})
    assert retry.status_code == 422
    assert retry.json()["detail"]["error"]["code"] == "generation_needs_review"
    creation.compile.assert_awaited_once()


@pytest.mark.asyncio
async def test_transient_provider_throttle_retries_once(monkeypatch):
    from server.brain import generation_runtime

    calls = []

    async def complete(**_kwargs):
        calls.append("extract")
        if len(calls) == 1:
            raise RuntimeError("HTTP 429 private provider detail")
        return extraction()

    monkeypatch.setattr(generation_runtime, "generation_target", lambda: (
        SimpleNamespace(structured_completion=complete), LLMConfig(provider="gemini", model="test-model")))
    monkeypatch.setattr(pipeline.asyncio, "sleep", AsyncMock())
    result = await pipeline.analyze_employee_brief(brief=BRIEF, language="en-IN")
    assert result.agent_name == "Meera"
    assert calls == ["extract", "extract"]


@pytest.mark.asyncio
async def test_permanent_provider_failure_reports_a_safe_stage_and_no_retry(monkeypatch):
    from server.brain import generation_runtime

    provider = AsyncMock(side_effect=RuntimeError("HTTP 403 private provider credential rejected"))
    monkeypatch.setattr(generation_runtime, "generation_target", lambda: (
        SimpleNamespace(structured_completion=provider), LLMConfig(provider="gemini", model="test-model")))
    with pytest.raises(GenerationStageError) as failure:
        await pipeline.analyze_employee_brief(brief=BRIEF, language="en-IN")
    provider.assert_awaited_once()
    public = failure.value.to_public_dict()
    assert public["code"] == "generation_failed"
    assert public["stage"] == "extract"
    assert public["retryable"] is False
    assert failure.value.correlation_id in str(public)
    assert "private provider" not in str(public)
    assert "403" not in public["message"]


@pytest.mark.asyncio
async def test_incomplete_extraction_is_reported_not_retried(monkeypatch):
    from server.brain import generation_runtime

    provider = AsyncMock(return_value={})
    monkeypatch.setattr(generation_runtime, "generation_target", lambda: (
        SimpleNamespace(structured_completion=provider), LLMConfig(provider="gemini", model="test-model")))
    with pytest.raises(GenerationStageError) as failure:
        await pipeline.analyze_employee_brief(brief=BRIEF, language="en-IN")
    provider.assert_awaited_once()
    assert failure.value.to_public_dict()["code"] == "generation_failed"
    assert failure.value.to_public_dict()["retryable"] is False
