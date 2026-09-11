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


def test_opening_line_offers_help():
    from server.prompts.agent_voice_rules import opening_line_for

    line = opening_line_for("en-IN", agent_name="Priya", company_name="Acme", work_scope="")
    assert "Priya" in line
    assert "help" in line.lower()
    assert "may i know your name" not in line.lower()


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
    assert "help" in line.lower()


def test_default_greeting_offers_help():
    from server.services.pstn_text_chunker import extract_opening_greeting

    g = extract_opening_greeting(None, "en-IN") or ""
    assert "help" in g.lower()
    assert "may i know your name" not in g.lower()
