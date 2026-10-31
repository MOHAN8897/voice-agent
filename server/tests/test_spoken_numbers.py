from server.services.spoken_numbers import expand_spoken_numbers, prepare_spoken_reply, strip_spoken_phone_numbers


def test_expands_rupee_amount():
    assert "rupees five thousand" in expand_spoken_numbers("That comes to Rs.5000.")


def test_expands_rs_dot_amount():
    assert "rupees one hundred" in expand_spoken_numbers("Price is Rs.100 only.")


def test_expands_dollars():
    assert "dollars one hundred" in expand_spoken_numbers("Budget is $100.")


def test_expands_fifty_lakhs():
    assert expand_spoken_numbers("Plots from 50 lakhs.") == "Plots from fifty lakh."


def test_strips_mobile_numbers():
    out = prepare_spoken_reply("Call us at 9876543210 for details.")
    assert "9876543210" not in out
    assert "nine eight" not in out


def test_leaves_plot_two_alone():
    assert expand_spoken_numbers("plot 2 is ready") == "plot 2 is ready"


def test_expands_otp_near_label():
    assert "four zero one two" in expand_spoken_numbers("OTP is 4012")


def test_expands_clock():
    assert "ten AM" in expand_spoken_numbers("Come at 10:00 AM")


def test_prepare_spoken_reply_keeps_sentence_period():
    from server.services.spoken_numbers import prepare_spoken_reply

    out = prepare_spoken_reply("We have plots in Hyderabad.")
    assert out.endswith(".")
    assert "Hyderabad" in out
    assert "dot" not in out.lower()


def test_prepare_spoken_reply_expands_bare_decimal():
    from server.services.spoken_numbers import prepare_spoken_reply

    out = prepare_spoken_reply("Size is 80.5 square feet.")
    assert "point" in out
    assert "eighty" in out.lower() or "point" in out
    # Sentence period may remain; bare decimal must not.
    assert "80.5" not in out


def test_prepare_spoken_reply_expands_abbrev_rs():
    from server.services.spoken_numbers import prepare_spoken_reply

    out = prepare_spoken_reply("Starting at Rs.50 lakhs.")
    assert "rupees" in out.lower() or "fifty" in out
    assert "dot" not in out.lower()
    assert out.endswith(".")


def test_prepare_spoken_reply_adds_terminal_punct_if_missing():
    from server.services.spoken_numbers import prepare_spoken_reply

    out = prepare_spoken_reply("Plots start from fifty lakhs")
    assert out.endswith(".")


def test_streaming_chunk_does_not_gain_artificial_full_stop():
    from server.services.spoken_numbers import prepare_spoken_reply

    out = prepare_spoken_reply("Hi, thanks for", ensure_terminal=False)
    assert out == "Hi, thanks for"


def test_opening_line_asks_for_moment_outbound():
    from server.prompts.agent_voice_rules import opening_line_for

    line = opening_line_for("en-IN", agent_name="Priya", company_name="Acme", work_scope="")
    assert "Priya" in line
    assert "moment" in line.lower()
    assert "how can i help" not in line.lower()
    assert "may i know your name" not in line.lower()


def test_opening_line_telugu_natural_permission():
    from server.prompts.agent_voice_rules import opening_line_for

    line = opening_line_for("te-IN", agent_name="Murthi", company_name="Raghava Sales", work_scope="")
    assert "Murthi" in line
    assert "konchem time unda" not in line.lower()
    assert "moment" in line.lower() or "free" in line.lower()


def test_opening_line_inbound_offers_help():
    from server.prompts.agent_voice_rules import opening_line_for

    line = opening_line_for(
        "en-IN",
        agent_name="Priya",
        company_name="Acme",
        work_scope="",
        direction="inbound",
    )
    assert "help" in line.lower()


def test_opening_line_includes_call_purpose_with_company():
    from server.prompts.agent_voice_rules import opening_line_for

    line = opening_line_for(
        "en-IN",
        agent_name="Priya",
        company_name="Acme Realty",
        work_scope="our new plots near Hyderabad",
    )
    assert "Priya" in line
    assert "Acme Realty" in line
    assert "plots" in line.lower()
    assert "moment" in line.lower()


def test_default_greeting_outbound_asks_for_moment():
    from server.services.pstn_text_chunker import extract_opening_greeting

    g = extract_opening_greeting(None, "en-IN", direction="outbound") or ""
    assert "moment" in g.lower()
    assert "how can i help" not in g.lower()


def test_digit_reading_engines_keep_digits_and_indian_currency():
    # Sarvam Bulbul v3/v4 normalize numbers natively; hand-expanding them is against their guide.
    out = prepare_spoken_reply("Total Rs.1,697 होगा, technician 10:30 AM आएंगे.", provider="sarvam",
                               model="bulbul:v3", language="hi-IN")
    assert out == "Total ₹1,697 होगा, technician 10:30 AM आएंगे."
    for provider, model in (("gemini", "gemini-3.8-flash-tts"), ("cartesia", "sonic-3.5")):
        assert "599" in prepare_spoken_reply("Split AC is 599 rupees.", provider=provider, model=model, language="en-IN")


def test_indic_call_never_gets_english_number_words():
    out = prepare_spoken_reply("Split AC ಗೆ 599 ರೂಪಾಯಿ ಆಗುತ್ತೆ.", provider="gnani", model="timbre-v3.0", language="kn-IN")
    assert "five hundred" not in out and "599" in out


def test_english_gnani_call_still_gets_spoken_words():
    out = prepare_spoken_reply("Split AC is 599 rupees, come at 10:30 AM.", provider="gnani",
                               model="timbre-v3.0", language="en-IN")
    assert "five hundred ninety nine rupees" in out and "ten thirty AM" in out


def test_indic_call_reads_rupee_amounts_in_the_call_language():
    out = prepare_spoken_reply("Split AC కి 599 rupees, total 1,697 Rupees అవుతుంది.", provider="sarvam",
                               model="bulbul:v3", language="te-IN")
    assert out == "Split AC కి ₹599, total ₹1,697 అవుతుంది."
    # English calls keep the written word; the voice reads it in English anyway.
    assert "599 rupees" in prepare_spoken_reply("It is 599 rupees.", provider="sarvam", model="bulbul:v3", language="en-IN")


def test_trailing_generic_check_in_is_dropped_but_real_questions_stay():
    from server.services.voice_pipeline_limits import drop_generic_check_in as drop

    assert drop("Window AC servicing is ₹499, and yes, we cover Kondapur. Is there anything else you would like to know?") \
        == "Window AC servicing is ₹499, and yes, we cover Kondapur."
    assert drop("Window AC servicing-ಗೆ ₹499 ಆಗುತ್ತೆ. ಬೇರೆ ಏನಾದ್ರೂ ಕೇಳ್ಬೇಕಾ?") == "Window AC servicing-ಗೆ ₹499 ಆಗುತ್ತೆ."
    assert drop("Fridge inspection ₹250 છે. બીજું કંઈ જાણવું છે તમારે?") == "Fridge inspection ₹250 છે."
    kept = "Split AC servicing ₹599 అవుతుంది. మీ area ఏది?"
    assert drop(kept) == kept
    assert drop("Anything else I can help with?") == "Anything else I can help with?"
    thanks = "You are welcome. Is there anything else I can help you with?"
    assert drop(thanks) == thanks


def test_order_claims_in_native_script_loanwords_are_caught_but_questions_are_not():
    from server.call.action_proof import PROOF_ORDER_CONFIRMED, unproven_claim

    for claim in ("అర్థమైంది. ఆర్డర్ కన్ఫర్మ్ చేస్తున్నాను.", "Order confirm कर दिया है।", "ઓર્ડર કન્ફર્મ કરી દીધો છે."):
        assert unproven_claim(claim, ()) == PROOF_ORDER_CONFIRMED, claim
    for question in ("ఇప్పుడు order confirm చేయమంటారా?", "Shall I confirm the order?"):
        assert unproven_claim(question, ()) is None, question


def test_long_replies_keep_two_sentences_and_the_closing_question():
    from server.services.voice_pipeline_limits import cap_spoken_sentences as cap

    long = "Order confirmed. 200 cards to MG Road. Delivery in 3 days. Payment is cash on delivery. Anything to add?"
    assert cap(long) == "Order confirmed. 200 cards to MG Road. Anything to add?"
    assert cap("ఆర్డర్ అయింది. Delivery 3 రోజుల్లో. Payment cash on delivery. ఇంకా ఉందా.") == "ఆర్డర్ అయింది. Delivery 3 రోజుల్లో."
    three = "One. Two. Three?"
    assert cap(three) == three


def test_verbatim_repeat_of_previous_reply_becomes_short_acknowledgement():
    from types import SimpleNamespace
    from server.agent.conversation_manager import conversation_manager
    from server.call.live_turn_orchestrator import _avoid_verbatim_repeat

    sid = "repeat-guard-test"
    conversation_manager.add_turn(sid, "Is it confirmed?", "ఇంకా confirm అవ్వలేదు. మీ locality చెప్తారా?")
    ctx = SimpleNamespace(session_id=sid, resolved_stack=SimpleNamespace(language="te-IN"))
    assert _avoid_verbatim_repeat("ఇంకా confirm అవ్వలేదు. మీ locality చెప్తారా?", ctx) == "సరే."
    assert _avoid_verbatim_repeat("మీ locality ఏది?", ctx) == "మీ locality ఏది?"


def test_sentences_repeated_from_previous_turn_are_dropped():
    from types import SimpleNamespace
    from server.agent.conversation_manager import conversation_manager
    from server.call.live_turn_orchestrator import _avoid_verbatim_repeat

    sid = "repeat-guard-sentences"
    conversation_manager.add_turn(sid, "Is it confirmed?", "No, it is not confirmed yet. I need your locality first.")
    ctx = SimpleNamespace(session_id=sid, resolved_stack=SimpleNamespace(language="en-IN"))
    assert _avoid_verbatim_repeat("No, it is not confirmed yet. Which area are you in?", ctx) == "Which area are you in?"
    assert _avoid_verbatim_repeat("No, it is not confirmed yet. I need your locality first.", ctx) == "Sure."


def test_callback_is_withdrawn_only_on_an_explicit_negation():
    from server.call.close_classifier import _CALLBACK_NEGATION as negation

    for thanks in ("ಓಕೆ, ಥ್ಯಾಂಕ್ ಯು.", "Okay thank you", "ఓకే థాంక్స్", "Nothing else, thanks"):
        assert not negation.search(thanks), thanks
    for refusal in ("No need to call me back", "callback వద్దు", "मुझे call मत करना", "callback ಬೇಡ",
                    "തിരിച്ചു വിളിക്കേണ്ട", "હવે call ના કરતા"):
        assert negation.search(refusal), refusal
