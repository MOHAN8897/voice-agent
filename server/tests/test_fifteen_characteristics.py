"""Critical tests for all 15 sales conversation characteristics.

Tests every characteristic from the human-salesperson evaluation checklist
across five multi-business scenarios:
  1. Priya Estates — plots/villas
  2. SmileCare Dental — appointments
  3. SalesFlow CRM — SaaS
  4. AutoCare Motors — service
  5. SpeakPro Academy — education

Each test validates that good responses pass and bad responses fail the
offline judge (judge_turn + detect_reask_known_facts).
"""
from __future__ import annotations

import pytest

from server.eval.behavior_scenarios import (
    CHAR1_MEANING,
    CHAR2_ANSWER_FIRST,
    CHAR3_USEFUL_QUESTIONS,
    CHAR5_DENSE_DUMP,
    CHAR6_REACT_TO_EMOTION,
    CHAR7_DIRECTION,
    CHAR8_RECOMMEND,
    CHAR9_STOP_SELLING,
    CHAR10_OBJECTIONS,
    CHAR11_CONVERSATION_JUMP,
    CHAR12_FRUSTRATION,
    CHAR13_SHORT_SPOKEN,
    CHAR14_VARIED_ACKS,
    CHAR15_WHOLE_THOUGHT,
)
from server.prompts.conversation_policy import (
    detect_reask_known_facts,
    judge_turn,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helper: run good/bad pair through judge_turn
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _assert_good_passes_bad_fails(turn: dict) -> None:
    hist = turn.get("history") or ""
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
        f"{turn['id']} GOOD should pass ({turn['intent']}): {good_fails}\n"
        f"  good={turn['good']!r}"
    )
    assert bad_fails, (
        f"{turn['id']} BAD should fail ({turn['intent']}):\n"
        f"  bad={turn['bad']!r}"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Characteristic 1: Understands meaning, not just keywords
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.mark.parametrize("turn", CHAR1_MEANING, ids=lambda t: t["id"])
def test_c1_understands_meaning_not_keywords(turn):
    _assert_good_passes_bad_fails(turn)


def test_c1_plot_implied_from_investment_statement():
    """After 'plot for investment', agent must not ask 'are you looking for a plot?'"""
    fails = detect_reask_known_facts(
        history="I'm actually looking for something around 25 lakhs. Maybe a plot for investment.",
        assistant="Are you looking for a plot?",
    )
    assert any("interest" in f for f in fails)


def test_c1_dental_need_clear_from_tooth_pain():
    """After 'dentist + tooth pain', asking 'what's the issue?' is a reask fail."""
    fails = detect_reask_known_facts(
        history="I need to see a dentist. I've been having tooth pain since yesterday.",
        assistant="What's the issue? What's bothering you?",
    )
    assert any("issue" in f or "problem" in f for f in fails)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Characteristic 2: Answers before asking
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.mark.parametrize("turn", CHAR2_ANSWER_FIRST, ids=lambda t: t["id"])
def test_c2_answers_before_asking(turn):
    _assert_good_passes_bad_fails(turn)


def test_c2_may_i_know_budget_is_qualify():
    """'May I know your budget first?' before answering a price question is a qualify fail."""
    fails = judge_turn(
        user="How much are your plots?",
        assistant="May I know your budget first?",
        expect=("no_qualify",),
    )
    assert fails, "should fail no_qualify"


def test_c2_before_i_tell_is_qualify():
    """'Before I tell you the price...' is a qualify-before-answering fail."""
    fails = judge_turn(
        user="How much does it cost?",
        assistant="Before I tell you the price, may I know your company size?",
        expect=("no_qualify",),
        history="CRM for my 10-person sales team.",
    )
    assert fails, "should fail for qualify-before-answer"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Characteristic 3: Every question has a reason
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.mark.parametrize("turn", CHAR3_USEFUL_QUESTIONS, ids=lambda t: t["id"])
def test_c3_every_question_has_a_reason(turn):
    _assert_good_passes_bad_fails(turn)


def test_c3_budget_reask_after_already_stated():
    """Asking 'What is your budget?' after customer said 25 lakhs is a re-ask fail."""
    fails = detect_reask_known_facts(
        history="I'm looking for a plot around Hyderabad. My budget is around 25 lakhs.",
        assistant="What is your budget?",
    )
    assert any("budget" in f for f in fails)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Characteristic 4: Doesn't repeat information (covered by no_reask_known)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_c4_reask_location_vanasthalipuram():
    """After 'looking around Vanasthalipuram', agent must not ask 'preferred location?'"""
    fails = detect_reask_known_facts(
        history="I'm looking for a plot around Vanasthalipuram.",
        assistant="What's your preferred location?",
    )
    assert any("location" in f or "area" in f for f in fails)


def test_c4_reask_car_model_after_stated():
    """After '2022 Hyundai Creta', agent must not ask 'which car?'"""
    fails = detect_reask_known_facts(
        history="My car is making a strange noise when I brake. It's a 2022 Hyundai Creta.",
        assistant="Which car is it?",
    )
    assert any("vehicle" in f for f in fails)


def test_c4_reask_time_after_tomorrow_evening():
    """After 'I can come tomorrow evening', asking 'when do you want to come?' is a fail."""
    fails = detect_reask_known_facts(
        history="I need to see a dentist. tooth pain. I can come tomorrow evening.",
        assistant="When would you like to come?",
    )
    assert any("schedule" in f for f in fails)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Characteristic 5: Combines multiple pieces of information (dense dump)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.mark.parametrize("turn", CHAR5_DENSE_DUMP, ids=lambda t: t["id"])
def test_c5_dense_dump_not_unpacked(turn):
    _assert_good_passes_bad_fails(turn)


def test_c5_multiple_questions_after_dense_dump_is_fail():
    """If customer gives 4 facts in one turn, asking 2+ questions back is a checklist fail."""
    fails = judge_turn(
        user="I need a CRM for my 10-person team, mainly for lead tracking, demo this week.",
        assistant="How many people are on your team? What features do you need? When can you meet?",
        expect=("use_all_facts",),
    )
    assert any("multiple" in f.lower() or "checklist" in f.lower() for f in fails)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Characteristic 6: Reacts to what was JUST said (emotional/intent state)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.mark.parametrize("turn", CHAR6_REACT_TO_EMOTION, ids=lambda t: t["id"])
def test_c6_reacts_to_emotion(turn):
    _assert_good_passes_bad_fails(turn)


def test_c6_hesitation_not_sure_must_not_jump_to_qualify():
    """'I'm not sure if I want to buy' → jumping to budget is a react_hesitation fail."""
    fails = judge_turn(
        user="I'm not sure if I want to buy yet.",
        assistant="What's your budget?",
        expect=("react_hesitation",),
        history="looking for a plot.",
    )
    assert fails, "should fail react_hesitation"


def test_c6_too_expensive_must_not_reask_budget():
    """'That's too expensive' → 'What is your budget?' is qualify fail on known data."""
    fails = judge_turn(
        user="That's too expensive.",
        assistant="What is your budget?",
        expect=("no_qualify",),
        history="looking for a plot. budget 25 lakhs.",
    )
    assert fails


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Characteristic 7: Has conversational direction
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.mark.parametrize("turn", CHAR7_DIRECTION, ids=lambda t: t["id"])
def test_c7_has_conversational_direction(turn):
    _assert_good_passes_bad_fails(turn)


def test_c7_multi_question_is_no_direction():
    """Three questions in one turn means no direction — just interrogation."""
    fails = judge_turn(
        user="I'm looking for a villa.",
        assistant="Are you interested in buying? What's your budget? Which location?",
        expect=("at_most_one_question",),
    )
    assert any("more than one" in f for f in fails)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Characteristic 8: Recommends instead of endlessly qualifying
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.mark.parametrize("turn", CHAR8_RECOMMEND, ids=lambda t: t["id"])
def test_c8_recommends_when_enough_known(turn):
    _assert_good_passes_bad_fails(turn)


def test_c8_reask_after_all_facts_known():
    """After plot+25L+investment+Vanasthalipuram, asking budget/location is a double fail."""
    fails = judge_turn(
        user="What options do you have?",
        assistant="Before I share options, may I know your budget and location?",
        expect=("no_qualify", "no_reask_known"),
        history="plot. 25 lakhs. investment. Vanasthalipuram side.",
    )
    assert fails


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Characteristic 9: Knows when to stop selling
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.mark.parametrize("turn", CHAR9_STOP_SELLING, ids=lambda t: t["id"])
def test_c9_stops_selling_when_customer_says_stop(turn):
    _assert_good_passes_bad_fails(turn)


def test_c9_send_details_then_qualify_is_fail():
    """After 'just send me the details', asking budget/location is interrogation fail."""
    fails = judge_turn(
        user="Just send me the details. I'll check them later.",
        assistant="Sure. May I know your budget? And when can I call you?",
        expect=("honor_next_step",),
        history="plot Hyderabad. 25 lakhs. Vanasthalipuram.",
    )
    assert fails


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Characteristic 10: Handles objections like a human
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.mark.parametrize("turn", CHAR10_OBJECTIONS, ids=lambda t: t["id"])
def test_c10_handles_objections_humanely(turn):
    _assert_good_passes_bad_fails(turn)


def test_c10_too_expensive_budget_reask_is_fail():
    """After 'too expensive' + known budget, re-asking budget is double fail."""
    fails = judge_turn(
        user="That's too expensive.",
        assistant="What is your budget?",
        expect=("no_qualify",),
        history="looking for a plot. 25 lakhs.",
    )
    assert fails


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Characteristic 11: Handles unexpected conversation jumps
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.mark.parametrize("turn", CHAR11_CONVERSATION_JUMP, ids=lambda t: t["id"])
def test_c11_handles_conversation_jumps(turn):
    _assert_good_passes_bad_fails(turn)


def test_c11_before_we_discuss_is_fail():
    """'Before we discuss plots' after villa→plot switch is a qualify fail."""
    fails = judge_turn(
        user="Actually forget the villa. Do you have plots?",
        assistant="Before we discuss plots, may I know why you're interested in a villa?",
        expect=("at_most_one_question",),
        history="looking for a villa. budget around 80 lakhs.",
    )
    # Should also trigger the 'before we discuss' qualify pattern.
    q_fails = judge_turn(
        user="Actually forget the villa. Do you have plots?",
        assistant="Before we discuss plots, may I know why you're interested in a villa?",
        expect=("no_qualify",),
        history="looking for a villa.",
    )
    assert fails or q_fails, "villa→plot switch: 'before we discuss' must fail"


def test_c11_addon_does_not_restart():
    """Adding 'also check brakes' must not restart the conversation."""
    hist = "strange noise when I brake. 2022 Hyundai Creta. Saturday around 10. book it for 10."
    reask = detect_reask_known_facts(
        history=hist,
        assistant="Sorry, let's start over. What's wrong with your car? Which car is it?",
    )
    assert len(reask) >= 2, "should fail for re-asking both vehicle and issue"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Characteristic 12: Detects frustration
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.mark.parametrize("turn", CHAR12_FRUSTRATION, ids=lambda t: t["id"])
def test_c12_detects_and_handles_frustration(turn):
    _assert_good_passes_bad_fails(turn)


def test_c12_already_told_budget_must_ack():
    """'I already told you my budget is 25 lakhs' → agent must acknowledge."""
    fails = judge_turn(
        user="I already told you my budget is 25 lakhs.",
        assistant="Okay. And may I know your budget?",
        expect=("ack_frustration",),
        history="looking for a plot. budget 25 lakhs.",
    )
    assert any("already" in f for f in fails)


def test_c12_frustrated_no_pitch():
    """Frustration → site visit pitch is a hard fail."""
    fails = judge_turn(
        user="This is taking too long. I'm getting frustrated.",
        assistant="I completely understand how you feel. Would you like to arrange a site visit?",
        expect=("short", "no_qualify"),
    )
    # Should catch: robot phrasing + pitch after frustration
    assert fails


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Characteristic 13: Uses short spoken sentences
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.mark.parametrize("turn", CHAR13_SHORT_SPOKEN, ids=lambda t: t["id"])
def test_c13_short_spoken_sentences(turn):
    _assert_good_passes_bad_fails(turn)


def test_c13_brochure_detected_comprehensive_range():
    """'comprehensive range of premium residential plots' is brochure copy."""
    fails = judge_turn(
        user="What do you offer?",
        assistant=(
            "We offer a comprehensive range of premium residential plots "
            "strategically located across multiple emerging areas with "
            "excellent connectivity and strong appreciation potential."
        ),
        expect=("spoken_short",),
    )
    assert any("brochure" in f for f in fails)


def test_c13_short_reply_passes():
    """A concise spoken-style answer passes the spoken_short check."""
    fails = judge_turn(
        user="What do you offer?",
        assistant="We have plots and villas around Hyderabad. Want me to narrow those down?",
        expect=("spoken_short",),
    )
    assert not fails


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Characteristic 14: Varied acknowledgments
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.mark.parametrize("turn", CHAR14_VARIED_ACKS, ids=lambda t: t["id"])
def test_c14_varied_acknowledgments(turn):
    _assert_good_passes_bad_fails(turn)


def test_c14_sure_absolutely_is_robot():
    """'Sure, absolutely.' at the start is robot phrasing."""
    fails = judge_turn(
        user="Okay.",
        assistant="Sure! Absolutely! May I know your preferred location?",
        expect=("not_robot",),
    )
    assert any("robot" in f for f in fails)


def test_c14_i_completely_understand_is_robot():
    """'I completely understand' is robot phrasing."""
    fails = judge_turn(
        user="This is expensive.",
        assistant="I completely understand how you feel. Let me show you options.",
        expect=("not_robot",),
    )
    assert any("robot" in f for f in fails)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Characteristic 15: Sounds like it's actually listening (whole-thought)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.mark.parametrize("turn", CHAR15_WHOLE_THOUGHT, ids=lambda t: t["id"])
def test_c15_whole_thought_response(turn):
    _assert_good_passes_bad_fails(turn)


def test_c15_ultimate_test_bad_agent_checklist():
    """The 'ultimate test' bad agent fires 5 questions — must fail use_all_facts."""
    fails = judge_turn(
        user=(
            "I'm looking for a plot around Hyderabad, preferably near Vanasthalipuram. "
            "My budget is around 25 lakhs and it's mainly for investment. "
            "I'm not in a huge hurry though, so I just want to understand what options are available."
        ),
        assistant=(
            "Are you interested in plots? What is your budget? "
            "Which location are you interested in? Is it for investment? "
            "When are you planning to buy?"
        ),
        expect=("use_all_facts",),
    )
    assert fails, "5-question checklist after dense dump must be caught"


def test_c15_natural_agent_passes():
    """The 'ultimate test' natural agent synthesizes all facts — must pass."""
    fails = judge_turn(
        user=(
            "I'm looking for a plot around Hyderabad, preferably near Vanasthalipuram. "
            "My budget is around 25 lakhs and it's mainly for investment. "
            "I'm not in a huge hurry though, so I just want to understand what options are available."
        ),
        assistant=(
            "Got it. So you're looking around Vanasthalipuram, around 25 lakhs, mainly as an investment. "
            "Since you're not in a hurry, I can first give you a couple of options that fit that range."
        ),
        expect=("use_all_facts", "at_most_one_question", "spoken_short"),
    )
    assert not fails, f"Natural whole-thought response should pass: {fails}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Cross-cutting: Combined multi-fact + objection + frustration
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_cross_send_details_after_dense_dump():
    """After giving all facts and asking for details, agent must not interrogate."""
    hist = "plot. 25 lakhs. investment. Vanasthalipuram. What options do you have?"
    fails = judge_turn(
        user="Okay, can you send me the details on WhatsApp?",
        assistant="Sure. May I know your budget? And when can I call you?",
        expect=("honor_next_step", "no_reask_known"),
        history=hist,
    )
    assert fails


def test_cross_autocare_full_flow_no_restart():
    """After full context + booking + add-on, restarting is a critical fail."""
    hist = (
        "strange noise when I brake. 2022 Hyundai Creta. "
        "Saturday morning around 10. book it for 10."
    )
    # Add-on: also check brakes
    good = judge_turn(
        user="Actually, can you also check the brakes?",
        assistant=(
            "Updated — Saturday 10 AM for brake noise plus a full brake inspection "
            "on the 2022 Creta."
        ),
        expect=("at_most_one_question", "no_reask_known", "no_sell", "no_hangup"),
        history=hist,
    )
    assert not good, "natural add-on handling should pass"

    bad = judge_turn(
        user="Actually, can you also check the brakes?",
        assistant="Let's start over. What's wrong with your car?",
        expect=("no_reask_known",),
        history=hist,
    )
    assert bad, "restarting conversation after add-on must fail"


def test_cross_speakpro_trial_class_is_the_close():
    """Trial class request is the natural close — don't restart pitching."""
    fails = judge_turn(
        user="Can I attend a trial class first?",
        assistant="First tell me your goal again. Are you interested?",
        expect=("at_most_one_question", "no_reask_known"),
        history="improve English speaking. evenings. intermediate course. I think that could work.",
    )
    assert fails


def test_cross_crm_demo_request_honor():
    """Demo request is a buying signal — honor it, don't re-qualify."""
    fails = judge_turn(
        user="Can I see a demo?",
        assistant="How many people are on your team?",
        expect=("at_most_one_question", "no_reask_known"),
        history="10-person team. lead tracking. That sounds reasonable.",
    )
    assert fails
