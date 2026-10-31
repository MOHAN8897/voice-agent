from server.realtime.live_transcript_sanitize import sanitize_live_assistant_transcript


def test_drops_gemini_end_call_reasoning_monologue():
    raw = (
        "The user explicitly stated they are not interested and said sorry. "
        "Per the instructions, I must accept the firm refusal, provide a polite farewell, "
        "and call the end_call tool to terminate the conversation."
    )
    assert sanitize_live_assistant_transcript(raw) == ""
