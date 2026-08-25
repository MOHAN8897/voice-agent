"""
Session-scoped stack resolution — interim until Phase 3 call/start.
"""
from __future__ import annotations

from server.config.env import get_settings
from server.providers import resolve_stack
from server.providers.base import ResolvedStack, StackSelection, StageSelection
from server.services.runtime_settings import runtime_settings


def resolve_stack_for_session(session_id: str, *, language: str = "te-IN") -> ResolvedStack:
    """
    Resolve L1 stack for a live session.
    Uses env tier bundles in env mode; runtime overrides in frontend mode.
    """
    settings = get_settings()
    runtime = runtime_settings.get(session_id)
    lang = runtime.get("sttLanguage") or language

    if settings.voice_agent_config_mode == "env":
        return resolve_stack(
            mode="env",
            tier=settings.voice_agent_tier,
            language=lang,
            environment=settings.app_environment,
        )

    tier = settings.voice_agent_tier
    selection = StackSelection(
        stt=StageSelection(
            getattr(settings, f"voice_{tier}_stt_provider"),
            runtime.get("sttModel") or getattr(settings, f"voice_{tier}_stt_model"),
            {
                "mode": runtime.get("sttMode") or "transcribe",
                "stream_type": runtime.get("sttStreamType") or "fast",
            },
        ),
        llm=StageSelection(
            getattr(settings, f"voice_{tier}_llm_provider"),
            runtime.get("openaiModel") or getattr(settings, f"voice_{tier}_llm_model"),
            {},
        ),
        tts=StageSelection(
            getattr(settings, f"voice_{tier}_tts_provider"),
            runtime.get("ttsModel") or getattr(settings, f"voice_{tier}_tts_model"),
            {"speaker": runtime.get("ttsSpeaker") or settings.sarvam_tts_speaker_te},
        ),
        language=lang,
        voice_preset=runtime.get("voicePresetId"),
    )
    return resolve_stack(
        mode="frontend",
        user_selection=selection,
        language=lang,
        environment=settings.app_environment,
    )
