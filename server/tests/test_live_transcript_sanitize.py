from server.realtime.live_transcript_sanitize import sanitize_live_assistant_transcript


def test_sanitize_drops_underscore_placeholders():
    assert sanitize_live_assistant_transcript("_____") == ""
    assert sanitize_live_assistant_transcript("___") == ""


def test_sanitize_drops_gemini_internal_monologue():
    raw = (
        "The user provided their name, Mohan.\n"
        "I have confirmed the callback details.\n"
        "I will now end the call as the goal is complete."
    )
    assert sanitize_live_assistant_transcript(raw) == ""


def test_sanitize_keeps_normal_spoken_line():
    line = "Thank you, Mohan. Our team will call you tomorrow. Goodbye."
    assert sanitize_live_assistant_transcript(line) == line


def test_sanitize_drops_markdown_garbage():
    raw = "6 (10 ).\n\n**5. \"\" **\n---\n*: **Living Merchandising** .*"
    assert sanitize_live_assistant_transcript(raw) == ""


def test_sanitize_drops_generic_inbound_greeting():
    assert sanitize_live_assistant_transcript("Hello! How can I help you today?") == ""
