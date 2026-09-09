"""Critical agentic multi-business conversation flows (offline judge + compile).

Covers five very different conversation patterns:
1. Priya Estates — plot/villa sales
2. SmileCare Dental — appointment booking
3. SalesFlow CRM — SaaS subscription
4. AutoCare Motors — service request + intent override
5. SpeakPro Academy — spoken English / trial class
"""
from __future__ import annotations

import pytest

from server.agent.brain_prompt_composer import BUDGET_MAX_TOKENS, estimate_tokens
from server.brain.agent_script_compiler import (
    _assemble_brain,
    _deterministic_script,
    resolve_script_identity,
)
from server.eval.behavior_scenarios import AGENTIC_BRIEFS, AGENTIC_SCRIPTS
from server.prompts.conversation_policy import (
    detect_reask_known_facts,
    flow_section,
    infer_agent_role,
    judge_turn,
)


FLOW_MARKERS = {
    "sales": "NATURAL SALES PROGRESSION",
    "appointment": "APPOINTMENT FLOW",
    "support": "SERVICE / SUPPORT FLOW",
    "education": "EDUCATION FLOW",
}


@pytest.mark.parametrize("biz_id,spec", list(AGENTIC_BRIEFS.items()))
def test_agentic_role_inference(biz_id: str, spec: dict):
    role = infer_agent_role(spec["brief"])
    assert role == spec["expected_role"], f"{biz_id}: got {role}"


@pytest.mark.parametrize("biz_id,spec", list(AGENTIC_BRIEFS.items()))
def test_agentic_compiled_flow_and_budget(biz_id: str, spec: dict):
    role = spec["expected_role"]
    brief = spec["brief"]
    name, company, work, opening = resolve_script_identity(brief, language="en-IN")
    script = _deterministic_script(
        brief,
        agent_name=name,
        company_name=company,
        work_scope=work,
        opening_line=opening,
        language="en-IN",
        role=role,
    )
    marker = FLOW_MARKERS[role]
    assert marker in script, f"{biz_id} missing {marker}"
    low = script.lower()
    assert "never re-ask" in low
    assert "question 1" in low or "question/step" in low or "step 1 trees" in low

    # Role-specific anti-checklist cues must survive compile.
    if role == "appointment":
        assert "tomorrow evening" in low or "do not ask when" in low or "never re-ask when" in low
    if role == "support":
        assert "latest intent" in low or "add-on" in low or "also check" in low
    if role == "education":
        assert "trial class" in low
    if role == "sales":
        assert "are you interested" in low or "never re-ask interest" in low or "interest once" in low

    brain = _assemble_brain(script=script, language="en-IN", style=None)
    tokens = estimate_tokens(brain)
    assert tokens <= BUDGET_MAX_TOKENS, f"{biz_id} brain {tokens} > {BUDGET_MAX_TOKENS}"


def test_role_flow_sections_are_distinct():
    sales = flow_section("sales")
    appt = flow_section("appointment")
    edu = flow_section("education")
    support = flow_section("support")
    assert "NATURAL SALES PROGRESSION" in sales
    assert "APPOINTMENT FLOW" in appt
    assert "EDUCATION FLOW" in edu
    assert "SERVICE / SUPPORT FLOW" in support
    assert "are you interested" in sales.lower()
    assert "why they are calling" in appt.lower() or "do not ask why" in appt.lower()
    assert "trial-class" in edu.lower() or "trial class" in edu.lower()
    assert "latest intent" in support.lower()


@pytest.mark.parametrize("biz_id", list(AGENTIC_SCRIPTS.keys()))
def test_agentic_script_good_passes_bad_fails(biz_id: str):
    turns = AGENTIC_SCRIPTS[biz_id]
    assert len(turns) >= 5, f"{biz_id} needs a full multi-turn script"

    for turn in turns:
        hist = turn.get("history") or ""
        # Empty history still passes history="" so multi-turn reask path is exercised.
        good_fails = judge_turn(
            user=turn["user"],
            assistant=turn["good"],
            end_call={"should_end": False},
            expect=turn["expect"],
            history=hist,
        )
        bad_fails = judge_turn(
            user=turn["user"],
            assistant=turn["bad"],
            end_call={"should_end": False},
            expect=turn["expect"],
            history=hist,
        )
        assert not good_fails, (
            f"{biz_id}/{turn['id']} GOOD should pass ({turn['intent']}): {good_fails}\n"
            f"  assistant={turn['good']!r}"
        )
        assert bad_fails, (
            f"{biz_id}/{turn['id']} BAD should fail ({turn['intent']}):\n"
            f"  assistant={turn['bad']!r}"
        )


def test_critical_dental_does_not_reask_when_after_tomorrow_evening():
    fails = detect_reask_known_facts(
        history="I need to see a dentist. tooth pain. I can come tomorrow evening.",
        assistant="When would you like to come?",
    )
    assert any("schedule" in f for f in fails)


def test_critical_crm_does_not_reask_team_size_or_delay_price():
    assert judge_turn(
        user="How much does it cost?",
        assistant="Before I tell you the price, may I know your company size?",
        expect=("no_qualify", "no_question"),
        history="CRM for my 10-person sales team. lead tracking and follow-ups.",
    )
    assert not judge_turn(
        user="How much does it cost?",
        assistant="Plans start at five thousand rupees a month.",
        expect=("no_qualify", "no_question"),
        history="CRM for my 10-person sales team.",
    )
    size_fails = detect_reask_known_facts(
        history="I'm looking for a CRM for my 10-person sales team.",
        assistant="First, may I know your company size?",
    )
    assert any("team" in f or "company" in f for f in size_fails)


def test_critical_realty_no_are_you_interested_after_need():
    fails = detect_reask_known_facts(
        history="Hi, I'm actually looking for a plot around Hyderabad.",
        assistant="Are you interested in buying?",
    )
    assert any("interest" in f for f in fails)


def test_critical_autocare_keeps_vehicle_and_slot_on_addon():
    hist = (
        "strange noise when I brake. 2022 Hyundai Creta. "
        "Saturday morning around 10. book it for 10."
    )
    fails = detect_reask_known_facts(
        history=hist,
        assistant="Which car is it? When are you free?",
    )
    assert any("vehicle" in f for f in fails)
    assert any("schedule" in f for f in fails)
    assert not judge_turn(
        user="Actually, can you also check the brakes?",
        assistant=(
            "Updated — Saturday 10 AM for brake noise plus a full brake inspection "
            "on the 2022 Creta."
        ),
        expect=("at_most_one_question", "no_reask_known", "no_sell", "no_hangup"),
        history=hist,
    )


def test_critical_speakpro_answers_price_then_trial():
    assert judge_turn(
        user="How much is the intermediate course?",
        assistant="Before I share the fee, may I know your availability?",
        expect=("no_qualify", "no_question"),
        history="spoken English. evenings are better.",
    )
    assert not judge_turn(
        user="Can I attend a trial class first?",
        assistant="Yes — I'll book an evening trial class. Which day works?",
        expect=("at_most_one_question", "no_reask_known", "no_hangup"),
        history="improve English speaking. evenings better. intermediate course.",
    )
