"""Live reply soft limits — prompt brevity + sentence-safe safety cap."""
from server.call.live_turn_orchestrator import finalize_live_spoken_text
from server.services.voice_pipeline_limits import (
    LIVE_REPLY_MAX_CHARS,
    LIVE_REPLY_SOFT_MAX_CHARS,
    LiveReplyStreamCap,
    clamp_live_spoken_reply,
    collapse_repeated_spoken_reply,
    spoken_delta_after_collapse,
)


def test_clamp_long_catalog_reply():
    long_reply = (
        "If you mean the person in charge, I don't have a confirmed person name to share from here. "
        "I can help with the business info: Priya Estates handles land and villa enquiries, "
        "and you can reach them on eight eight nine seven nine zero eight four seven zero. "
        "We also have weekend site visits, loan desk support, and a brochure we can email later today "
        "if you want more detail on plot sizes and villa floor plans across the Hyderabad outskirts."
    )
    trimmed = clamp_live_spoken_reply(long_reply)
    assert len(trimmed) <= LIVE_REPLY_MAX_CHARS
    assert trimmed.startswith("If you mean")
    assert not trimmed.lower().endswith((" or", " or.", " and", " from"))


def test_collapse_exact_repeated_greeting():
    g = "Hi, this is Priya calling from Acme Realty. How can I help you today?"
    assert collapse_repeated_spoken_reply(g + g) == g


def test_collapse_restarted_greeting_keeps_second_take():
    doubled = (
        "Hi, this is Priya calling from Acme Realty. How can I help you today?"
        "Hi, this is Priya calling from Acme Realty. I'm doing well, thanks. How can I help you today?"
    )
    out = collapse_repeated_spoken_reply(doubled)
    assert out.count("Hi, this is Priya") == 1
    assert "doing well" in out.lower()
    assert "how can i help you today?" in out.lower()


def test_finalize_collapses_restarted_greeting():
    doubled = (
        "Hi, this is Priya calling from Acme Realty. How can I help you today?"
        "Hi, this is Priya calling from Acme Realty. I'm doing well, thanks. How can I help you today?"
    )
    out = finalize_live_spoken_text("Hi, how are you?", doubled)
    assert out.count("Priya") == 1
    assert "doing well" in out.lower()


def test_finalize_direct_fact_stays_one_sentence():
    user = "What time do you close?"
    reply = "We close at eight PM. We're open daily and parking is included on weekends."
    out = finalize_live_spoken_text(user, reply)
    assert out.startswith("We close at eight PM")
    assert "parking" not in out.lower()
    assert len(out) <= LIVE_REPLY_MAX_CHARS


def test_stream_cap_suppresses_restart_double():
    cap = LiveReplyStreamCap()
    first = "Hi, this is Priya calling from Acme Realty. How can I help you today?"
    assert cap.feed(first) == first
    # Restart begins
    assert cap.feed("Hi, this is Priya calling from Acme Realty. I'm doing well.") == ""
    assert cap.exhausted
    final = cap.finalize(
        first + "Hi, this is Priya calling from Acme Realty. I'm doing well, thanks. How can I help you today?"
    )
    assert final.count("Priya") == 1
    assert "doing well" in final.lower()


def test_stream_cap_soft_safety():
    cap = LiveReplyStreamCap()
    first = cap.feed("A" * (LIVE_REPLY_MAX_CHARS - 30))
    second = cap.feed("B" * 80)
    assert len(first) == LIVE_REPLY_MAX_CHARS - 30
    assert len(cap.emitted) <= LIVE_REPLY_MAX_CHARS
    assert len(second) <= 30


def test_soft_target_leaves_room_to_finish_sentence():
    reply = (
        "We currently offer periodic car service plans and AMC options for hatchbacks and sedans, "
        "including Basic and Comprehensive Service. The workshop is in Kukatpally, and pickup is "
        "available within the surrounding area."
    )
    assert LIVE_REPLY_SOFT_MAX_CHARS < len(reply) < LIVE_REPLY_MAX_CHARS

    cap = LiveReplyStreamCap()
    emitted = cap.feed(reply[:190]) + cap.feed(reply[190:])
    assert emitted == reply
    assert cap.finalize(emitted) == reply


def test_stream_cap_does_not_suppress_normal_mid_reply():
    """Collapse must not kill a normal offer sentence mid-stream."""
    from server.services.voice_pipeline_limits import is_incomplete_spoken_crumb

    cap = LiveReplyStreamCap()
    first = "We offer residential plots in Hyderabad outskirts from rupees fifty "
    assert cap.feed(first) == first
    second = "lakhs. A site visit is a good next step."
    assert cap.feed(second) == second
    assert not cap.exhausted
    final = cap.finalize(first + second)
    assert "fifty lakhs" in final.lower()
    assert not is_incomplete_spoken_crumb(final)


def test_incomplete_spoken_crumbs():
    from server.services.voice_pipeline_limits import is_incomplete_spoken_crumb

    assert is_incomplete_spoken_crumb("We.")
    assert is_incomplete_spoken_crumb("We focus on residential plots from rupees fifty lak.")
    assert not is_incomplete_spoken_crumb("OK.")
    assert not is_incomplete_spoken_crumb(
        "We offer residential plots in Hyderabad outskirts from rupees fifty lakhs."
    )


def test_finalize_drops_incomplete_crumb():
    assert finalize_live_spoken_text("Tell me more", "We.") == ""
    assert finalize_live_spoken_text("Tell me more", "fifty lak.") == ""


def test_spoken_delta_after_collapse_skips_restart_prefix():
    first = "Hi, this is Priya calling from Acme Realty. How can I help you today?"
    restart = (
        "Hi, this is Priya calling from Acme Realty. I'm doing well, thanks. "
        "How can I help you today?"
    )
    delta, accum = spoken_delta_after_collapse(first, restart)
    assert "doing well" in delta.lower()
    assert accum.count("Priya") == 1


def test_spoken_delta_after_collapse_exact_duplicate():
    line = "We close at eight PM on weekdays."
    delta, accum = spoken_delta_after_collapse(line, line)
    assert delta == ""
    assert accum == line
