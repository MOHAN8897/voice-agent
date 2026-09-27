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
    provider, _ = realtime_voice_llm_provider(stack_override, model)
    if provider == "gemini":
        from server.realtime.gemini_audio_session import build_gemini_audio_session_instructions

        return build_gemini_audio_session_instructions(
            compiled_brain,
            caller_id=caller_id,
            language=language,
            direction=direction,
            opening_greeting=opening_greeting,
        )
    from server.realtime.text_session import build_audio_session_instructions

    return build_audio_session_instructions(
        compiled_brain,
        caller_id=caller_id,
        language=language,
        direction=direction,
        opening_greeting=opening_greeting,
    )
