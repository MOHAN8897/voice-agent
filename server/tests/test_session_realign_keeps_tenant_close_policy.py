"""Starting a call keeps the tenant's own farewell and close reasons.

realign_compiled_brain_for_session used to rebuild CALL END POLICY from platform
defaults on every call, so a custom farewell and narrowed close reasons were
silently dropped. A farewell written in another language still gives way to the
platform default for the call language (a Telugu goodbye on a Hindi callback).
"""
from __future__ import annotations

from server.brain.script_entities import realign_compiled_brain_for_session
from server.call.call_end_policy import (
    CALL_END_FAREWELLS,
    format_call_end_section,
    policy_from_brain,
)

TELUGU_FAREWELL = "సరే, మళ్ళీ కలుద్దాం. ధన్యవాదాలు."


def _brain(language: str, policy: dict) -> str:
    return (
        "--- SAFETY ---\nBe safe.\n\n"
        "--- CALLING SCRIPT ---\n@language: te-IN\nSell visiting cards.\n\n"
        f"{format_call_end_section(language, policy)}\n\n"
        "--- STATIC OUTPUT RULES ---\n- Answer first.\n\nLanguage: te-IN. Style: warm."
    )


def test_custom_farewell_and_reasons_survive_a_same_language_call():
    brain = _brain("te-IN", {"farewell": TELUGU_FAREWELL, "farewellSource": "tenant",
                             "allowedReasons": ["goodbye", "not_interested"]})
    policy = policy_from_brain(realign_compiled_brain_for_session(brain, "te-IN"), "te-IN")
    assert policy["farewell"] == TELUGU_FAREWELL
    assert policy["farewellSource"] == "tenant"
    assert policy["allowedReasons"] == ["goodbye", "not_interested"]


def test_other_language_call_uses_the_default_farewell_but_keeps_reasons():
    brain = _brain("te-IN", {"farewell": TELUGU_FAREWELL, "farewellSource": "tenant",
                             "allowedReasons": ["goodbye", "not_interested"]})
    policy = policy_from_brain(realign_compiled_brain_for_session(brain, "hi-IN"), "hi-IN")
    assert policy["farewell"] == CALL_END_FAREWELLS["hi-IN"]
    assert policy["farewellSource"] == "default"
    assert policy["allowedReasons"] == ["goodbye", "not_interested"]


def test_default_farewell_follows_the_call_language():
    brain = _brain("te-IN", {})
    policy = policy_from_brain(realign_compiled_brain_for_session(brain, "ta-IN"), "ta-IN")
    assert policy["farewell"] == CALL_END_FAREWELLS["ta-IN"]
