"""Critical brain-compile / Gemini prompt fixes from script→brain audit."""
from __future__ import annotations

import pytest

from server.brain.agent_script_compiler import (
    _format_business_offer,
    _sanitize_conversation_flow,
    validate_agent_script,
)
from server.prompts.conversation_policy import infer_call_direction, writer_flow_must_preserve
from server.realtime.gemini_audio_session import build_gemini_audio_session_instructions
from server.services.saas.agent_onboarding_compose import _fallback_greeting
from server.services.saas.script_variables import merge_variables


def test_writer_flow_must_preserve_detects_conditional_steps():
    flow = (
        "1. Greet briefly.\n"
        "2. Check enrollment date before discussing refunds.\n"
        "3. Ask permission before any WhatsApp follow-up."
    )
    assert writer_flow_must_preserve(flow)
    out = _sanitize_conversation_flow(
        f"--- CONVERSATION FLOW ---\n{flow}\n",
        role="support",
    )
    assert "enrollment date" in out.lower()
    assert "whatsapp" in out.lower()
    assert "PLATFORM FLOW POLICY" in out


def test_validate_rejects_invented_price_and_wrong_company():
    brief = "Broski Academy. Course fee is ₹12,000. Agent Priya."
    script = """--- AGENT IDENTITY ---
You are Priya, calling from WrongCo.

--- CANONICAL OPENING ---
Example opening: Hi, this is Priya from WrongCo. Our course is only ₹99,999.

--- COMPANY & OFFER ---
WrongCo sells courses for ₹99,999.
"""
    issues = validate_agent_script(
        script,
        brief=brief,
        agent_name="Priya",
        company_name="Broski Academy",
    )
    assert any("price" in i.lower() or "amount" in i.lower() for i in issues)
    assert any("company" in i.lower() or "wrong" in i.lower() for i in issues)


def test_gemini_pins_outbound_workflow_from_compiled_brain():
    brain = (
        "--- AGENT IDENTITY ---\nYou are Priya, calling from Acme.\n\n"
        "--- PLATFORM CALL RULES ---\n"
        "--- OUTBOUND WORKFLOW ---\n"
        "Step A: confirm they have a moment.\n"
        "Step B: ask about plot size preference.\n"
    )
    gemini = build_gemini_audio_session_instructions(
        brain,
        language="en-IN",
        direction="outbound",
        opening_greeting="Hi, Priya from Acme.",
    )
    assert "PINNED CONVERSATION FLOW" in gemini
    assert "plot size" in gemini.lower()


def test_mandatory_business_facts_survive_offer_shortening():
    brief = (
        "Acme Insurance. We sell term plans. "
        + ("Affordable family cover with strong hospital network. " * 40)
        + "Refunds are not available after enrollment date is confirmed."
    )
    offer = _format_business_offer(
        brief,
        agent_name="Priya",
        company_name="Acme Insurance",
        work_scope="term insurance",
    )
    assert "refund" in offer.lower() or "enrollment" in offer.lower()
    assert "MANDATORY BUSINESS FACTS" in offer


def test_infer_call_direction_prefers_outbound_when_mixed():
    brief = (
        "We run outbound sales calls to leads. "
        "When customers call inbound for support, transfer to billing."
    )
    assert infer_call_direction(brief) == "outbound"


def test_onboarding_fallback_outbound_telugu_uses_double_brace_tags():
    greeting = _fallback_greeting(
        "Priya",
        "sales",
        "Broski",
        language="te-IN",
        direction="outbound",
    )
    assert "{{business_name}}" in greeting
    assert "thanks for calling" not in greeting.lower()
    vars_ = merge_variables(None, greeting, "")
    keys = {v["key"] for v in vars_}
    assert "business_name" in keys


@pytest.mark.asyncio
async def test_default_compile_path_runs_validation_not_empty():
    from server.brain.agent_script_compiler import compile_agent_from_brief

    compiled, result, *_ = await compile_agent_from_brief(
        brief="Broski Academy. Agent Priya. Outbound course sales. Fee ₹12,000 only.",
        language="en-IN",
        use_llm=False,
        interpret_brief=False,
        direction="outbound",
    )
    assert "Broski" in compiled or "broski" in compiled.lower()
    assert result.company_name or "Priya" in result.agent_name
