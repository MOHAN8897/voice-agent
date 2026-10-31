"""Deterministic reply guards: invented business facts, canned audio lines, echo and repeats."""
from __future__ import annotations

import pytest

from server.call import reply_guard
from server.call.reply_guard import (
    audio_issue_evidence,
    caller_turn_since_agent,
    gate_canned_audio_lines,
    guard_business_claims,
    guard_repeated_asks,
    guard_reply,
    is_acknowledgement,
    join_caller_fragments,
    strip_filler_echo,
    unknown_fact_line,
)
from server.prompts.agent_voice_rules import SLOW_DOWN_FALLBACK, UNCLEAR_FALLBACK

BRAIN = """--- SAFETY ---
- Never invent prices, availability, or policies.
--- SPOKEN LANGUAGE (te-IN) ---
Style anchors, not extra facts: ‘ఆ విషయం నాకు తెలియదు.’ for a missing fact; ‘మీకు ఏ details కావాలి?’ only when their request is unclear.
--- CALLING SCRIPT ---
--- AGENT IDENTITY ---
You are Meera, representing subhasri sells.
--- COMPANY & OFFER ---
Digital products include icards and visiting cards
Price is 25 rs per visiting card
Digital icards and visiting cards are delivered through the post
--- UNKNOWN INFORMATION ---
Do not invent callbacks, additional pricing, discounts, policies, links, or capabilities.
--- GUARDRAILS ---
- Never claim discounts, guarantees or a company size that the facts do not state.
"""


# --- 1. business facts the agent was not given ---------------------------------------------

@pytest.mark.parametrize("reply, category", [
    ("మేము చిన్న business, రోడ్ సైడ్ బిజినెస్.", "size_or_kind"),
    ("We are a small family business.", "size_or_kind"),
    ("हम एक छोटी कंपनी हैं।", "size_or_kind"),
    ("நாங்க ஒரு பெரிய கம்பெனி.", "size_or_kind"),
    ("ನಾವು ದೊಡ್ಡ ಕಂಪನಿ.", "size_or_kind"),
    ("We have 50 employees.", "staff"),
    ("మా దగ్గర 20 మంది ఎంప్లాయిస్ ఉన్నారు.", "staff"),
    ("We have been running for 10 years.", "years_running"),
    ("हमारी 5 शाखाएं हैं।", "branches"),
    ("Our office is in Hyderabad.", "location"),
    ("Bulk order మీద 10% డిస్కౌంట్ ఉంటుంది.", "discount_or_offer"),
    ("You get free delivery on this order.", "discount_or_offer"),
    ("ఈ cards కి గ్యారంటీ ఉంటుంది.", "guarantee"),
])
def test_unsupported_business_claim_is_replaced_by_the_unknown_line(reply, category):
    guarded, flagged = guard_business_claims(reply, brain=BRAIN, language="te-IN")
    assert flagged == [category]
    assert guarded == "ఆ విషయం నాకు తెలియదు."


def test_only_the_invented_sentence_is_replaced():
    reply = "మేము చిన్న business, రోడ్ సైడ్ బిజినెస్. Visiting cards ఒక్కొక్కటి ₹25 ఉంటాయి."
    guarded, flagged = guard_business_claims(reply, brain=BRAIN, language="te-IN")
    assert flagged == ["size_or_kind"]
    assert guarded == "ఆ విషయం నాకు తెలియదు. Visiting cards ఒక్కొక్కటి ₹25 ఉంటాయి."


@pytest.mark.parametrize("reply", [
    "ఆ విషయం నాకు తెలియదు. ప్రస్తుతానికి bulk discounts గురించి information అందుబాటులో లేదు.",
    "I'm sorry, discount details are not available right now.",
    "మీకు discount కావాలా?",
    "మా team దాన్ని confirm చేస్తారు.",
    "Our staff will call you back.",
    "మీరు తర్వాత free ఉన్నప్పుడు call చేయమని చెప్పండి.",
    "మా visiting cards ఒక్కొక్కటి ₹25 ఉంటాయి.",
    "Our branch team will confirm the order.",
])
def test_no_flag_on_unknowns_questions_or_ordinary_lines(reply):
    assert guard_business_claims(reply, brain=BRAIN, language="te-IN") == (reply, [])


def test_claims_the_brain_supports_are_kept():
    brain = BRAIN.replace(
        "--- UNKNOWN INFORMATION ---",
        "We are a small family-run business established in 1998 with 12 employees and 3 branches.\n"
        "Bulk orders above 500 cards get a 10% discount. Our office is located in Vijayawada.\n"
        "--- UNKNOWN INFORMATION ---",
    )
    for reply in (
        "మేము చిన్న business.", "We have 12 employees.", "We have been running for 25 years.",
        "Bulk order మీద 10% డిస్కౌంట్ ఉంటుంది.", "Our office is in Vijayawada.", "We have 3 branches.",
    ):
        assert guard_business_claims(reply, brain=brain, language="te-IN") == (reply, []), reply


def test_platform_guardrail_words_are_not_business_facts():
    # "Never claim discounts..." sits in GUARDRAILS / UNKNOWN INFORMATION: it supports nothing.
    _, flagged = guard_business_claims("You will get a discount.", brain=BRAIN, language="en-IN")
    assert flagged == ["discount_or_offer"]


def test_unknown_line_falls_back_to_the_platform_default_per_language():
    assert unknown_fact_line(BRAIN, "hi-IN") == "ఆ విషయం నాకు తెలియదు."
    assert unknown_fact_line("--- COMPANY & OFFER ---\nfacts", "hi-IN") == "इसकी जानकारी मेरे पास नहीं है।"
    assert unknown_fact_line("", "ta-IN") == "அந்த விவரம் எனக்குத் தெரியலைங்க."


# --- 2. caller fragments since the agent's last turn ---------------------------------------

CALL_FRAGMENTS = [
    "ఓకే నాకు ఒక 100 విజిటింగ్ కార్స్ కావాలి.",
    "ఓకే నాకు ఒక 100 విజిటింగ్ కార్స్ కావాలి. ఇది చెప్పండి మీ",
    "ఇది చెప్పండి, మీ మేనేజర్ కి చెప్పండి నా కాల్ బ్యాక్ చేయమని.",
    "ఇది చెప్పండి, మీ మేనేజర్ కి చెప్పండి నా కాల్ బ్యాక్ చేయమని. ఆ పేరు.",
    "నా పేరు Saikiran",
]


def test_overlapping_finals_join_into_one_utterance_without_duplicates():
    joined = join_caller_fragments(CALL_FRAGMENTS)
    assert joined.count("100") == 1
    assert joined.count("మేనేజర్") == 1
    assert joined.count("ఇది చెప్పండి") == 1
    assert joined.startswith("ఓకే నాకు ఒక 100")
    assert joined.endswith("నా పేరు Saikiran")


def test_caller_turn_uses_only_fragments_after_the_last_agent_reply():
    history = [
        {"role": "user", "content": "అవును"},
        {"role": "assistant", "content": "సరే. మీకు ఎన్ని visiting cards కావాలో చెప్తారా?"},
        *({"role": "user", "content": f} for f in CALL_FRAGMENTS[:-1]),
    ]
    joined = caller_turn_since_agent(history, CALL_FRAGMENTS[-1])
    assert "అవును" not in joined
    assert "100" in joined and "Saikiran" in joined
    assert caller_turn_since_agent([{"role": "assistant", "content": "hi"}], "hello") == "hello"


# --- 4. slow-down and unclear-audio lines --------------------------------------------------

@pytest.mark.parametrize("language, caller", [
    ("te-IN", "ఓకే ఓకే."), ("te-IN", "అవును"), ("hi-IN", "हाँ"), ("hi-IN", "ठीक है"),
    ("ta-IN", "சரி"), ("kn-IN", "ಹೌದು"), ("ml-IN", "ശരി"), ("mr-IN", "हो"), ("bn-IN", "হ্যাঁ"),
    ("gu-IN", "હા"), ("pa-IN", "ਹਾਂ ਜੀ"), ("en-IN", "ok, hmm"),
])
def test_an_acknowledgement_never_earns_the_slow_down_or_unclear_line(language, caller):
    assert is_acknowledgement(caller)
    assert audio_issue_evidence(caller, server_requested=True) is False
    for canned in (SLOW_DOWN_FALLBACK[language], UNCLEAR_FALLBACK[language]):
        reply = f"{canned} Visiting cards ₹25."
        assert gate_canned_audio_lines(reply, caller=caller, language=language, evidence=False) == "Visiting cards ₹25."


def test_canned_line_alone_after_an_acknowledgement_becomes_an_acknowledgement():
    out = gate_canned_audio_lines("కొంచెం నెమ్మదిగా చెప్తారా?", caller="ఓకే", language="te-IN", evidence=False)
    assert out == "సరే."


def test_canned_line_is_kept_with_evidence():
    reply = UNCLEAR_FALLBACK["hi-IN"]
    assert audio_issue_evidence("") is True
    assert audio_issue_evidence("��") is True
    assert audio_issue_evidence("a b c d") is True
    assert audio_issue_evidence("मुझे सौ कार्ड चाहिए", server_requested=True) is True

    class Ctx:
        last_stt_confidence = 0.3

    assert audio_issue_evidence("मुझे सौ कार्ड चाहिए", Ctx()) is True
    assert audio_issue_evidence("मुझे सौ कार्ड चाहिए") is False
    assert gate_canned_audio_lines(reply, caller="", language="hi-IN", evidence=True) == reply


# --- 5. repetition and repeated asks -------------------------------------------------------

def test_second_ask_after_a_bare_yes_invites_and_third_offers_later():
    state: dict = {}
    first, _ = guard_repeated_asks("మీ delivery address చెప్తారా?", caller="నా పేరు Saikiran", language="te-IN", state=state)
    assert first == "మీ delivery address చెప్తారా?"
    second, reasons = guard_repeated_asks("సరే. మీ delivery address చెప్తారా, order confirm చేస్తాను.",
                                          caller="యా అండి ఓకే", language="te-IN", state=state)
    assert reasons == ["repeat_ask:address"] and second == "సరే, చెప్పండి."
    third, reasons = guard_repeated_asks("మీ delivery address చెప్పండి, order confirm చేస్తాను.",
                                         caller="అవును అవునండి", language="te-IN", state=state)
    assert reasons == ["offer_later:address"] and third == "పర్వాలేదు, అది తర్వాత కూడా చెప్పొచ్చు."
    fourth, reasons = guard_repeated_asks(
        "సరే, మీ delivery address చెప్పండి. Payment కోసం cards లేదా cash on delivery తీసుకోవచ్చు.",
        caller="యా ఓకే అండి థ్యాంక్ యూ", language="te-IN", state=state)
    assert reasons == ["deferred_slot:address"]
    assert "address" not in fourth and "Payment" in fourth


@pytest.mark.parametrize("language, ask, ack, go_ahead", [
    ("hi-IN", "आपको कितने कार्ड चाहिए, बताइए?", "हाँ जी", "जी, बताइए।"),
    ("ta-IN", "உங்களுக்கு எத்தனை cards வேணும், சொல்லுங்க?", "சரி", "சரி, சொல்லுங்க."),
    ("en-IN", "How many cards do you need?", "yeah okay", "Sure, go ahead."),
])
def test_repeated_ask_rewrite_in_other_languages(language, ask, ack, go_ahead):
    state: dict = {}
    guard_repeated_asks(ask, caller="hello there", language=language, state=state)
    out, reasons = guard_repeated_asks(ask, caller=ack, language=language, state=state)
    assert (out, reasons) == (go_ahead, ["repeat_ask:quantity"])


def test_a_substantive_reply_resets_the_ask_count():
    state: dict = {}
    guard_repeated_asks("How many cards do you need?", caller="hi", language="en-IN", state=state)
    out, reasons = guard_repeated_asks("How many cards do you need?", caller="what is the price first",
                                       language="en-IN", state=state)
    assert reasons == [] and out == "How many cards do you need?"


def test_a_known_slot_is_not_asked_again_but_may_be_confirmed():
    out, reasons = guard_repeated_asks(
        "సరే Saikiran గారు, ఒక్కో card ₹25. మీకు ఎన్ని కావాలో చెప్తారా?", caller="ఓకే",
        language="te-IN", state={}, known={"quantity": "100"})
    assert reasons == ["known_slot:quantity"] and "ఎన్ని" not in out
    confirm = "500 cards కదా, confirm చేస్తారా?"
    assert guard_repeated_asks(confirm, caller="ఓకే", language="te-IN", state={}, known={"quantity": "500"}) == (confirm, [])


def test_near_identical_reply_to_an_acknowledgement_is_not_repeated():
    history = [
        {"role": "assistant", "content": "ఆ విషయం నాకు తెలియదు. ప్రస్తుతానికి bulk discounts గురించి information అందుబాటులో లేదు."},
    ]
    out, reasons = guard_reply("ప్రస్తుతం bulk discounts గురించి information అందుబాటులో లేదు.", caller="ఓకే ఓకే",
                               language="te-IN", history=history, state={})
    assert reasons == ["near_repeat"] and out == "సరే."


def test_a_repeat_request_or_a_new_question_may_get_the_same_answer():
    history = [{"role": "assistant", "content": "Visiting cards cost 25 rupees each."}]
    for caller in ("can you repeat that?", "how much is one card?"):
        out, reasons = guard_reply("Visiting cards cost 25 rupees each.", caller=caller,
                                   language="en-IN", history=history, state={})
        assert reasons == [], caller


# --- 6. filler echo ------------------------------------------------------------------------

@pytest.mark.parametrize("caller, reply, expected", [
    ("పర్లేదండి పర్లేదండి ఓకే అండి పర్లేదు", "పర్లేదండి. మీకు ఎన్ని cards కావాలో చెప్తారా?", "మీకు ఎన్ని cards కావాలో చెప్తారా?"),
    ("ठीक है", "ठीक है, आपको कितने कार्ड चाहिए?", "आपको कितने कार्ड चाहिए?"),
    ("சரிங்க", "சரி. உங்க address சொல்லுங்க.", "உங்க address சொல்லுங்க."),
    ("okay okay", "Okay, the price is 25 rupees.", "the price is 25 rupees."),
    ("ಹೌದು", "ಹೌದು, ನಿಮ್ಮ ಹೆಸರು ಹೇಳಿ.", "ನಿಮ್ಮ ಹೆಸರು ಹೇಳಿ."),
])
def test_reply_does_not_open_by_echoing_the_callers_filler(caller, reply, expected):
    assert strip_filler_echo(reply, caller) == expected


def test_an_acknowledgement_the_caller_did_not_say_is_not_an_echo():
    assert strip_filler_echo("సరే. మీ address చెప్తారా?", "యా అండి ఓకే") == "సరే. మీ address చెప్తారా?"
    # A reply that is only the acknowledgement stays: something must be said.
    assert strip_filler_echo("ఓకే.", "ఓకే") == "ఓకే."


def test_acknowledgement_detection_is_not_fooled_by_content():
    assert not is_acknowledgement("ఓకే నాకు ఒక 100 విజిటింగ్ కార్స్ కావాలి")
    assert not is_acknowledgement("no")
    assert not is_acknowledgement("")
    assert is_acknowledgement("యా ఓకే అండి థ్యాంక్ యూ")


def test_every_rewrite_line_exists_for_every_supported_language():
    for table in (reply_guard.REPEAT_ACK, reply_guard.GO_AHEAD, reply_guard.SHARE_LATER):
        assert set(table) >= {"te", "hi", "ta", "kn", "ml", "mr", "bn", "gu", "pa", "en"}
    assert set(reply_guard.ACKNOWLEDGEMENTS) >= {"te", "hi", "ta", "kn", "ml", "mr", "bn", "gu", "pa", "en"}
