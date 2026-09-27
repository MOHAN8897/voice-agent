"""Gemini Live must receive full user business script (identity, offer, role, opening)."""
from __future__ import annotations

import pytest

from server.brain.agent_script_compiler import compile_agent_from_brief
from server.eval.behavior_scenarios import AGENTIC_BRIEFS, EVAL_BRIEFS
from server.realtime.gemini_audio_session import build_gemini_audio_session_instructions

_CASES = [
    ("sales_acme", EVAL_BRIEFS["sales"], "Acme Realty", "fifty lakhs"),
    ("support_billing", EVAL_BRIEFS["support"], "Acme Billing", "invoices"),
    ("smilecare", AGENTIC_BRIEFS["smilecare_dental"], "SmileCare Dental", "appointment"),
    ("salesflow", AGENTIC_BRIEFS["salesflow_crm"], "SalesFlow CRM", "five thousand"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("key,spec,company_needle,fact_needle", _CASES)
async def test_gemini_live_prompt_retains_compiled_business_script(
    key: str,
    spec: dict,
    company_needle: str,
    fact_needle: str,
):
    compiled, result, *_ = await compile_agent_from_brief(
        brief=spec["brief"],
        language=spec.get("language", "en-IN"),
        use_llm=False,
        interpret_brief=False,
        direction="outbound",
    )
    assert company_needle.lower() in (result.company_name or "").lower() or company_needle.lower() in compiled.lower()

    gemini = build_gemini_audio_session_instructions(
        compiled,
        language=spec.get("language", "en-IN"),
        direction="outbound",
        opening_greeting="Hi, do you have a moment?",
    )
    low = gemini.lower()
    assert "pinned business script" in low
    assert "company & offer" in low or company_needle.lower() in low
    assert "canonical opening" in low or "example opening" in low
    assert "your role on this call" in low or "role on this call" in low
    assert fact_needle.lower() in low or fact_needle.lower() in (result.agent_script or "").lower()
    assert result.agent_name.lower() in low
    assert "adherence" in low
    assert "--- calling script ---" not in low
    assert low.count("pinned company & offer") == 1


@pytest.mark.asyncio
async def test_gemini_prompt_includes_platform_workflow_when_trimmed():
    brief = EVAL_BRIEFS["sales"]["brief"]
    compiled, *_ = await compile_agent_from_brief(
        brief=brief,
        language="en-IN",
        use_llm=False,
        interpret_brief=False,
        direction="outbound",
    )
    gemini = build_gemini_audio_session_instructions(
        compiled,
        language="en-IN",
        direction="outbound",
        token_budget=2500,
    )
    assert "OUTBOUND WORKFLOW" in gemini or "PINNED CONVERSATION FLOW" in gemini
    assert "Priya" in gemini
