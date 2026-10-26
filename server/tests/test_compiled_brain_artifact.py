"""Unified compiled brain assembly and live render (section 5)."""
from __future__ import annotations

import pytest

from server.brain.compiled_brain_artifact import (
    assemble_unified_brain,
    build_artifact,
    is_unified_compiled_brain,
    platform_body_for_agent_language,
    refresh_platform_sections,
)
from server.brain.sections import STATIC_OUTPUT_RULES
from server.prompts.agent_voice_rules import spoken_pack_for
from server.prompts.brain_prompt import CORE_SYSTEM_PROMPT, SECTION_SAFETY
from server.realtime.gemini_audio_session import build_gemini_audio_session_instructions
from server.realtime.text_session import build_audio_session_instructions


def test_assemble_includes_one_language_pack():
    text = assemble_unified_brain(language="ta-IN", script="--- AGENT IDENTITY ---\nYou are Meera.")
    assert "--- SPOKEN LANGUAGE (ta-IN) ---" in text
    assert "Tamil" in spoken_pack_for("ta-IN")
    assert "Tamil" in text
    assert STATIC_OUTPUT_RULES.strip() in text
    assert SECTION_SAFETY.strip() in text


def test_is_unified_detects_platform_assembly():
    unified = assemble_unified_brain(language="en-IN", script="Offer widgets.")
    assert is_unified_compiled_brain(unified)
    assert not is_unified_compiled_brain("Only business facts here.")


def test_unified_gemini_skips_duplicate_language_lock():
    brain = assemble_unified_brain(
        language="te-IN",
        script=(
            "--- AGENT IDENTITY ---\nYou are Priya.\n\n"
            "--- OUTBOUND WORKFLOW ---\n1. Wait.\n"
        ),
    )
    gemini = build_gemini_audio_session_instructions(
        brain,
        language="te-IN",
        direction="outbound",
        opening_greeting="Hi",
    )
    assert "FINAL LANGUAGE CONSTRAINT" not in gemini
    assert "SPOKEN LANGUAGE: only te-IN" not in gemini
    assert "OUTPUT MODALITY RULES" in gemini
    assert "SPOKEN LANGUAGE (TE-IN)" in gemini.upper()


def test_legacy_brain_keeps_language_overlay():
    brain = "--- AGENT IDENTITY ---\nYou are Priya.\n"
    gemini = build_gemini_audio_session_instructions(
        brain,
        language="te-IN",
        direction="outbound",
    )
    assert spoken_pack_for("te-IN", include_brevity=False, core_only=True) in gemini


def test_unified_openai_audio_skips_final_language_constraint():
    brain = assemble_unified_brain(language="en-IN", script="--- AGENT IDENTITY ---\nYou are Sam.")
    openai = build_audio_session_instructions(brain, language="en-IN", direction="outbound")
    assert "FINAL LANGUAGE CONSTRAINT" not in openai
    assert "OUTPUT MODALITY RULES" in openai


def test_platform_body_strips_legacy_core_prompt():
    assert platform_body_for_agent_language(CORE_SYSTEM_PROMPT, "en-IN") == ""


def test_build_artifact_checksum_stable():
    a = build_artifact(language="hi-IN", script="Role: support.")
    b = build_artifact(language="hi-IN", script="Role: support.")
    assert a.checksum == b.checksum
    assert a.schema_version == "1"


def test_assemble_realigns_stale_script_language_marker():
    """Switching an agent's language must not leave the stored script naming the old pack."""
    from server.brain.brain_prompt_validate import validate_rendered_brain

    script = (
        "--- LANGUAGE ---\nUse the selected en-IN language pack. Follow the platform language policy.\n\n"
        "--- CANONICAL OPENING ---\nAfter the callee speaks, say once:\nHello, this is Meera.\n"
    )
    brain = assemble_unified_brain(language="te-IN", script=script)
    assert "Use the selected te-IN language pack" in brain
    assert validate_rendered_brain(brain, "te-IN") == []


def test_refresh_platform_sections_realigns_language_change():
    from server.brain.brain_prompt_validate import validate_rendered_brain

    brain = assemble_unified_brain(
        language="te-IN",
        script="--- LANGUAGE ---\nUse the selected te-IN language pack.\n\n--- AGENT IDENTITY ---\nYou are Priya.\n",
    )
    refreshed = refresh_platform_sections(brain, "hi-IN")
    assert "Use the selected hi-IN language pack" in refreshed
    assert "--- SPOKEN LANGUAGE (hi-IN) ---" in refreshed
    assert validate_rendered_brain(refreshed, "hi-IN") == []


@pytest.mark.parametrize("locale", ["te-IN", "hi-IN", "en-IN", "en-US", "ta-IN", "kn-IN"])
def test_assemble_and_validate_all_supported_languages(locale):
    from server.brain.brain_prompt_validate import assert_rendered_brain_valid

    brain = assemble_unified_brain(
        language=locale,
        script=f"--- AGENT IDENTITY ---\nYou are a helpful representative.\n@language: {locale}\n",
    )
    assert f"--- SPOKEN LANGUAGE ({locale}) ---" in brain
    assert_rendered_brain_valid(brain, locale)


@pytest.mark.parametrize("target_locale", ["en-IN", "en-US", "ta-IN", "kn-IN", "hi-IN", "te-IN"])
def test_realign_compiled_brain_validates_cleanly(target_locale):
    from server.brain.brain_prompt_validate import assert_rendered_brain_valid
    from server.brain.script_entities import realign_compiled_brain_for_session

    initial_brain = assemble_unified_brain(
        language="te-IN",
        script="--- AGENT IDENTITY ---\nYou are Priya from HDFC.\n@language: te-IN\n",
    )
    # Realigning a Telugu compiled brain to any session language must cleanly swap headers and validate
    realigned = realign_compiled_brain_for_session(
        initial_brain,
        target_locale,
        direction="inbound",
    )
    assert f"--- SPOKEN LANGUAGE ({target_locale}) ---" in realigned
    assert_rendered_brain_valid(realigned, target_locale)
