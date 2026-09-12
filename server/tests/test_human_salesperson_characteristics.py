"""Fifteen human-salesperson characteristics + ultimate dump test (offline judge)."""
from __future__ import annotations

from server.eval.behavior_scenarios import AGENTIC_SCRIPTS
from server.prompts.conversation_policy import (
    LIVE_CALL_GUIDE_BODY,
    detect_reask_known_facts,
    flow_section,
    judge_turn,
)
from server.prompts.agent_voice_rules import live_realtime_output_rules, script_writer_system


ULTIMATE_DUMP = (
    "I'm looking for a plot around Hyderabad, preferably near Vanasthalipuram. "
    "My budget is around 25 lakhs and it's mainly for investment. "
    "I'm not in a huge hurry though, so I just want to understand what options are available."
)


def test_policy_embeds_human_sales_loop():
    flow = flow_section("sales").lower()
    guide = LIVE_CALL_GUIDE_BODY.lower()
    live = live_realtime_output_rules("en-IN").lower()
    writer = script_writer_system(language="en-IN", budget_tokens=3500).lower()
    for blob in (flow, guide, live, writer):
        assert "answer" in blob and ("first" in blob or "before" in blob)
        assert "never re-ask" in blob or "do not re-ask" in blob or "never re-ask" in flow
    assert "understand" in flow and "recommend" in flow
    assert "dense" in flow or "dump" in flow or "whole picture" in flow
    assert "send-details" in flow or "send-details" in guide


def test_1_understands_meaning_not_keywords():
    user = "I'm actually looking for something around 25 lakhs. Maybe a plot for investment."
    bad = "Are you looking for a plot?"
    good = "Got it — a plot around 25 lakhs for investment. Which area works best?"
    assert judge_turn(user=user, assistant=bad, expect=("no_qualify", "no_reask_known", "at_most_one_question"))
    assert not judge_turn(
        user=user,
        assistant=good,
        expect=("no_qualify", "no_reask_known", "at_most_one_question"),
    )


def test_2_answers_before_asking():
    bad = "May I know your budget first?"
    good = "Our plots start around 25 lakhs. If you're near that range I can narrow the options."
    assert judge_turn(
        user="How much are your plots?",
        assistant=bad,
        expect=("no_qualify", "no_question"),
    )
    assert not judge_turn(
        user="How much are your plots?",
        assistant=good,
        expect=("no_qualify", "no_question"),
    )


def test_3_every_question_has_a_reason_not_reask_budget():
    hist = "looking for a plot. My budget is around 25 lakhs."
    bad = "What is your budget?"
    good = (
        "Got it. Since you're looking mainly for investment, are you holding for a few years "
        "or thinking of building later?"
    )
    assert detect_reask_known_facts(history=hist, assistant=bad)
    assert not detect_reask_known_facts(history=hist + " mainly for investment.", assistant=good)


def test_4_does_not_repeat_location():
    user = "I'm looking for a plot around Vanasthalipuram."
    bad = "Sure. What's your preferred location?"
    good = "Vanasthalipuram — got it. What's your budget range?"
    assert judge_turn(
        user=user,
        assistant=bad,
        expect=("no_reask_known", "at_most_one_question"),
        history="",
    )
    assert not judge_turn(
        user=user,
        assistant=good,
        expect=("no_reask_known", "at_most_one_question"),
        history="",
    )


def test_5_combines_multiple_pieces_of_information():
    user = (
        "I'm looking for a 200-square-yard plot near Vanasthalipuram, "
        "around 30 lakhs, mainly for investment."
    )
    bad = "What size? What location? What's your budget? What's the purpose?"
    good = (
        "That gives me a clear picture. A plot in that range for investment makes sense — "
        "I'll narrow the suitable options."
    )
    assert judge_turn(
        user=user,
        assistant=bad,
        expect=("use_all_facts", "at_most_one_question", "no_reask_known"),
        history="",
    )
    assert not judge_turn(
        user=user,
        assistant=good,
        expect=("use_all_facts", "at_most_one_question", "no_reask_known"),
        history="",
    )


def test_6_reacts_to_what_was_just_said():
    user = "I'm not sure if I want to buy yet."
    bad = "What's your budget?"
    good = (
        "That's completely fine. Are you mainly comparing prices right now, "
        "or would you like to understand which options are available first?"
    )
    assert judge_turn(
        user=user,
        assistant=bad,
        expect=("react_hesitation", "at_most_one_question"),
    )
    assert not judge_turn(
        user=user,
        assistant=good,
        expect=("react_hesitation", "at_most_one_question"),
    )


def test_7_has_conversational_direction():
    user = "I'm looking for a villa."
    bad = "Are you interested? What is your budget? Which location?"
    good = (
        "Sure. We have villas starting around 80 lakhs. "
        "If that's within your range, I can narrow it by location."
    )
    assert judge_turn(
        user=user,
        assistant=bad,
        expect=("at_most_one_question", "no_reask_known"),
        history="",
    )
    assert not judge_turn(
        user=user,
        assistant=good,
        expect=("at_most_one_question", "no_reask_known"),
        history="",
    )


def test_8_recommends_instead_of_endlessly_qualifying():
    hist = "plot. budget 25 lakhs. investment. Vanasthalipuram."
    user = "What options do you have?"
    bad = "Before I share, may I know your budget and location?"
    good = (
        "Based on that, I'd suggest our plot options rather than villas. "
        "I can send the details and we can arrange a visit if something interests you."
    )
    assert judge_turn(
        user=user,
        assistant=bad,
        expect=("no_qualify", "no_reask_known", "at_most_one_question"),
        history=hist,
    )
    assert not judge_turn(
        user=user,
        assistant=good,
        expect=("no_qualify", "no_reask_known", "at_most_one_question"),
        history=hist,
    )


def test_9_knows_when_to_stop_selling():
    user = "Just send me the details. I'll check them later."
    bad = "Sure. May I know your budget? And when can I call you?"
    good = "Absolutely. I'll send you the details. Have a look when you're free."
    assert judge_turn(
        user=user,
        assistant=bad,
        expect=("honor_next_step", "at_most_one_question", "no_hangup"),
    )
    assert not judge_turn(
        user=user,
        assistant=good,
        expect=("honor_next_step", "at_most_one_question", "no_hangup"),
    )


def test_10_handles_objections_like_a_human():
    hist = "budget is around 25 lakhs"
    user = "That's too expensive."
    bad = "What is your budget?"
    good = (
        "I understand. If 25 lakhs is your comfortable range, "
        "I can show options closer to that budget."
    )
    assert judge_turn(
        user=user,
        assistant=bad,
        expect=("no_reask_known", "at_most_one_question", "no_hangup"),
        history=hist,
    )
    assert not judge_turn(
        user=user,
        assistant=good,
        expect=("no_reask_known", "at_most_one_question", "no_hangup"),
        history=hist,
    )


def test_11_handles_unexpected_conversation_jumps():
    hist = "How much is the villa?"
    user = "Actually forget the villa. Do you have plots?"
    bad = "Before we discuss plots, may I know why you're interested in a villa?"
    good = "Sure — we have plots from 25 lakhs. Want options near your preferred area?"
    assert judge_turn(
        user=user,
        assistant=bad,
        expect=("no_qualify", "at_most_one_question", "no_old_script"),
        history=hist,
    )
    assert not judge_turn(
        user=user,
        assistant=good,
        expect=("no_qualify", "at_most_one_question", "no_old_script"),
        history=hist,
    )


def test_12_detects_frustration():
    user = "I already told you my budget is 25 lakhs."
    bad = "Okay. And may I know your budget?"
    good = "Yes, you're right. You mentioned 25 lakhs. Let me work with that and narrow this down."
    assert judge_turn(
        user=user,
        assistant=bad,
        expect=("ack_frustration", "no_reask_known"),
        history="budget is around 25 lakhs",
    )
    assert not judge_turn(
        user=user,
        assistant=good,
        expect=("ack_frustration", "no_reask_known"),
        history="budget is around 25 lakhs",
    )


def test_13_uses_short_spoken_sentences():
    user = "What plot options do you have?"
    bad = (
        "We offer a comprehensive range of premium residential plots strategically located "
        "across multiple emerging areas with excellent connectivity and strong appreciation potential."
    )
    good = "We do have a few plot options. If you're around the 25-lakh range, I can narrow those down."
    assert judge_turn(user=user, assistant=bad, expect=("spoken_short", "no_question"))
    assert not judge_turn(user=user, assistant=good, expect=("spoken_short", "no_question"))


def test_14_does_not_use_same_robot_opener():
    assert judge_turn(
        user="Tell me more.",
        assistant="Sure! Absolutely! We have great plots.",
        expect=("not_robot",),
    )
    assert not judge_turn(
        user="Tell me more.",
        assistant="Got it. Plots start around 25 lakhs — want me to narrow by area?",
        expect=("not_robot", "at_most_one_question"),
    )


def test_15_sounds_like_its_listening_parents_villa():
    user = (
        "I'm looking for something for my parents. They'd probably prefer a villa because "
        "they don't want to deal with construction. My budget is around 80 lakhs, and I'd "
        "prefer somewhere not too far from the city."
    )
    bad = "Are you interested? What is your budget? Which location? Is it for investment?"
    good = (
        "That makes sense. A ready villa would suit better than a plot if you want to skip "
        "construction. I can narrow villas around 80 lakhs closer to the city."
    )
    assert judge_turn(
        user=user,
        assistant=bad,
        expect=("use_all_facts", "at_most_one_question", "no_reask_known"),
        history="",
    )
    assert not judge_turn(
        user=user,
        assistant=good,
        expect=("use_all_facts", "at_most_one_question", "no_reask_known"),
        history="",
    )


def test_ultimate_dump_bad_checklist_fails_natural_passes():
    bad = (
        "Are you interested in plots? What is your budget? Which location are you interested in? "
        "Is it for investment? When are you planning to buy?"
    )
    good = (
        "Got it. So you're looking around Vanasthalipuram, around 25 lakhs, mainly as an investment. "
        "Since you're not in a hurry, I can first give you a couple of options that fit that range."
    )
    assert judge_turn(
        user=ULTIMATE_DUMP,
        assistant=bad,
        expect=("use_all_facts", "at_most_one_question", "no_reask_known", "no_qualify"),
        history="",
    )
    assert not judge_turn(
        user=ULTIMATE_DUMP,
        assistant=good,
        expect=("use_all_facts", "at_most_one_question", "no_reask_known", "no_qualify"),
        history="",
    )


def test_five_business_scripts_still_pass_good_and_fail_bad():
    for biz_id, turns in AGENTIC_SCRIPTS.items():
        for turn in turns:
            hist = turn.get("history") or ""
            assert not judge_turn(
                user=turn["user"],
                assistant=turn["good"],
                end_call={"should_end": False},
                expect=turn["expect"],
                history=hist,
            ), f"{biz_id}/{turn['id']} good"
            assert judge_turn(
                user=turn["user"],
                assistant=turn["bad"],
                end_call={"should_end": False},
                expect=turn["expect"],
                history=hist,
            ), f"{biz_id}/{turn['id']} bad"


def test_adversarial_subtle_reasks_still_fail():
    """Tough near-miss phrasings that still re-ask known facts."""
    cases = [
        (
            "looking for a plot around Vanasthalipuram. budget 25 lakhs. investment.",
            "What options do you have?",
            "Just to confirm, which location are you preferring?",
            ("no_reask_known", "no_qualify", "at_most_one_question"),
        ),
        (
            "CRM for my 10-person sales team. lead tracking.",
            "How much does it cost?",
            "Happy to share pricing — first, how many people are on your team?",
            ("no_qualify", "no_reask_known", "no_question"),
        ),
        (
            "dentist. tooth pain. I can come tomorrow evening.",
            "Around 6 would be good.",
            "Great. When would you like to come in?",
            ("no_reask_known", "no_sell", "at_most_one_question"),
        ),
        (
            "2022 Hyundai Creta. Saturday morning. book it for 10.",
            "Actually, can you also check the brakes?",
            "Got it. Which car is this for, and when are you free?",
            ("no_reask_known", "no_sell", "at_most_one_question"),
        ),
        (
            "improve English speaking. evenings are better.",
            "How much is the intermediate course?",
            "Before I share the fee, when are you available?",
            ("no_qualify", "no_question", "no_reask_known"),
        ),
    ]
    for hist, user, bad, expect in cases:
        fails = judge_turn(
            user=user,
            assistant=bad,
            expect=expect,
            history=hist,
            end_call={"should_end": False},
        )
        assert fails, f"expected fail for bad={bad!r} hist={hist!r}"


def test_live_turn_discipline_wraps_transcript_for_llm():
    from server.agent.instruction_builder import LIVE_TURN_DISCIPLINE, build_live_input

    msgs = build_live_input(
        compiled_brain_text="brain",
        history=[],
        transcript=ULTIMATE_DUMP,
    )
    text = msgs[-1]["content"][0]["text"]
    assert text.startswith(LIVE_TURN_DISCIPLINE)
    assert ULTIMATE_DUMP in text
    assert "Dense dump" in text or "dumped several facts" in text
    assert "never re-ask" in text


def test_compiled_static_rules_version_and_sales_loop():
    from server.brain.sections import STATIC_OUTPUT_RULES, STATIC_OUTPUT_RULES_VERSION

    assert STATIC_OUTPUT_RULES_VERSION == "sr_v27"
    low = STATIC_OUTPUT_RULES.lower()
    assert "answer" in low and "first" in low
    assert "dense dump" in low
    assert "frustration" in low or "already told" in low
    assert "sales loop" in low or "understand" in low
