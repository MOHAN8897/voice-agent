"""Guard the compiled brain artifact: size, section inventory, hangup integrity.

`assemble_unified_brain` is the single output of brief-compile, session-compile
and the SaaS employee path, so anything that changes it changes every live call.
These tests pin the three things that must not drift silently: the section
inventory, the hangup story, and the overall size.
"""
from __future__ import annotations

import pytest

from server.agent.brain_prompt_composer import estimate_tokens
from server.brain.compiled_brain_artifact import assemble_unified_brain
from server.prompts.agent_voice_rules import spoken_pack_for

# Every section the compiled brain has always carried. The order is the order
# they are emitted in. Nothing may be dropped: the model needs all six.
EXPECTED_SECTIONS = (
    "SAFETY",
    "SPOKEN LANGUAGE",
    "CALLING SCRIPT",
    "PLATFORM CALL RULES",
    "CALL END POLICY",
    "STATIC OUTPUT RULES",
)

# Size ceiling. The brief asked for 3_000; the measured result is 2_877 for the
# te-IN agent and 2_638 for en-IN, the largest locale. The number/phone TTS
# blocks and the worked examples are not shipped in the compiled brain — the
# standalone pack still carries them. Reaching materially below this would mean
# dropping a rule the model needs (caller details, grammar, or the hangup
# policy), so this is the floor, not a soft target.
COMPILED_BRAIN_TOKEN_CEILING = 3_000

SCRIPT = """--- ENTITY TAGS ---
@agent_name: Alex
@company_name: spandana private limited
@opening_line: Hi, nenu Alex, spandana private limited nundi matladutunnanu. Meeku oka moment unda?"""


def _brain(language: str = "te-IN") -> str:
    return assemble_unified_brain(
        language=language,
        script=SCRIPT,
        platform_call_rules="--- OUTBOUND WORKFLOW ---\n1. Wait for the callee to speak first.",
    )


def test_all_sections_are_present_in_order():
    brain = _brain()
    positions = [brain.index(f"--- {name}") for name in EXPECTED_SECTIONS]
    assert positions == sorted(positions), "compiled brain sections are out of order"


def test_spoken_pack_matches_the_configured_language():
    brain = _brain("te-IN")
    assert "--- SPOKEN LANGUAGE (te-IN) ---" in brain
    assert "--- SPOKEN LANGUAGE (en-IN) ---" not in brain


def test_hangup_story_is_intact():
    brain = _brain()
    # The call end policy is the authoritative hangup story; these markers are
    # what keeps a spoken goodbye bound to a real disconnect.
    for marker in (
        "end_call",
        "Never say goodbye unless should_end is true.",
        "firm_refusal",
        "goal_complete",
    ):
        assert marker in brain, f"hangup marker lost: {marker}"


def test_call_end_policy_section_is_present_and_unembellished():
    brain = _brain()
    start = brain.index("--- CALL END POLICY ---")
    end = brain.index("--- STATIC OUTPUT RULES ---")
    policy = brain[start:end]
    assert "end_call" in policy
    assert policy.count("--- ") == 1, "call end policy picked up a nested section"


def test_compiled_brain_is_within_the_size_ceiling():
    for language in ("te-IN", "en-IN", "en-US", "hi-IN"):
        brain = _brain(language)
        assert estimate_tokens(brain) <= COMPILED_BRAIN_TOKEN_CEILING, (
            f"{language} compiled brain is {estimate_tokens(brain)} tokens"
        )


def test_length_bands_survive_in_the_static_rules():
    from server.services.voice_pipeline_limits import (
        LIVE_REPLY_COMPLEX_MAX,
        LIVE_REPLY_MAX_CHARS,
        LIVE_REPLY_MIN_CHARS,
        LIVE_REPLY_NORMAL_MAX,
        LIVE_REPLY_OBJECTION_MAX,
        LIVE_REPLY_SIMPLE_MAX,
        LIVE_REPLY_SOFT_MAX_CHARS,
    )

    static = _brain().split("--- STATIC OUTPUT RULES ---", 1)[1]
    assert f"{LIVE_REPLY_MIN_CHARS}–{LIVE_REPLY_SIMPLE_MAX}" in static
    assert f"30–{LIVE_REPLY_NORMAL_MAX}" in static
    assert f"30–{LIVE_REPLY_OBJECTION_MAX}" in static
    assert f"70–{LIVE_REPLY_COMPLEX_MAX}" in static
    assert str(LIVE_REPLY_SOFT_MAX_CHARS) in static
    assert str(LIVE_REPLY_MAX_CHARS) in static


def test_outbound_numbering_rules_still_ship():
    """The 'dialed number already known' rule must survive the pack trim."""
    pack = _brain().split("--- SPOKEN LANGUAGE (te-IN) ---", 1)[1]
    assert "dialed customer number is ALREADY KNOWN" in pack


def test_core_only_pack_drops_the_requested_rule_blocks():
    """NUMBERS, PHONE NUMBERS, VOICE EXAMPLES and the policy pointer stay out.

    They are removed from the compiled brain only. A pack used on its own is
    unchanged, so no other caller silently loses a TTS guardrail.
    """
    from server.prompts.agent_voice_rules import PHONE_CALL_POLICY_PTR

    core = spoken_pack_for("te-IN", include_brevity=False, core_only=True)
    for dropped in ("NUMBERS (speak them", "PHONE NUMBERS", "VOICE EXAMPLES", "PHONE CALL"):
        assert dropped not in core, f"{dropped} should not ship in the compiled brain"
    assert PHONE_CALL_POLICY_PTR not in core
    # What must survive.
    assert "CALLER DETAILS" in core
    assert "OVERLAP" in core
    assert "SPOKEN GRAMMAR" in core
    assert "--- SPOKEN LANGUAGE (te-IN) ---" in core


def test_core_only_strip_is_case_insensitive():
    """Regression: comparing an uppercased line to a lowercase header silently
    kept NUMBERS and PHONE NUMBERS in the compiled brain."""
    for locale in ("te-IN", "en-IN", "en-US", "hi-IN"):
        core = spoken_pack_for(locale, include_brevity=False, core_only=True)
        assert "rupees fifty lakhs" not in core, locale
        assert "Never read phone, mobile, WhatsApp" not in core, locale


def test_standalone_pack_keeps_every_rule_block():
    """Any caller using a pack on its own must still get the full guardrails."""
    for locale in ("te-IN", "en-IN", "en-US", "hi-IN"):
        pack = spoken_pack_for(locale)
        for kept in ("NUMBERS (speak them", "PHONE NUMBERS", "VOICE EXAMPLES", "PHONE CALL"):
            assert kept in pack, f"{kept} missing from standalone {locale} pack"


def test_number_and_phone_rules_are_absent_from_the_compiled_brain():
    brain = _brain()
    assert "rupees fifty lakhs" not in brain
    assert "Never read phone, mobile, WhatsApp" not in brain
    assert "VOICE EXAMPLES" not in brain


def test_length_bands_are_not_shipped_twice():
    """The pack and STATIC both carried the bands; the assembly asks for one copy."""
    from server.services.voice_pipeline_limits import LIVE_REPLY_BREVITY_RULE

    brain = _brain()
    assert brain.count(LIVE_REPLY_BREVITY_RULE.strip()) == 1
    # The standalone pack is unchanged, so a pack used on its own still guards.
    assert LIVE_REPLY_BREVITY_RULE in spoken_pack_for("te-IN")


def test_language_lock_is_not_stated_twice():
    from server.prompts.agent_voice_rules import LANGUAGE_LOCK

    brain = _brain()
    assert brain.count(LANGUAGE_LOCK["te-IN"].strip()) == 1


def test_section_markers_are_stripped_from_the_compiled_artifact():
    raw = "<!-- section:facts:abc -->\nWe sell plots.\n\n<!-- section:faq:def -->\n"
    brain = assemble_unified_brain(language="te-IN", script=raw)
    assert "<!-- section:" not in brain
    assert "We sell plots." in brain


def test_hangup_rule_survives_in_the_default_behaviour_seed():
    """test_hangup_judgment_critical requires this; a trim pass removed it once."""
    from server.prompts.voice_defaults import DEFAULT_BEHAVIOUR_INSTRUCTIONS

    assert "stay on the line" in DEFAULT_BEHAVIOUR_INSTRUCTIONS.lower()


async def test_superseded_defaults_are_reseeded_but_user_edits_are_kept(monkeypatch):
    """The seeds were slimmed, so agents seeded earlier must pick up the new text.

    Matching is on the exact superseded text: a section somebody edited does not
    match and must be left exactly as it is.
    """
    from server.brain import business_brain_store as store
    from server.brain.sections import default_section_seeds

    current = {s.type: s.raw_text for s in default_section_seeds()}
    stale = store._LEGACY_DEFAULT_TEXTS["identity_purpose"][0]

    sections = [
        {"section_id": "a", "type": "identity_purpose", "raw_text": stale, "order": 10},
        {"section_id": "b", "type": "facts", "raw_text": "My own hand-written facts.", "order": 20},
    ]
    saved: dict[str, str] = {}

    async def fake_get(_agent_id):
        return list(sections)

    async def fake_save(_agent_id, updated):
        saved["payload"] = repr(updated)
        return updated

    monkeypatch.setattr(store.business_brain_store, "get_sections", fake_get)
    monkeypatch.setattr(store.business_brain_store, "save_draft_sections", fake_save)

    result = await store.business_brain_store._refresh_untouched_defaults("agent", sections)

    by_id = {s["section_id"]: s["raw_text"] for s in result}
    assert by_id["a"] == current["identity_purpose"], "stale default was not refreshed"
    assert by_id["b"] == "My own hand-written facts.", "user edit was clobbered"
