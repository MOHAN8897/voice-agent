"""Five critical tests: natural sales brain progression (interest → name → preference → next step)."""
from __future__ import annotations

from server.brain.agent_script_compiler import (
    _deterministic_script,
    _sanitize_conversation_flow,
    ensure_script_identity_and_scope,
)
from server.brain.sections import STATIC_OUTPUT_RULES, default_section_seeds
from server.prompts.agent_voice_rules import live_realtime_output_rules, script_writer_system
from server.prompts.conversation_policy import (
    HUMAN_FLOW_SECTION,
    LIVE_CALL_GUIDE_BODY,
    checklist_flow_detected,
    flow_section,
)
from server.services.voice_pipeline_limits import LIVE_REPLY_BREVITY_RULE, LIVE_REPLY_MAX_CHARS


def test_1_sales_flow_has_natural_progression_ladder():
    """Critical 1: sales FLOW teaches interest → name → preference → next step."""
    flow = flow_section("sales")
    low = flow.lower()
    assert "NATURAL SALES PROGRESSION" in flow
    assert "interest" in low
    assert "name" in low
    assert "never re-ask" in low
    assert "next step" in low
    assert "never question 1" in low or "question/step" in low
    assert "step 1 trees" in low or "never question 1" in low


def test_2_soft_ask_if_unknown_fields_survive_sanitize():
    """Critical 2: soft plot ladder is kept; hard Step trees are wiped."""
    soft = (
        "--- CONVERSATION FLOW ---\n"
        "If unknown, confirm interest once. Then ask name. "
        "Then ask which area they want the plot in. Then offer a site visit.\n\n"
        "--- GUARDRAILS ---\nNever invent prices.\n"
    )
    soft_out = ensure_script_identity_and_scope(
        soft,
        agent_name="Priya",
        company_name="Acme Realty",
        work_scope="selling residential plots in Hyderabad",
        opening_line="Hi, this is Priya from Acme Realty.",
        language="en-IN",
        role="sales",
    )
    assert "area they want the plot" in soft_out.lower() or "brief-specific ask-if-unknown" in soft_out.lower()
    assert "NATURAL SALES PROGRESSION" in soft_out
    assert "never re-ask interest" in soft_out.lower() or "already said yes" in soft_out.lower()

    hard = (
        "--- CONVERSATION FLOW ---\n"
        "Step 1 greet. Step 2 ask interest. Step 3 ask name. Step 4 ask location.\n\n"
        "--- GUARDRAILS ---\nNever invent.\n"
    )
    hard_out = _sanitize_conversation_flow(hard, "sales")
    assert "step 2" not in hard_out.lower()
    assert checklist_flow_detected("Step 1 greet. Step 2 ask interest.") is True
    assert checklist_flow_detected(
        "If unknown confirm interest. Then ask name. Then ask preferred area."
    ) is False


def test_3_after_interest_instructions_forbid_reasking_interest():
    """Critical 3: compiled live instructions forbid restarting at interest."""
    guide = LIVE_CALL_GUIDE_BODY.lower()
    static = STATIC_OUTPUT_RULES.lower()
    live = live_realtime_output_rules("en-IN").lower()
    for blob in (guide, static, live):
        assert "interested" in blob or "interest" in blob
        assert "never re-ask interest" in blob or "do not re-ask interest" in blob or "never re-ask" in blob
    assert "human salesperson" in guide or "natural phone sales" in guide or "warm ack" in guide


def test_4_writer_and_defaults_require_progressive_sales_not_freeze():
    """Critical 4: script writer + default qualification section progress the lead."""
    system = script_writer_system(language="en-IN", budget_tokens=3500).lower()
    assert "ask-if-unknown" in system
    assert "interest" in system and "name" in system
    assert "never re-ask" in system
    assert "question 1" in system  # forbidden pattern mentioned
    seeds = {s.type: s.raw_text.lower() for s in default_section_seeds()}
    qual = seeds["flow_qualification"]
    assert "interest" in qual and "name" in qual
    assert "do not run a question checklist" not in qual
    assert "progress" in qual or "ask-if-unknown" in qual


def test_5_natural_speech_room_and_deterministic_sales_script():
    """Critical 5: brevity allows ack+question; deterministic sales script embeds ladder."""
    assert LIVE_REPLY_MAX_CHARS >= 200
    assert "warm acknowledgment" in LIVE_REPLY_BREVITY_RULE.lower() or "at most one question" in LIVE_REPLY_BREVITY_RULE.lower()
    assert "two questions" in LIVE_REPLY_BREVITY_RULE.lower() or "never two questions" in LIVE_REPLY_BREVITY_RULE.lower()

    script = _deterministic_script(
        "Sell Hyderabad plots. Capture interest, name, preferred area, then book a visit. Agent Priya at Acme Realty.",
        agent_name="Priya",
        company_name="Acme Realty",
        work_scope="selling Hyderabad residential plots",
        opening_line="Hi, this is Priya from Acme Realty. How can I help today?",
        language="en-IN",
        role="sales",
    )
    low = script.lower()
    assert "NATURAL SALES PROGRESSION" in script
    assert "live call guide" in low
    assert "interested" in low or "interest" in low
    assert "name" in low
    assert HUMAN_FLOW_SECTION.split("Role on this call")[0] in script or "natural sales progression" in low


def test_platform_rules_ask_unknown_and_busy_stay():
    from server.brain.agent_script_compiler import _platform_call_rules

    rules = _platform_call_rules(
        agent_name="Priya",
        role="sales",
        direction="outbound",
        language="en-IN",
    ).lower()
    assert "have not already given" in rules
    assert "stay on the line" in rules
    assert "okay/thanks" in rules or "bare okay" in rules
    assert "collect missing lead details one at a time" not in rules
