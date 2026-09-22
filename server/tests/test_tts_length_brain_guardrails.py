"""Assert TTS length tiers are embedded in the live brain the LLM sees."""
from server.brain.sections import STATIC_OUTPUT_RULES, STATIC_OUTPUT_RULES_VERSION
from server.prompts.agent_voice_rules import SOFT_BREVITY, live_realtime_output_rules, spoken_pack_for
from server.prompts.conversation_policy import CONVERSATION_INTELLIGENCE, LIVE_CALL_GUIDE_BODY
from server.realtime.text_session import build_session_instructions
from server.services.voice_pipeline_limits import (
    LIVE_REPLY_BREVITY_COMPACT,
    LIVE_REPLY_BREVITY_RULE,
    LIVE_REPLY_COMPLEX_MAX,
    LIVE_REPLY_MAX_CHARS,
    LIVE_REPLY_MIN_CHARS,
    LIVE_REPLY_NORMAL_MAX,
    LIVE_REPLY_OBJECTION_MAX,
    LIVE_REPLY_SIMPLE_MAX,
)


def _assert_tiers(blob: str) -> None:
    assert f"{LIVE_REPLY_MIN_CHARS}–{LIVE_REPLY_SIMPLE_MAX}" in blob or f"{LIVE_REPLY_MIN_CHARS}-{LIVE_REPLY_SIMPLE_MAX}" in blob
    assert f"30–{LIVE_REPLY_NORMAL_MAX}" in blob or f"30-{LIVE_REPLY_NORMAL_MAX}" in blob
    assert f"30–{LIVE_REPLY_OBJECTION_MAX}" in blob or f"30-{LIVE_REPLY_OBJECTION_MAX}" in blob
    assert f"70–{LIVE_REPLY_COMPLEX_MAX}" in blob or f"70-{LIVE_REPLY_COMPLEX_MAX}" in blob
    assert str(LIVE_REPLY_MAX_CHARS) in blob


def test_canonical_brevity_rule_has_all_tiers():
    _assert_tiers(LIVE_REPLY_BREVITY_RULE)
    _assert_tiers(LIVE_REPLY_BREVITY_COMPACT)
    assert (
        "short and meaningful" in LIVE_REPLY_BREVITY_RULE.lower()
        or "short and meaningful" in LIVE_REPLY_BREVITY_COMPACT.lower()
        or "human phone speech" in LIVE_REPLY_BREVITY_COMPACT.lower()
        or "warm ack" in LIVE_REPLY_BREVITY_RULE.lower()
    )


def test_static_rules_embed_full_length_guardrail():
    assert STATIC_OUTPUT_RULES_VERSION == "sr_v30"
    assert LIVE_REPLY_BREVITY_RULE in STATIC_OUTPUT_RULES
    _assert_tiers(STATIC_OUTPUT_RULES)


def test_spoken_pack_and_soft_brevity_embed_tiers():
    assert LIVE_REPLY_BREVITY_RULE in SOFT_BREVITY
    pack = spoken_pack_for("en-IN")
    assert LIVE_REPLY_BREVITY_RULE in pack
    _assert_tiers(pack)


def test_live_call_guide_and_human_call_embed_compact_tiers():
    _assert_tiers(LIVE_CALL_GUIDE_BODY)
    _assert_tiers(CONVERSATION_INTELLIGENCE)


def test_session_instructions_surface_length_to_realtime_llm():
    brain = f"{spoken_pack_for('en-IN')}\n\n--- CALLING SCRIPT ---\nDemo\n\n{STATIC_OUTPUT_RULES}"
    instr = build_session_instructions(brain, language="en-IN")
    _assert_tiers(instr)
    assert LIVE_REPLY_BREVITY_RULE in instr
    live = live_realtime_output_rules("en-IN")
    assert LIVE_REPLY_BREVITY_RULE in live
