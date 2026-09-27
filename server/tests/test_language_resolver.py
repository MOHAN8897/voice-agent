from server.agent.language_resolver import infer_spoken_language_from_text
from server.services.pstn_realtime_greeting_prewarm import prewarm_greeting_response_instructions


def test_infer_telugu_and_english():
    assert infer_spoken_language_from_text("నమస్తే మీరు ఎవరు?", agent_language="en-IN") == "te-IN"
    assert (
        infer_spoken_language_from_text("I only speak English please tell me more", agent_language="te-IN")
        == "en-IN"
    )


def test_prewarm_greeting_instructions_include_language():
    text = prewarm_greeting_response_instructions("te-IN", "నమస్తే, మీకు సహాయం కావాలా?")
    assert "te-IN" in text
    assert "Telugu" in text
    assert "నమస్తే" in text
