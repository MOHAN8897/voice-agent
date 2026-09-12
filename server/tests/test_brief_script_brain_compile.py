"""Brief → script → compiled brain smoke (deterministic path, no LLM)."""
from __future__ import annotations

import pytest

from server.agent.brain_prompt_composer import BUDGET_MAX_TOKENS, CACHE_MIN_TOKENS, estimate_tokens
from server.agent.instruction_builder import LIVE_TURN_DISCIPLINE
from server.brain.agent_script_compiler import compile_agent_from_brief, extract_company_from_brief
from server.brain.sections import STATIC_OUTPUT_RULES_VERSION
from server.eval.behavior_scenarios import AGENTIC_BRIEFS, EVAL_BRIEFS
from server.prompts.conversation_policy import infer_agent_role


@pytest.mark.asyncio
@pytest.mark.parametrize("key,spec", list(EVAL_BRIEFS.items()) + list(AGENTIC_BRIEFS.items()))
async def test_brief_compiles_script_and_brain(key: str, spec: dict):
    brief = spec["brief"]
    lang = spec.get("language", "en-IN")
    expected = spec.get("expected_role")
    compiled, result, _raw_t, comp_t, _budget = await compile_agent_from_brief(
        brief=brief,
        language=lang,
        use_llm=False,
        budget_tokens=3500,
    )
    role = infer_agent_role(brief)
    if expected:
        assert role == expected, f"{key}: role {role} != {expected}"
    assert CACHE_MIN_TOKENS <= comp_t <= BUDGET_MAX_TOKENS, f"{key}: tokens {comp_t}"
    assert result.agent_name.strip(), f"{key}: empty agent name"
    assert LIVE_TURN_DISCIPLINE.strip() not in compiled
    for needle in ("AGENT IDENTITY", "COMPANY & OFFER", "CANONICAL OPENING", "STATIC OUTPUT", "CALL END"):
        assert needle in compiled, f"{key}: missing {needle}"
    assert STATIC_OUTPUT_RULES_VERSION.startswith("sr_v")
    script = result.agent_script or ""
    assert "COMPANY & OFFER" in script
    assert "YOUR ROLE ON THIS CALL" in script
    assert "OUTBOUND WORKFLOW" not in script
    assert "GUARDRAILS" not in script
    assert "PLATFORM CALL RULES" in compiled or "OUTBOUND WORKFLOW" in compiled
    assert "LIVE CALL GUIDE" not in script
    assert "CONVERSATION FLOW" not in script


def test_structured_script_strips_other_speaker_name():
    from server.brain.agent_script_compiler import _structured_business_script

    brief = (
        "Agent named Priya. this is Mohan, related to Bindusara Agencies working in real estate "
        "plots near outer ring road Hyderabad"
    )
    script = _structured_business_script(
        brief,
        agent_name="Priya",
        company_name="Bindusara Agencies",
        work_scope="plots near outer ring road Hyderabad",
        opening_line="Hi, this is Priya calling from Bindusara Agencies. Do you have a moment?",
        language="en-IN",
        role="sales",
    )
    low = script.lower()
    assert "you are priya" in low
    assert "this is mohan" not in low
    assert "do you have a moment" in low
    assert "how can i help" not in low
    assert "COMPANY & OFFER" in script
    assert "YOUR ROLE ON THIS CALL" in script
    assert "OUTBOUND WORKFLOW" not in script

    expected = {
        "sales": "Acme Realty",
        "priya_estates": "Priya Estates",
        "smilecare_dental": "SmileCare Dental",
        "salesflow_crm": "SalesFlow CRM",
        "autocare_motors": "AutoCare Motors",
        "speakpro_academy": "SpeakPro Academy",
    }
    briefs = {**EVAL_BRIEFS, **AGENTIC_BRIEFS}
    for key, company in expected.items():
        got = extract_company_from_brief(briefs[key]["brief"])
        assert got == company, f"{key}: got {got!r} expected {company!r}"


def test_bindusara_tis_brief_prefers_agent_named_over_name_is():
    from server.brain.agent_script_compiler import resolve_script_identity

    brief = (
        "name is mohan, realted to bindusara agencies working in real estate "
        "create a agent naed tis who should convince the users to buy plots in our venture "
        "near outer ring road in hyderabad"
    )
    name, company, work, opening = resolve_script_identity(brief, language="en-IN")
    assert name == "Tis"
    assert company == "Bindusara Agencies"
    assert "outer ring road" in work.lower() or "hyderabad" in work.lower()
    assert "tis" in opening.lower()
    assert "mohan" not in opening.lower()


@pytest.mark.asyncio
async def test_bindusara_tis_brief_compiled_script():
    from server.brain.agent_script_compiler import compile_agent_from_brief

    brief = (
        "name is mohan, realted to bindusara agencies working in real estate "
        "create a agent naed tis who should convince the users to buy plots in our venture "
        "near outer ring road in hyderabad"
    )
    _compiled, result, *_ = await compile_agent_from_brief(brief=brief, language="en-IN", use_llm=False)
    script = result.agent_script or ""
    assert "Tis" in script
    assert "Bindusara Agencies" in script
    assert "OUTBOUND WORKFLOW" not in script
    assert "mohan" not in script.lower()
    assert result.agent_name == "Tis"
