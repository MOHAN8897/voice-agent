"""PSTN voice-flow factory — composed STT/LLM/TTS vs Realtime audio E2E."""
from __future__ import annotations

from typing import Any

from server.realtime.models import uses_realtime_voice
from server.services.pstn_voice_core import PstnVoiceLoop


def is_realtime_e2e_stack(stack_override: dict[str, Any] | None) -> bool:
    return uses_realtime_voice(stack_override=stack_override)


def create_pstn_voice_loop(
    *,
    stack_override: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    """Return the composed PstnVoiceLoop unless this call opted into Realtime audio E2E."""
    if is_realtime_e2e_stack(stack_override):
        from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

        kwargs["stack_override"] = stack_override
        return PstnRealtimeVoiceLoop(**kwargs)
    return PstnVoiceLoop(**kwargs)
