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
    for needle in ("AGENT IDENTITY", "LIVE CALL GUIDE", "CONVERSATION FLOW", "ROLE & OBJECTIVE", "STATIC OUTPUT"):
        assert needle in compiled, f"{key}: missing {needle}"
    assert STATIC_OUTPUT_RULES_VERSION.startswith("sr_v")
    script = result.agent_script or ""
    assert estimate_tokens(script) > 200
    if role in ("sales", "lead_qualification"):
        assert "NATURAL SALES" in compiled
    if role == "appointment":
        assert "APPOINTMENT FLOW" in compiled
    if role == "education":
        assert "EDUCATION FLOW" in compiled
    if role == "support":
        assert "SERVICE / SUPPORT FLOW" in compiled


def test_named_for_company_extraction_on_eval_briefs():
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
