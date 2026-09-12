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
    assert "OUTBOUND WORKFLOW" in script
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
    )
    low = script.lower()
    assert "you are priya" in low
    assert "this is mohan" not in low
    assert "do you have a moment" in low
    assert "how can i help" not in low
    assert "COMPANY & OFFER" in script
    assert "OUTBOUND WORKFLOW" in script

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
