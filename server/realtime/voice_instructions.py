"""Route realtime voice system prompts by provider (OpenAI path unchanged)."""
from __future__ import annotations

from typing import Any

from server.realtime.models import realtime_voice_llm_provider


def build_realtime_voice_instructions(
    compiled_brain: str | None,
    *,
    model: str | None = None,
    stack_override: dict[str, Any] | None = None,
    caller_id: str | None = None,
    language: str = "te-IN",
    direction: str | None = None,
    opening_greeting: str | None = None,
) -> str:
    from server.brain.brain_prompt_validate import assert_rendered_brain_valid
    from server.prompts.agent_voice_rules import assert_spoken_pack_available
    assert_spoken_pack_available(language)
    provider, _ = realtime_voice_llm_provider(stack_override, model)
    import logging
    logger = logging.getLogger(__name__)

    if provider == "gemini":
        from server.realtime.gemini_audio_session import build_gemini_audio_session_instructions

        instructions = build_gemini_audio_session_instructions(
            compiled_brain,
            caller_id=caller_id,
            language=language,
            direction=direction,
            opening_greeting=opening_greeting,
        )
        try:
            assert_rendered_brain_valid(instructions, language)
        except Exception as val_err:
            logger.warning(
                "[REALTIME_VOICE] Rendered brain language validation warning (lang=%s): %s",
                language,
                val_err,
            )
        return instructions
    from server.realtime.text_session import build_audio_session_instructions

    instructions = build_audio_session_instructions(
        compiled_brain,
        caller_id=caller_id,
        language=language,
        direction=direction,
        opening_greeting=opening_greeting,
    )

    try:
        assert_rendered_brain_valid(instructions, language)
    except Exception as val_err:
        logger.warning(
            "[REALTIME_VOICE] Rendered brain language validation warning (lang=%s): %s",
            language,
            val_err,
        )
    return instructions
