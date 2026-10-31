"""Select OpenAI vs Gemini Live adapter for speech-to-speech PSTN."""
from __future__ import annotations

from typing import Any

from server.realtime.models import realtime_voice_llm_provider


def create_realtime_voice_adapter(
    *,
    stack_override: dict[str, Any] | None = None,
    model: str | None = None,
) -> Any:
    provider, _ = realtime_voice_llm_provider(stack_override, model)
    if provider == "gemini":
        from server.realtime.providers.gemini_voice import GeminiLiveVoiceAdapter

        return GeminiLiveVoiceAdapter()
    from server.realtime.providers.openai_voice import OpenAIRealtimeVoiceAdapter

    return OpenAIRealtimeVoiceAdapter()
