"""Exercise the production pipeline with deterministic provider responses, no API spend."""
import copy
import json
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.brain import employee_script_pipeline as pipeline
from server.brain.brief_contract import BriefValidationError
from server.brain.employee_script_pipeline import GenerationStageError
from server.providers.base import LLMConfig


BRIEF = ("Agent name is Meera. Company is Example Clinic. Answer questions about opening hours. "
         "Opening hours are 09:00 to 18:00. Do not offer bookings.")


def extraction():
    fact = {"text": "Opening hours are 09:00 to 18:00.", "evidence": "Opening hours are 09:00 to 18:00."}
    return {"agent_name": "Meera", "company_name": "Example Clinic",
            "primary_goal": {"text": "Answer questions about opening hours.", "evidence": "Answer questions about opening hours."},
            "facts": [fact], "workflow": [], "permitted_next_steps": [],
            "forbidden_actions": [{"text": "Do not offer bookings.", "evidence": "Do not offer bookings."}],
            "tone": None, "conflicts": [], "missing_critical_info": []}


def draft():
    return {"opening": "Hello, I’m Meera from Example Clinic. How can I help with opening hours?",
            "call_flow": "Answer the caller's opening-hours question from the supplied facts. Ask only one necessary question at a time.",
            "call_to_action": "Provide opening hours; do not offer bookings or collect payment.",
            "objection_handling": "Price, trust, refund or send-details: use known facts only; explain missing details briefly. Respect refusal without another pitch.",
            "unknown_information": "Say you do not have unavailable details. Never claim a tool action succeeded without confirmation. If asked, disclose briefly that you are an AI assistant.",
            "closing": "Confirm the answer, thank the caller when they are done and follow platform call-end policy. Busy or hesitation follows platform policy."}


@pytest.fixture
def pipeline_model(monkeypatch):
    from server.brain import generation_runtime

    state = SimpleNamespace(extracted=extraction(), written=draft(), repaired=draft(), passed=True, calls=[])

    async def complete(**kwargs):
        state.calls.append(kwargs)
        if kwargs["schema_name"] == "employee_brief_extract":
            return copy.deepcopy(state.extracted)
        if kwargs["schema_name"] == "employee_script_write":
            return copy.deepcopy(state.written)
        return {"passed": state.passed, "issues": [], "fixed_script": copy.deepcopy(state.repaired)}

    monkeypatch.setattr(generation_runtime, "generation_target", lambda: (
        SimpleNamespace(structured_completion=complete), LLMConfig(provider="gemini", model="test-model")))
    return state


@pytest.mark.asyncio
async def test_three_stages_only_structured_facts_reach_writer_and_repair_is_published(pipeline_model):
    from server.services.saas.employee_brain_build import compile_brief_for_employee

    pipeline_model.written["opening"] = "Wrong draft opening to be repaired."
    config = {"agentRole": "information", "callDirection": "inbound", "naturalSpokenStyle": True}
    compiled, result, _variables = await compile_brief_for_employee(brief=BRIEF, language="en-IN", generation_config=config)
    assert [call["schema_name"] for call in pipeline_model.calls] == ["employee_brief_extract", "employee_script_write", "employee_script_review"]
    assert [call["config"].temperature for call in pipeline_model.calls] == [0.2, 0.5, 0.2]
    writer_input = json.loads(pipeline_model.calls[1]["input_messages"][1]["content"][0]["text"])
    assert "brief" not in writer_input and "raw_brief" not in writer_input["business"]
    assert "Wrong draft" not in result.agent_script
    assert pipeline_model.repaired["opening"] in result.agent_script
    assert result.agent_spec["direction"] == "inbound"
    assert result.generation_config == config
    assert result.provenance["stages"] == ["extract", "generate", "validate"]
    assert "09:00 to 18:00" in compiled and "Do not offer bookings" in compiled
    assert re.findall(r"--- SPOKEN LANGUAGE \(([^)]+)\) ---", compiled) == ["en-IN"]


@pytest.mark.asyncio
async def test_questions_stop_before_generation_and_include_identity_and_goal(pipeline_model):
    pipeline_model.extracted.update(agent_name=None, primary_goal=None)
    # Keep all fake output source-backed while removing only the missing fields.
    with pytest.raises(BriefValidationError) as failure:
        await pipeline.compile_employee_script(brief=BRIEF, language="en-IN")
    assert {item["field"] for item in failure.value.issues} == {"agent_name", "primary_goal"}
    assert len(pipeline_model.calls) == 1


@pytest.mark.asyncio
async def test_answers_are_extraction_inputs_and_optional_unknowns_are_not_reasked(pipeline_model):
    pipeline_model.extracted["missing_critical_info"] = [{"field": "refund_policy", "question": "What is the refund policy?", "reason": "Callers may ask about refunds.", "required": False}]
    answer = pipeline.ClarificationAnswer(field="refund_policy", question="What is the refund policy?", answer="", unavailable=True)
    result = await pipeline.analyze_employee_brief(brief=BRIEF, language="en-IN", answers=[answer])
    assert result.missing_critical_info == []
    sent = json.loads(pipeline_model.calls[0]["input_messages"][1]["content"][0]["text"])
    assert sent["answers"][0]["unavailable"] is True


@pytest.mark.asyncio
async def test_questions_are_not_evidence_and_invented_prices_are_rejected(pipeline_model):
    pipeline_model.extracted["facts"] = [{"text": "The price is INR 500.", "evidence": "The price is INR 500."}]
    answer = pipeline.ClarificationAnswer(field="price", question="The price is INR 500.", answer="Not known", unavailable=False)
    with pytest.raises(GenerationStageError) as failure:
        await pipeline.analyze_employee_brief(brief=BRIEF, language="en-IN", answers=[answer])
    assert failure.value.stage == "extract"
    assert failure.value.to_public_dict()["code"] == "generation_needs_review"


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["new_price", "merged_name", "new_company", "new_number", "qa_failure", "language_change", "invented_link", "wrong_speaker"])
async def test_fail_closed_at_the_relevant_stage(pipeline_model, mutation):
    if mutation == "merged_name":
        pipeline_model.extracted["agent_name"] = "Meera Related to my agency"
    elif mutation == "new_company":
        pipeline_model.extracted["company_name"] = "Imaginary Bank"
    elif mutation == "new_price":
        pipeline_model.extracted["facts"][0]["text"] += " Pay INR 500."
    elif mutation == "new_number":
        pipeline_model.repaired["call_to_action"] = "Pay INR 900 to complete a booking."
    elif mutation == "language_change":
        pipeline_model.repaired["opening"] = "నమస్కారం, మీకు ఎలా సహాయం చేయగలను?"
    elif mutation == "invented_link":
        pipeline_model.repaired["call_to_action"] = "Go to https://invented.example.com to buy."
    elif mutation == "wrong_speaker":
        pipeline_model.repaired["opening"] = "Hello, I’m Alex from Example Clinic. How can I help?"
    else:
        pipeline_model.passed = False
    with pytest.raises((GenerationStageError, BriefValidationError)):
        await pipeline.compile_employee_script(brief=BRIEF, language="en-IN")


@pytest.mark.asyncio
async def test_provider_failure_does_not_fall_back_or_repeat(monkeypatch):
    from server.brain import generation_runtime
    provider = AsyncMock(side_effect=RuntimeError("private credential error"))
    monkeypatch.setattr(generation_runtime, "generation_target", lambda: (
        SimpleNamespace(structured_completion=provider), LLMConfig(provider="gemini", model="test")))
    with pytest.raises(RuntimeError):
        await pipeline.compile_employee_script(brief=BRIEF, language="en-IN")
    provider.assert_awaited_once()


@pytest.mark.asyncio
async def test_wrong_locale_after_review_gets_one_grounded_repair(monkeypatch, pipeline_model):
    from server.brain import generation_runtime

    calls = []

    async def complete(**kwargs):
        calls.append(kwargs["schema_name"])
        if kwargs["schema_name"] == "employee_brief_extract":
            return extraction()
        if kwargs["schema_name"] == "employee_script_write":
            return draft()
        data = json.loads(kwargs["input_messages"][1]["content"][0]["text"])
        fixed = draft()
        if not data.get("validation_feedback"):
            fixed["opening"] = "నమస్కారం, నేను మీరా మాట్లాడుతున్నాను."
        else:
            assert data["selected_language"] == "en-IN"
            assert data["business"]["agent_name"] == "Meera"
        return {"passed": True, "issues": [], "fixed_script": fixed}

    monkeypatch.setattr(generation_runtime, "generation_target", lambda: (
        SimpleNamespace(structured_completion=complete), LLMConfig(provider="gemini", model="test-model")))
    _compiled, result = await pipeline.compile_employee_script(brief=BRIEF, language="en-IN")
    assert draft()["opening"] in result.agent_script
    assert calls.count("employee_script_review") == 2
    assert calls.count("employee_brief_extract") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("brief", [
    "Agent name is Meera. Company is Example Clinic. Answer questions about opening hours. Opening hours are 09:00 to 18:00. Do not offer bookings.",
    "Agent name is Meera related to my agency. Company is Example Clinic. Answer questions about opening hours. Opening hours are 09:00 to 18:00. Do not offer bookings.",
    "Agent name is Meera. Company is Example Clinic. Answer questions about opening hours. Opening hours are 09:00 to 18:00. Do not offer bookings. Use frendly phrasing.",
    "Agent name is Meera. Company is Example Clinic. Answer questions about opening hours. Opening hours are 09:00 to 18:00. Do not offer bookings. Be formal; specifically use warm simple wording.",
    "Agent name is Meera. Answer questions about opening hours. Opening hours are 09:00 to 18:00. Do not offer bookings.",
    "Help callers.",
    "Agent name is Meera. Company is Example Clinic. Answer questions about opening hours. Opening hours are 09:00 to 18:00. Do not offer bookings. The only price is INR 500. The only price is INR 700.",
    "Agent name is Meera. Company is Example Clinic. Answer questions about opening hours. Opening hours are 09:00 to 18:00. Do not offer bookings. Explain pricing only if asked; no discount is available.",
    "Agent name is Meera. Company is Example Clinic. Answer questions about opening hours. Opening hours are 09:00 to 18:00. Do not offer bookings. Never promise a callback.",
    "Agent name is Meera. Company is Example Clinic. Answer questions about opening hours. Opening hours are 09:00 to 18:00. Do not offer bookings. Ask one question only if needed.",
])
async def test_ten_brief_shapes_remain_grounded_or_need_input(pipeline_model, brief):
    if "Example Clinic" not in brief:
        pipeline_model.extracted["company_name"] = None
    if brief == "Help callers.":
        pipeline_model.extracted.update(agent_name=None, primary_goal=None, facts=[], forbidden_actions=[])
    if "only price" in brief:
        pipeline_model.extracted["conflicts"] = ["Which is the current price: INR 500 or INR 700?"]
    result = await pipeline.analyze_employee_brief(brief=brief, language="en-IN")
    response = pipeline.clarification_response(result)
    assert response["status"] == ("needs_user_input" if brief == "Help callers." or "only price" in brief else "ready")


def test_analysis_route_is_authorized_read_only_and_errors_do_not_leak(monkeypatch, pipeline_model):
    from server.routes import app_agents
    app = FastAPI()
    app.include_router(app_agents.router)
    principal = SimpleNamespace(tenant_id="test-workspace")
    app.dependency_overrides[app_agents.require_subscriber_jwt] = lambda: principal
    monkeypatch.setattr(app_agents, "require_subscriber_permission", lambda *_: None)
    monkeypatch.setattr(app_agents, "subscriber_workspace_tenant_id", lambda _: "test-workspace")
    monkeypatch.setattr(app_agents.platform_languages, "is_enabled", lambda _: True)
    create = AsyncMock(side_effect=AssertionError("analysis must not create an agent"))
    monkeypatch.setattr(app_agents.agent_service, "create_agent", create)
    with TestClient(app) as client:
        assert client.post("/api/app/agents/analyze-brief", json={"brief": BRIEF}).json()["status"] == "ready"
        pipeline_model.extracted["agent_name"] = None
        response = client.post("/api/app/agents/analyze-brief", json={"brief": BRIEF})
        assert response.status_code == 200 and response.json()["questions"][0]["field"] == "agent_name"
        monkeypatch.setattr(app_agents, "analyze_employee_brief", AsyncMock(side_effect=RuntimeError("private credential")))
        response = client.post("/api/app/agents/analyze-brief", json={"brief": BRIEF})
        assert response.status_code == 502 and "private credential" not in response.text
    create.assert_not_awaited()


@pytest.mark.parametrize("brief,expected", [
    ("Agent name is Moksha related to my agency.", "Moksha"),
    ("Agent name is Moksha realted to my agency.", "Moksha"),
    ("Customer name is Alex. Explain the offer.", ""),
    ("Business name is Mohan Private Limited and the person who calls the users is Sindhuja.", "Sindhuja"),
])
def test_identity_is_person_only_and_never_caller_or_company(brief, expected):
    from server.brain.brief_contract import resolve_agent_identity
    name, issues, _ = resolve_agent_identity(brief)
    assert name == expected
    assert bool(issues) == (not expected)


@pytest.mark.asyncio
@pytest.mark.parametrize("temperature", [0.2, 0.5])
async def test_gemini_structured_requests_use_the_stage_temperature(monkeypatch, temperature):
    import httpx
    from server.providers.gemini_llm import GeminiLLMAdapter

    monkeypatch.setattr("server.providers.gemini_llm._api_key", lambda: "synthetic-test-key")
    sent = {}

    def handle(request):
        sent.update(json.loads(request.content))
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"ok":true}'}]}}]})

    client = httpx.AsyncClient
    monkeypatch.setattr("server.providers.gemini_llm.httpx.AsyncClient", lambda **kwargs: client(**kwargs, transport=httpx.MockTransport(handle)))
    await GeminiLLMAdapter().structured_completion(input_messages=[{"role": "user", "content": "Test"}],
        schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
        config=LLMConfig(provider="gemini", model="synthetic-model", temperature=temperature))
    assert sent["generationConfig"]["temperature"] == temperature


@pytest.mark.asyncio
async def test_openai_structured_requests_use_the_stage_temperature(monkeypatch):
    from server.providers.openai_llm import OpenAILLMAdapter
    response = SimpleNamespace(output_text='{"ok":true}')
    create = AsyncMock(return_value=response)
    monkeypatch.setattr("server.utils.http_clients.get_openai_client", lambda: SimpleNamespace(responses=SimpleNamespace(create=create)))
    monkeypatch.setattr("server.services.saas.post_call_costs.record_post_call_response", AsyncMock())
    await OpenAILLMAdapter().structured_completion(input_messages=[{"role": "user", "content": "Test"}],
        schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
        config=LLMConfig(provider="openai", model="gpt-4.1", temperature=0.2))
    assert create.await_args.kwargs["temperature"] == 0.2
