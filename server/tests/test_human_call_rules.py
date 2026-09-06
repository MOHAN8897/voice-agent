"""Human-call compile rules — latest requirement wins, no interrogation checklist."""
from __future__ import annotations

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
    assert "Nenu satish" in opening


def test_extract_agent_named_pattern():
    from server.brain.agent_script_compiler import extract_agent_name_from_brief

    assert extract_agent_name_from_brief("agent named Kavya for nursery") == "Kavya"
    assert extract_agent_name_from_brief("Agent name: Swetha") == "Swetha"
    assert extract_agent_name_from_brief("Agent name Meera") == "Meera"
    assert extract_agent_name_from_brief("agent name Ravi") == "Ravi"


def test_static_rules_forbid_interrogation_checklist():
    blob = STATIC_OUTPUT_RULES.lower() + HUMAN_CALL_RULES.lower()
    assert "checklist" in blob
    assert "overrides script defaults" in blob
    assert "don't call" in blob or "dont call" in blob.replace("'", "")
    assert "whatsapp" in blob
    assert "not a hangup" in blob or "do not hang up" in blob


def test_script_writer_does_not_order_qualify_first():
    system = script_writer_system(language="te-IN", budget_tokens=3500)
    assert "interrogation checklist" in system.lower() or "not a form" in system.lower() or "answer before you qualify" in system.lower()
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
    assert "Do not run a budget, location, or timeline checklist" in script
    assert "Latest customer requirement overrides" in script


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


def test_checklist_flow_is_rewritten():
    from server.brain.agent_script_compiler import ensure_script_identity_and_scope

    raw = (
        "--- CONVERSATION FLOW ---\n"
        "Ask budget, location, and timeline one at a time.\n\n"
        "--- GUARDRAILS ---\nNever invent prices.\n"
    )
    out = ensure_script_identity_and_scope(
        raw,
        agent_name="Satish",
        company_name="",
        work_scope="selling plots",
        opening_line="Namaste",
        language="te-IN",
        role="sales",
    )
    assert "one at a time" not in out.lower()
    assert "Do not run a budget, location, or timeline checklist" in out
