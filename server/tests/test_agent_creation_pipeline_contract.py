"""Creation must publish one generated artifact and keep its explicit settings."""
import asyncio
import importlib
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from server.agent.brain_prompt_composer import PromptSectionTooLong
from server.agent.instruction_store import InstructionStore
from server.brain.agent_script_compiler import AgentScriptResult
from server.brain.brief_contract import BriefValidationError, brief_issue
from server.routes import app_agents
from server.services.saas import employee_brain_build
from server.utils.errors import AppError, ErrorCode


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
    return SimpleNamespace(client=TestClient(app), compile=compile_mock, create=create_mock, delete=delete_mock, publish=publish_mock, artifact=artifact)


def test_creation_forwards_all_picker_settings_and_publishes_same_artifact(creation):
    settings = {"employeeName": "Meera", "agentRole": "support", "callDirection": "inbound", "mode": "bulk", "industry": "clinic", "naturalSpokenStyle": True}
    response = creation.client.post("/api/app/agents/build-employee", json={"brief": "Meera answers clinic questions.", "language": "hi-IN", **settings})
    assert response.status_code == 200
    creation.compile.assert_awaited_once_with(brief="Meera answers clinic questions.", language="hi-IN", generation_config=settings)
    assert creation.publish.await_args.kwargs["compiled_artifact"] is creation.artifact
    assert creation.publish.await_args.kwargs["generation_config"] == settings
    creation.delete.assert_not_awaited()


def test_compile_failure_creates_no_agent_and_does_not_repeat(creation):
    creation.compile.side_effect = RuntimeError("private provider credential must never reach UI")
    response = creation.client.post("/api/app/agents/build-employee", json={"brief": "Meera answers clinic questions."})
    assert response.status_code == 502
    assert "private provider" not in response.text
    creation.compile.assert_awaited_once()
    creation.create.assert_not_awaited()


def test_ambiguous_brief_returns_structured_clarification_without_creation(creation):
    issue = brief_issue("identity_conflict", "Choose Meera or Kavya as the agent name.", field="agent_name")
    creation.compile.side_effect = BriefValidationError([issue])
    response = creation.client.post("/api/app/agents/build-employee", json={"brief": "The agent is Meera. The agent is Kavya."})
    assert response.status_code == 422
    assert response.json()["detail"]["error"]["issues"] == [issue]
    creation.create.assert_not_awaited()


def test_publish_failure_cleans_only_new_agent_in_own_workspace(creation):
    creation.publish.side_effect = RuntimeError("publish unavailable")
    response = creation.client.post("/api/app/agents/build-employee", json={"brief": "Meera answers clinic questions."})
    assert response.status_code == 502
    assert response.json()["detail"]["error"]["cleanupFailed"] is False
    creation.delete.assert_awaited_once_with("new-agent", tenant_id="workspace-one")
    creation.compile.assert_awaited_once()


def test_cleanup_failure_reports_recoverable_agent_without_masking_publish_failure(creation):
    creation.publish.side_effect = RuntimeError("publish unavailable")
    creation.delete.side_effect = RuntimeError("cleanup unavailable")
    response = creation.client.post("/api/app/agents/build-employee", json={"brief": "Meera answers clinic questions."})
    error = response.json()["detail"]["error"]
    assert error["code"] == "publish_failed"
    assert error["cleanupFailed"] is True
    assert error["agentId"] == "new-agent"


def test_publication_validation_error_keeps_original_safe_diagnostic(creation):
    creation.publish.side_effect = AppError(ErrorCode.VALIDATION_ERROR, "Resolve blocking generation issues before publishing", status_code=422)
    response = creation.client.post("/api/app/agents/build-employee", json={"brief": "Meera answers clinic questions."})
    assert response.status_code == 422
    assert response.json()["detail"]["error"]["message"] == "Resolve blocking generation issues before publishing"


@pytest.fixture
def idempotent_creation(creation, monkeypatch):
    service_module = importlib.import_module("server.brain.agent_service")
    monkeypatch.setattr(service_module, "get_session_factory", lambda: None)
    monkeypatch.setattr(service_module, "_MEM_AGENTS", {})
    monkeypatch.setattr(service_module, "_MEM_BUILD_REQUESTS", {})
    return creation


def test_request_id_replays_completed_creation_without_compiling_or_publishing_twice(idempotent_creation):
    payload = {"brief": "Meera answers clinic questions.", "requestId": str(uuid.uuid4())}
    first = idempotent_creation.client.post("/api/app/agents/build-employee", json=payload)
    second = idempotent_creation.client.post("/api/app/agents/build-employee", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["agent"]["tenant_id"] == "workspace-one"
    idempotent_creation.compile.assert_awaited_once()
    idempotent_creation.publish.assert_awaited_once()


def test_request_id_cannot_be_rebound_to_changed_inputs(idempotent_creation):
    payload = {"brief": "Meera answers clinic questions.", "requestId": str(uuid.uuid4())}
    assert idempotent_creation.client.post("/api/app/agents/build-employee", json=payload).status_code == 200
    response = idempotent_creation.client.post("/api/app/agents/build-employee", json={**payload, "agentRole": "support"})
    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == "request_input_changed"
    idempotent_creation.compile.assert_awaited_once()


@pytest.mark.asyncio
async def test_concurrent_request_is_guarded_before_second_compile(idempotent_creation):
    started, release = asyncio.Event(), asyncio.Event()

    async def slow_compile(**_kwargs):
        started.set()
        await release.wait()
        return idempotent_creation.artifact

    idempotent_creation.compile.side_effect = slow_compile
    payload = {"brief": "Meera answers clinic questions.", "requestId": str(uuid.uuid4())}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=idempotent_creation.client.app), base_url="http://test") as client:
        pending = asyncio.create_task(client.post("/api/app/agents/build-employee", json=payload))
        await asyncio.wait_for(started.wait(), timeout=2)
        try:
            duplicate = await client.post("/api/app/agents/build-employee", json=payload)
            assert duplicate.status_code == 409
            assert duplicate.json()["detail"]["error"]["code"] == "creation_in_progress"
        finally:
            release.set()
        assert (await pending).status_code == 200
    idempotent_creation.compile.assert_awaited_once()
    idempotent_creation.publish.assert_awaited_once()


def test_idempotent_publish_failure_keeps_explicit_failed_draft_and_never_deletes(idempotent_creation):
    idempotent_creation.publish.side_effect = RuntimeError("unavailable")
    payload = {"brief": "Meera answers clinic questions.", "requestId": str(uuid.uuid4())}
    first = idempotent_creation.client.post("/api/app/agents/build-employee", json=payload)
    second = idempotent_creation.client.post("/api/app/agents/build-employee", json=payload)
    assert first.status_code == second.status_code == 502
    assert first.json()["detail"]["error"]["draftRetained"] is True
    idempotent_creation.delete.assert_not_awaited()
    idempotent_creation.compile.assert_awaited_once()


@pytest.mark.parametrize("patch_result", [RuntimeError("unavailable"), {}])
def test_claimed_draft_attachment_failure_records_terminal_error_before_retry(idempotent_creation, monkeypatch, patch_result):
    patch = AsyncMock(side_effect=patch_result) if isinstance(patch_result, Exception) else AsyncMock(return_value=patch_result)
    monkeypatch.setattr(app_agents.agent_service, "patch_agent", patch)
    payload = {"brief": "Meera answers clinic questions.", "requestId": str(uuid.uuid4())}
    first = idempotent_creation.client.post("/api/app/agents/build-employee", json=payload)
    retry = idempotent_creation.client.post("/api/app/agents/build-employee", json=payload)
    assert first.status_code == retry.status_code == 502
    assert first.json() == retry.json()
    error = first.json()["detail"]["error"]
    assert error["code"] == "create_failed"
    assert error["draftRetained"] is True
    assert error["agentId"]
    idempotent_creation.compile.assert_awaited_once()
    idempotent_creation.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_build_request_ids_are_scoped_to_tenant(idempotent_creation):
    request_id = str(uuid.uuid4())
    service = app_agents.agent_service
    first = await service.claim_build_request(request_id=request_id, fingerprint="same", tenant_id="workspace-one", name="Meera", language="en-IN")
    second = await service.claim_build_request(request_id=request_id, fingerprint="same", tenant_id="workspace-two", name="Meera", language="en-IN")
    assert first["agent"]["agent_id"] != second["agent"]["agent_id"]
    assert first["agent"]["tenant_id"] == "workspace-one"
    assert second["agent"]["tenant_id"] == "workspace-two"


@pytest.mark.asyncio
async def test_build_request_outcome_survives_new_service_instance_in_database(monkeypatch):
    """Exercise transaction persistence; SQLite does not prove Postgres row locks."""
    from server.db.models.entities import Agent, Base, ConfigVersion, Tenant

    service_module = importlib.import_module("server.brain.agent_service")
    # Keep production PostgreSQL models untouched outside this isolated test.
    for table in (Tenant.__table__, Agent.__table__, ConfigVersion.__table__):
        for column in table.columns:
            if isinstance(column.type, (ARRAY, JSONB)):
                monkeypatch.setattr(column, "type", JSON())
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(service_module, "get_session_factory", lambda: sessions)
    tenant_id, request_id = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        async with engine.begin() as connection:
            await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[Tenant.__table__, Agent.__table__, ConfigVersion.__table__]))
        async with sessions() as session:
            session.add(Tenant(tenant_id=uuid.UUID(tenant_id), name="Isolated test tenant"))
            await session.commit()
        service = service_module.AgentService()
        claim = await service.claim_build_request(request_id=request_id, fingerprint="approved-inputs", tenant_id=tenant_id, name="Meera", language="en-IN")
        assert claim["created"] is True
        agent_id = claim["agent"]["agent_id"]
        completed = await service.finish_build_request(agent_id, tenant_id=tenant_id, response={"ok": True, "agentId": agent_id, "script": "Approved exact script"})
        replay = await service_module.AgentService().claim_build_request(request_id=request_id, fingerprint="approved-inputs", tenant_id=tenant_id, name="Meera", language="en-IN")
        assert replay["created"] is False
        assert replay["state"] == "completed"
        assert replay["response"] == completed
        assert replay["response"]["agent"]["status"] == "active"
        with pytest.raises(service_module.AgentBuildRequestConflict, match="different inputs"):
            await service.claim_build_request(request_id=request_id, fingerprint="changed-inputs", tenant_id=tenant_id, name="Meera", language="en-IN")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_employee_compiler_does_not_repeat_identical_failed_strategy(monkeypatch):
    compiler = AsyncMock(side_effect=ValueError("bad brief"))
    monkeypatch.setattr(employee_brain_build, "compile_agent_from_brief", compiler)
    with pytest.raises(ValueError, match="bad brief"):
        await employee_brain_build.compile_brief_for_employee(brief="Name Meera", language="en-IN", generation_config={"agentRole": "support"})
    compiler.assert_awaited_once()
    assert compiler.await_args.kwargs["generation_config"] == {"agentRole": "support"}


@pytest.mark.asyncio
async def test_employee_generation_settings_reach_real_compiler_spec_and_artifact():
    config = {"employeeName": "Meera", "agentRole": "information", "callDirection": "inbound", "mode": "bulk", "industry": "clinic", "naturalSpokenStyle": True}
    compiled, result, _variables = await employee_brain_build.compile_brief_for_employee(
        brief="Example Clinic answers questions about opening hours. Opening hours are 09:00 to 18:00. Do not offer bookings.",
        language="en-IN", generation_config=config,
    )
    assert result.agent_name == "Meera"
    assert result.detected_role == "information"
    assert result.agent_spec["direction"] == "inbound"
    assert result.generation_config == config
    assert "09:00 to 18:00" in compiled
    assert "Do not offer bookings" in compiled
    assert "natural conversational wording" in result.agent_script


@pytest.mark.asyncio
async def test_employee_input_limit_returns_actionable_diagnostics_without_retry(monkeypatch):
    compiler = AsyncMock(side_effect=PromptSectionTooLong("Agent brief", 1201, 1200, 3000, 6000))
    monkeypatch.setattr(employee_brain_build, "compile_agent_from_brief", compiler)
    with pytest.raises(BriefValidationError) as failure:
        await employee_brain_build.compile_brief_for_employee(brief="Meera answers", language="en-IN")
    assert failure.value.issues[0]["code"] == "input_limit_exceeded"
    compiler.assert_awaited_once()


@pytest.mark.asyncio
async def test_publisher_reuses_exact_compile_and_shared_publication_gate(monkeypatch):
    compiler = AsyncMock(side_effect=AssertionError("must not compile twice"))
    publish = AsyncMock(return_value={"checksum": "approved"})
    monkeypatch.setattr(employee_brain_build, "compile_brief_for_employee", compiler)
    monkeypatch.setattr(employee_brain_build.compiled_brain_service, "publish_agent_brain", publish)
    result = AgentScriptResult(agent_script="Exact reviewed script", agent_name="Meera", platform_call_rules="Approved rules")
    artifact = ("Exact validated brain", result, [])
    response = await employee_brain_build.publish_saas_employee_brain("new-agent", brief="Meera answers clinic questions", language="hi-IN", generation_config={"agentRole": "support"}, compiled_artifact=artifact)
    compiler.assert_not_awaited()
    assert publish.await_args.kwargs["optimized_prompt"] == artifact[0]
    assert publish.await_args.kwargs["optimizer_report"]["agent_script"] == result.agent_script
    config_section = next(row for row in publish.await_args.kwargs["sections"] if row["title"] == "saas_generation_config")
    assert config_section["enabled"] is False
    assert response["compiled"] == artifact[0]


def test_new_brief_clears_old_spec_and_exposes_matching_generation_settings(monkeypatch):
    monkeypatch.setattr(InstructionStore, "_hydrate_from_disk", lambda _self: None)
    monkeypatch.setattr(InstructionStore, "_persist", lambda *_args: None)
    store = InstructionStore()
    common = {"compiled_brain": "Compiled brain", "optimizer_report": {}, "source_checksum": "first", "language": "en-IN"}
    store.save_agent_script("test", "Original brief", "Original script", None, agent_spec={"agent_name": "Old"}, **common)
    config = {"employeeName": "Meera", "agentRole": "support", "callDirection": "inbound"}
    saved = store.save_agent_script("test", "New brief", "New script", None, generation_config=config, **common)
    assert saved["agentSpec"] is None
    assert saved["generationConfig"] == config
    assert store.get_with_meta("test")["generationConfig"] == config
    assert store.get_with_meta("test")["agentSpec"] is None


def test_store_keeps_only_spec_from_current_generation_report(monkeypatch):
    monkeypatch.setattr(InstructionStore, "_hydrate_from_disk", lambda _self: None)
    monkeypatch.setattr(InstructionStore, "_persist", lambda *_args: None)
    store = InstructionStore()
    report = {"agent_spec": {"agent_name": "Meera"}, "generation_config": {"agentRole": "support"}}
    saved = store.save_agent_script("test", "Meera answers", "Script", None, compiled_brain="Compiled", optimizer_report=report, source_checksum="new")
    assert saved["agentSpec"] == report["agent_spec"]
    edited = store.save_agent_script("test", "Meera answers", "Edited script", None, compiled_brain="Compiled edited", optimizer_report={**report, "user_edited": True}, source_checksum="edited")
    assert edited["agentSpec"] is None
