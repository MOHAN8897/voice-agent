"""Creation must publish one generated artifact and keep its explicit settings."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.agent.brain_prompt_composer import PromptSectionTooLong
from server.agent.instruction_store import InstructionStore
from server.brain.agent_script_compiler import AgentScriptResult
from server.brain.brief_contract import BriefValidationError, brief_issue
from server.routes import app_agents
from server.services.saas import employee_brain_build


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


@pytest.mark.asyncio
async def test_employee_compiler_does_not_repeat_identical_failed_strategy(monkeypatch):
    compiler = AsyncMock(side_effect=ValueError("bad brief"))
    monkeypatch.setattr(employee_brain_build, "compile_agent_from_brief", compiler)
    with pytest.raises(ValueError, match="bad brief"):
        await employee_brain_build.compile_brief_for_employee(brief="Name Meera", language="en-IN", generation_config={"agentRole": "support"})
    compiler.assert_awaited_once()
    assert compiler.await_args.kwargs["generation_config"] == {"agentRole": "support"}


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
