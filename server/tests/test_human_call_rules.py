"""Human-call compile rules — latest requirement wins, no interrogation checklist."""
from __future__ import annotations

import pytest

from server.brain.agent_script_compiler import (
    _deterministic_script,
    resolve_script_identity,
)
from server.brain.sections import STATIC_OUTPUT_RULES
from server.call.end_call_validate import validate_end_call
from server.prompts.agent_voice_rules import HUMAN_CALL_RULES, script_writer_system


def test_named_agent_brief_does_not_garble_work_scope():
    brief = (
        "ok create a agent named satish where he is a expert at selling plots "
        "in exclusive conclaves which is a prime location where 1000 square feet "
        "apartments are selling at cheap rates 50 lakhs"
    )
    name, company, work, opening = resolve_script_identity(brief, language="te-IN")
    assert name.lower() == "satish"
    assert company == ""
    assert "1000 square feet" in work
    assert "50 lakhs" in work
    assert "create a t" not in work.lower()
    assert "satish" not in work.lower()
    assert "nenu satish" in opening.lower()
    assert "konchem time" in opening.lower() or "moment" in opening.lower()


def test_extract_agent_named_pattern():
    from server.brain.agent_script_compiler import (
        extract_agent_name_from_brief,
        extract_company_from_brief,
        resolve_script_identity,
    )

    assert extract_agent_name_from_brief("agent named Kavya for nursery") == "Kavya"
    assert extract_agent_name_from_brief("Agent name: Swetha") == "Swetha"
    assert extract_agent_name_from_brief("Agent name Meera") == "Meera"
    assert extract_agent_name_from_brief("agent name Ravi") == "Ravi"
    assert extract_agent_name_from_brief("Agent name Priya from Acme Realty.") == "Priya"
    assert extract_company_from_brief("Agent name Priya from Acme Realty. We offer plots.") == "Acme Realty"
    assert extract_company_from_brief(
        "Create an English sales agent named Priya for Acme Realty. Known listing: 2BHK."
    ) == "Acme Realty"
    assert extract_company_from_brief(
        "Create an English appointment agent named Meera for SmileCare Dental. Book dentist appointments."
    ) == "SmileCare Dental"
    assert extract_company_from_brief(
        "Create an English service agent named Ravi for AutoCare Motors car service center."
    ) == "AutoCare Motors"
    assert extract_company_from_brief(
        "Create an English sales counselor named Karthik for DriveRight Auto Care in Hyderabad. "
        "Workshop with pickup from Hitec City and Gachibowli."
    ) == "DriveRight Auto Care"
    name, company, work, opening = resolve_script_identity(
        "Agent name Priya from Acme Realty. We offer plots from 50 lakhs.",
        language="te-IN",
    )
    assert name == "Priya"
    assert company == "Acme Realty"
    assert "50 lakhs" in work
    assert "Priya from Acme" not in name
    assert "We offer residential" not in company
    assert "nenu priya" in opening.lower()
    assert "Acme Realty" in opening
    assert "konchem time" in opening.lower() or "moment" in opening.lower()


def test_static_rules_forbid_interrogation_checklist():
    blob = STATIC_OUTPUT_RULES.lower() + HUMAN_CALL_RULES.lower()
    assert "checklist" in blob
    assert "overrides script defaults" in blob
    assert "don't call" in blob or "dont call" in blob.replace("'", "")
    assert "whatsapp" in blob
    assert "not a hangup" in blob or "do not hang up" in blob
    assert "15" in blob or "30–80" in blob or "30-80" in blob or "150" in blob
    assert "length" in blob
    assert "tts" in blob or "short" in blob or "meaningful" in blob


def test_script_writer_does_not_order_qualify_first():
    system = script_writer_system(language="te-IN", budget_tokens=3500)
    low = system.lower()
    assert "question tree" in low or "step 1" in low
    assert "qualified lead" in low or "convert interested" in low
    assert "earn its place" in low or "answer before you qualify" in low or "ask-if-unknown" in low or "factual questions before" in low
    assert "interrogation checklist" in system.lower() or "not a form" in system.lower() or "answer before you qualify" in system.lower() or "never re-ask" in system.lower()
    assert "qualify budget, location, timeline" not in system.lower()


def test_deterministic_script_has_human_flow():
    script = _deterministic_script(
        "Sell plots. 1000 sq ft from 50 lakhs.",
        agent_name="Satish",
        company_name="",
        work_scope="selling plots",
        opening_line="Namaste",
        language="te-IN",
        role="sales",
    )
    assert "NATURAL SALES PROGRESSION" in script
    assert "never re-ask" in script.lower()
    assert "Latest customer requirement overrides" in script or "overrides script defaults" in script.lower()


def test_dont_call_again_hangup_accepted():
    d = validate_end_call(
        {"should_end": True, "reason": "goodbye", "farewell": "Sare, good day."},
        user_text="వద్దు, నాకు interest లేదు. ఇక call చేయకండి.",
        language="te-IN",
        completed_turns=4,
    )
    assert d.accepted is True


def test_dont_call_inferred_when_model_forgets_end_call():
    d = validate_end_call(
        {"should_end": False, "reason": "none", "farewell": ""},
        user_text="వద్దు, నాకు interest లేదు. ఇక call చేయకండి.",
        language="te-IN",
        completed_turns=4,
    )
    assert d.accepted is True
    assert d.reason == "goodbye"


def test_location_dislike_is_not_hangup():
    d = validate_end_call(
        {"should_end": True, "reason": "firm_refusal", "farewell": "Sare, good day."},
        user_text="Location నాకు నచ్చలేదు.",
        language="te-IN",
        completed_turns=3,
    )
    assert d.accepted is False
    inferred = validate_end_call(
        {"should_end": False, "reason": "none", "farewell": ""},
        user_text="Location నాకు నచ్చలేదు.",
        language="te-IN",
        completed_turns=3,
    )
    assert inferred.accepted is False


def test_undecided_budget_is_not_refusal():
    d = validate_end_call(
        {"should_end": True, "reason": "firm_refusal", "farewell": "Bye"},
        user_text="నాకు budget ఇంకా decide కాలేదు.",
        language="te-IN",
        completed_turns=2,
    )
    assert d.accepted is False


def test_just_price_vaddu_is_not_refusal():
    d = validate_end_call(
        {"should_end": True, "reason": "firm_refusal", "farewell": "Bye"},
        user_text="Just price చెప్పండి, ఇంకేమీ వద్దు.",
        language="te-IN",
        completed_turns=2,
    )
    assert d.accepted is False


def test_compiled_script_includes_live_call_guide():
    script = _deterministic_script(
        "Sell plots. 1000 sq ft from 50 lakhs.",
        agent_name="Satish",
        company_name="",
        work_scope="selling plots",
        opening_line="Namaste",
        language="te-IN",
    )
    assert "LIVE CALL GUIDE" in script
    assert "overrides catalog defaults" in script


def test_sprawl_discovery_recommendation_headers_stripped():
    from server.brain.agent_script_compiler import (
        ensure_script_identity_and_scope,
        validate_agent_script,
    )

    raw = (
        "--- DISCOVERY RULES ---\nAsk budget if unknown.\n\n"
        "--- RECOMMENDATION RULES ---\nAlways pitch villa.\n\n"
        "--- CONVERSATION FLOW ---\nStep 1 ask name.\n\n"
        "--- GUARDRAILS ---\nNever invent prices.\n"
    )
    out = ensure_script_identity_and_scope(
        raw,
        agent_name="Priya",
        company_name="Acme",
        work_scope="plots from 50 lakhs",
        opening_line="Hi",
        language="en-IN",
        role="sales",
    )
    assert "DISCOVERY RULES" not in out
    assert "RECOMMENDATION RULES" not in out
    assert "Always pitch villa" not in out
    assert validate_agent_script(out, brief="plots from 50 lakhs", agent_name="Priya") == []


def test_validate_agent_script_rejects_step_tree_and_invented_price():
    from server.brain.agent_script_compiler import (
        ensure_script_identity_and_scope,
        validate_agent_script,
    )

    brief = "Sell plots for Acme. Agent name Satish. Plots from 50 lakhs."
    bad = (
        "--- VOICE STYLE ---\n"
        "Step 1: Ask budget. Step 2: Ask location.\n\n"
        "--- CONVERSATION FLOW ---\n"
        "Step 1 greet then qualify.\n\n"
        "--- GUARDRAILS ---\n"
        "Villas start at 95 lakhs.\n"
    )
    bound = ensure_script_identity_and_scope(
        bad,
        agent_name="Satish",
        company_name="Acme",
        work_scope="Sell plots. Plots from 50 lakhs.",
        opening_line="Namaste",
        language="te-IN",
        role="sales",
    )
    issues = validate_agent_script(bound, brief=brief, agent_name="Satish")
    assert any("Step/Question" in r for r in issues)
    assert any("price/amount" in r for r in issues)


def test_validate_agent_script_accepts_clean_bound_script():
    from server.brain.agent_script_compiler import (
        _deterministic_script,
        validate_agent_script,
    )

    brief = "Sell plots for Acme. Agent name Satish. Plots from 50 lakhs."
    script = _deterministic_script(
        brief,
        agent_name="Satish",
        company_name="Acme",
        work_scope="Sell plots. Plots from 50 lakhs.",
        opening_line="Namaste",
        language="te-IN",
        role="sales",
    )
    assert validate_agent_script(script, brief=brief, agent_name="Satish") == []


def test_spoken_pack_uses_policy_pointer_not_full_human_call():
    from server.prompts.agent_voice_rules import (
        HUMAN_CALL_RULES,
        PHONE_CALL_POLICY_PTR,
        spoken_pack_for,
    )

    pack = spoken_pack_for("te-IN")
    assert PHONE_CALL_POLICY_PTR in pack
    # Full HUMAN_CALL dump must not be embedded (token budget).
    assert "Turn priority every reply:" not in pack
    assert "Turn priority every reply:" in HUMAN_CALL_RULES


@pytest.mark.asyncio
async def test_compile_falls_back_when_llm_invents_price():
    from unittest.mock import AsyncMock, patch

    from server.brain.agent_script_compiler import compile_agent_from_brief

    brief = "Agent name Satish. Sell plots for Acme. Plots from 50 lakhs. Talk naturally."
    bad_payload = {
        "agent_script": (
            "AGENT IDENTITY\nSatish from Acme.\n\n"
            "OPENING\nNamaste.\n\n"
            "VOICE STYLE\nNatural Tanglish.\n\n"
            "CONVERSATION FLOW\nAnswer first.\n\n"
            "GUARDRAILS\nVillas from 95 lakhs.\n\n"
            "CLOSING\nThanks."
        ),
        "agent_name": "Satish",
        "company_name": "Acme",
        "role": "sales",
        "key_facts": ["50 lakhs"],
    }
    with patch(
        "server.brain.agent_script_compiler._llm_generate_script",
        new=AsyncMock(return_value=bad_payload),
    ):
        compiled, result, *_ = await compile_agent_from_brief(
            brief=brief,
            language="te-IN",
            use_llm=True,
        )
    # This incomplete draft is rejected by the sectional quality gate before
    # factual validation. The invented-price assertion below remains required.
    assert result.optimizer_model == "legacy_deterministic_quality_floor_v1"
    assert "95" not in result.agent_script
    assert "LIVE CALL GUIDE" in result.agent_script
    assert "STATIC OUTPUT RULES" in compiled or "Turn priority" in compiled
