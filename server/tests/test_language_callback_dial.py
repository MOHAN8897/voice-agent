"""Calling a contact back in another language: never blocked by the agent's own-language fixed lines."""
from __future__ import annotations

import importlib
from unittest.mock import AsyncMock

import pytest

from server.brain.compiled_brain_artifact import assemble_unified_brain
from server.call.call_end_policy import policy_from_brain
from server.call.language_callback_lines import (
    disclosure_text_for_call,
    language_substitutions,
    substitution_note,
    written_for,
)
from server.prompts.agent_voice_rules import CALL_END_FAREWELLS, build_recording_disclosure_instruction
from server.services.saas import language_switch_service as svc
from server.tests.test_language_switch_callback import _item, db  # noqa: F401 -- shared fixture

TE_FAREWELL = "సన్‌పీక్ తరఫున ధన్యవాదాలు, మీ రోజు బాగుండాలి."
TE_NOTICE = "మా సేవ మెరుగుపరచడానికి ఈ కాల్ రికార్డ్ అవుతుంది."
LANGUAGES = ["te-IN", "hi-IN", "ta-IN", "kn-IN", "ml-IN", "mr-IN", "bn-IN", "gu-IN", "pa-IN", "en-IN"]


def _telugu_agent(**extra):
    return {"agent_id": "agent-te", "languages": ["te-IN"], "active_compiled_brain_version": "v1",
            "recording_disclosure_enabled": True, "recording_disclosure_text": TE_NOTICE, **extra}


def _telugu_brain(farewell: str = TE_FAREWELL) -> str:
    return assemble_unified_brain(
        language="te-IN", script="--- OPENING ---\nనమస్తే, సన్‌పీక్ నుంచి మాట్లాడుతున్నాను.\n",
        call_end_policy={"farewell": farewell},
        platform_call_rules=build_recording_disclosure_instruction(disclosure_text=TE_NOTICE, language="te-IN"),
    )


@pytest.fixture
def published(monkeypatch):
    """The agent's active brain and a voice stack that speaks whatever language leads."""
    cbs = importlib.import_module("server.brain.compiled_brain_service")
    from server.services.saas import pstn_saas_stack

    state = {"brain": _telugu_brain()}

    async def active(agent_id):
        return {"compiled_text": state["brain"]}

    async def stack(agent):
        state["stack_languages"] = agent["languages"]
        return {"language": agent["languages"][0]}

    monkeypatch.setattr(cbs.compiled_brain_service, "get_active_for_agent", active)
    monkeypatch.setattr(pstn_saas_stack, "saas_stack_override_for_agent", stack)
    return state


async def test_custom_telugu_farewell_called_back_in_hindi_is_ready_with_a_note(published):
    ready = await svc.language_readiness(_telugu_agent(), "hi-IN")
    assert ready["ready"] and ready["code"] == "ready", ready
    assert published["stack_languages"][0] == "hi-IN"
    assert [s["line"] for s in ready["substitutions"]] == ["farewell", "recording_disclosure"]
    assert ready["note"] == ("Used the standard Hindi goodbye and recording notice because your custom ones are in "
                             "Telugu. Add a Hindi version in the script.")


@pytest.mark.parametrize("language", LANGUAGES)
def test_call_brain_speaks_only_the_call_languages_fixed_lines(language):
    rendered = svc.render_call_brain(_telugu_brain(), _telugu_agent(), language)
    assert f"--- SPOKEN LANGUAGE ({language}) ---" in rendered
    assert rendered.count("--- SPOKEN LANGUAGE (") == 1
    policy = policy_from_brain(rendered, language)
    # The agent's own-language call keeps its custom farewell; any other language
    # gets the platform default for that language.
    assert policy["farewell"] == (TE_FAREWELL if language == "te-IN" else CALL_END_FAREWELLS[language])
    if language != "te-IN":
        assert TE_FAREWELL not in rendered and TE_NOTICE not in rendered
        assert build_recording_disclosure_instruction(language=language).strip() in rendered
    else:
        assert TE_NOTICE in rendered


async def test_reviewed_farewell_in_the_target_language_is_not_reported_as_replaced(published):
    published["brain"] = _telugu_brain("सनपीक की ओर से धन्यवाद, आपका दिन शुभ हो।")
    ready = await svc.language_readiness(_telugu_agent(recording_disclosure_enabled=False), "hi-IN")
    assert ready["ready"] and ready["substitutions"] == [] and ready["note"] is None


async def test_dial_carries_the_substitutions_into_call_meta_and_returns_the_note(db, monkeypatch, published):  # noqa: F811
    from server.services.saas import call_callback_service

    factory, principal = db
    item = await _item(factory, principal, language="hi-IN")
    monkeypatch.setattr(call_callback_service, "resolve_workspace_agent",
                        AsyncMock(return_value=_telugu_agent(agent_id=item.agent_id)))
    dial = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr("server.services.saas.telephony_orchestrator.subscriber_outbound", dial)
    result = await svc.call_language_switch(principal, item.id)
    assert result["ok"] and result["language"] == "hi-IN"
    assert "standard Hindi goodbye" in result["note"]
    contact = dial.await_args.kwargs["contact"]
    assert contact["call_language"] == "hi-IN" and contact["language_switch_id"] == str(item.id)
    assert {s["line"] for s in contact["language_substitutions"]} == {"farewell", "recording_disclosure"}
    assert all(s["toLanguage"] == "hi-IN" and s["fromLanguage"] == "te-IN" for s in contact["language_substitutions"])


def test_session_disclosure_uses_the_call_languages_default_only_when_custom_text_is_foreign():
    from server.call.call_lifecycle_service import apply_recording_disclosure

    agent = _telugu_agent()
    assert TE_NOTICE in apply_recording_disclosure("brain", agent, "te-IN")
    hindi = apply_recording_disclosure("brain", agent, "hi-IN")
    assert TE_NOTICE not in hindi and build_recording_disclosure_instruction(language="hi-IN").strip() in hindi
    assert disclosure_text_for_call({**agent, "recording_disclosure_text": "यह कॉल रिकॉर्ड होगी।"}, "hi-IN")


def test_shared_script_is_never_assumed_to_be_the_other_language():
    # Hindi and Marathi share Devanagari: a Hindi agent's line is not a Marathi line.
    assert not written_for("धन्यवाद, नमस्ते।", "mr-IN", own_language="hi-IN")
    assert written_for("ধন্যবাদ, নমস্কার।", "bn-IN", own_language="te-IN")
    assert not written_for("Thanks from Acme.", "hi-IN", own_language="en-IN")
    assert written_for("Thanks from Acme.", "en-IN", own_language="te-IN")


def test_no_substitution_when_the_call_is_in_the_agents_own_language():
    assert language_substitutions(_telugu_brain(), _telugu_agent(), "te-IN") == []
    assert substitution_note([]) is None


def test_opening_from_a_telugu_script_is_spoken_in_hindi():
    from server.services.composed_voice_session import opening_needs_localization
    from server.services.pstn_text_chunker import extract_prewarm_greeting

    rendered = svc.render_call_brain(_telugu_brain(), _telugu_agent(), "hi-IN")
    opening = extract_prewarm_greeting(rendered, "hi-IN", direction="outbound") or ""
    assert any(0x0900 <= ord(c) <= 0x097F for c in opening), opening
    assert not any(0x0C00 <= ord(c) <= 0x0C7F for c in opening), opening
    assert not opening_needs_localization(opening, "hi-IN")
