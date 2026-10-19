import pytest

from server.brain.agent_script_compiler import _personal_opening_line
from server.prompts.agent_voice_rules import LANGUAGE_LOCK
from server.prompts.agent_voice_rules import live_realtime_audio_rules, script_writer_system, spoken_pack_for
from server.realtime.gemini_audio_session import build_gemini_audio_session_instructions


@pytest.mark.parametrize("language", list(LANGUAGE_LOCK))
def test_live_policy_replaces_stale_platform_spoken_pack(language):
    brain = (
        "--- AGENT IDENTITY ---\nYou are Priya from Acme.\n"
        "--- COMPANY & OFFER ---\nAcme repairs phones.\n"
        "--- SPOKEN LANGUAGE (te-IN) ---\nSTALE_LANGUAGE_LOCK Telugu only. Never use English.\n"
        "--- CONVERSATION FLOW ---\nAsk about the phone fault.\n"
    )
    prompt = build_gemini_audio_session_instructions(brain, language=language, direction="inbound")
    assert LANGUAGE_LOCK[language] in prompt
    assert prompt.count(LANGUAGE_LOCK[language]) == 1
    assert "STALE_LANGUAGE_LOCK" not in prompt
    assert "Acme repairs phones" in prompt and "phone fault" in prompt
    if not language.startswith("en-"):
        assert "natural" in LANGUAGE_LOCK[language] and "English" in LANGUAGE_LOCK[language]


def test_hindi_personal_inbound_opening_does_not_use_telugu():
    opening = _personal_opening_line(agent_name="Priya", callee_name="", language="hi-IN", direction="inbound", is_test=True)
    assert "Nenu" not in opening and "Idi" not in opening
    assert "kaise madad" in opening and "test call" in opening


@pytest.mark.parametrize("language", list(LANGUAGE_LOCK))
def test_generation_and_live_policies_agree_on_locale_and_english_mixing(language):
    from server.prompts.conversation_policy import CONVERSATION_INTELLIGENCE, LIVE_CALL_GUIDE_BODY

    generated_policy = script_writer_system(language=language, budget_tokens=4000)
    spoken = spoken_pack_for(language)
    runtime = live_realtime_audio_rules(language)
    assert LANGUAGE_LOCK[language] in spoken
    assert LANGUAGE_LOCK[language] in runtime
    assert "NEVER switch" not in runtime + CONVERSATION_INTELLIGENCE + LIVE_CALL_GUIDE_BODY
    if not language.startswith("en-"):
        assert "English" in generated_policy
    if language == "te-IN":
        assert "Tanglish" not in spoken + generated_policy
