"""Production phone-call stack for SaaS subscribers (same path as new PSTN realtime flow)."""
from __future__ import annotations

from typing import Any

from server.realtime.models import (
    DEFAULT_GEMINI_LIVE_MODEL,
    DEFAULT_REALTIME_VOICE,
    GEMINI_LIVE_LIBRARY_VOICES,
    GEMINI_LIVE_VOICES,
    REALTIME_VOICES,
    default_gemini_live_voice,
)
from server.services.pstn_stack import normalize_pstn_stack_override
from server.services.saas.agent_voice_config import load_agent_voice_config
from server.services.saas.platform_phone_stack import resolve_platform_phone_stack
from server.services.saas.voice_catalog import phone_voice_catalog


def realtime_voice_catalog() -> list[dict[str, str]]:
    return phone_voice_catalog()


def _agent_spoken_language(agent: dict[str, Any], voice_cfg: dict[str, Any]) -> str:
    """Settings languages[] win over stale voice-section language."""
    from server.config.constants import normalize_supported_language

    langs = agent.get("languages") or []
    if isinstance(langs, list) and langs:
        code = str(langs[0] or "").strip()
        if code:
            return normalize_supported_language(code)
    single = str(agent.get("language") or "").strip()
    if single:
        return normalize_supported_language(single)
    voice_lang = str(voice_cfg.get("language") or "").strip()
    if voice_lang:
        return normalize_supported_language(voice_lang)
    return "te-IN"


async def saas_stack_override_for_agent(agent: dict[str, Any]) -> dict[str, Any]:
    """Platform stack from dev panel; agent only overrides spoken voice, speed, and language."""
    agent_id = str(agent.get("agent_id") or agent.get("id") or "")
    voice_cfg = await load_agent_voice_config(agent_id) if agent_id else {}
    saved_voice_settings = agent.get("voice_settings")
    if not isinstance(saved_voice_settings, dict):
        saved_voice_settings = agent.get("voiceSettings")
    if not isinstance(saved_voice_settings, dict):
        saved_voice_settings = voice_cfg
    agent_voice = agent.get("voice") if isinstance(agent.get("voice"), dict) else {}
    speed_val = next((value for value in (
        saved_voice_settings.get("speed"), voice_cfg.get("speed"), agent_voice.get("speed"),
    ) if value is not None), None)
    raw_tier = agent.get("default_tier") or agent.get("defaultTier")
    from server.services.saas.voice_stack_profiles import (
        VoiceProfileError,
        canonical_voice_tier,
        resolve_agent_selection,
    )

    tier = canonical_voice_tier(raw_tier)
    if tier != "premium":
        try:
            lang = _agent_spoken_language(agent, voice_cfg)
            environment = str(agent.get("environment") or "").strip()
            if not environment:
                from server.services.dev_runtime import effective_app_environment

                environment = effective_app_environment()
            stack, _snapshot = await resolve_agent_selection(
                environment=environment,
                tier=tier,
                voice_settings=saved_voice_settings if isinstance(saved_voice_settings, dict) else {},
                language=lang,
                allow_fallback=True,
            )
            if speed_val is not None:
                from server.services.tts_voice_direction import resolve_speech_pace

                tts = dict(stack["tts"])
                config = dict(tts.get("config") or {})
                config["pace"] = resolve_speech_pace(tts["provider"], speed_val)
                if tts["provider"] == "cartesia":
                    config["speed"] = config["pace"]
                stack = {**stack, "tts": {**tts, "config": config}}
            from server.services.pstn_stack import (
                normalize_pstn_stack_override as normalize_composed_stack_override,
            )

            normalized, _ = normalize_composed_stack_override(stack, language=lang, tier=tier)
            if not normalized:
                raise VoiceProfileError("profile_unavailable", "The selected voice profile is unavailable.", status_code=409)
            return normalized
        except VoiceProfileError as exc:
            import logging
            logging.getLogger(__name__).warning("PSTN composed stack selection conflict (%s), falling back to platform phone stack", exc)

    lang = _agent_spoken_language(agent, voice_cfg)
    stack = await resolve_platform_phone_stack(lang)
    rv = dict(stack.get("realtime_voice") or {})
    realtime_voice = str(
        (saved_voice_settings.get("realtimeVoice") if isinstance(saved_voice_settings, dict) else None)
        or (saved_voice_settings.get("voiceId") if isinstance(saved_voice_settings, dict) else None)
        or voice_cfg.get("realtimeVoice")
        or voice_cfg.get("voiceId")
        or agent_voice.get("realtimeVoice")
        or agent_voice.get("voiceId")
        or rv.get("voice")
        or DEFAULT_REALTIME_VOICE
    )
    llm = stack.get("llm") if isinstance(stack.get("llm"), dict) else {}
    if str(llm.get("provider") or "").lower() == "gemini":
        gemini_ids = {item.lower() for item in (*GEMINI_LIVE_VOICES, *GEMINI_LIVE_LIBRARY_VOICES)}
        if realtime_voice.lower() in {item.lower() for item in REALTIME_VOICES}:
            realtime_voice = default_gemini_live_voice(lang)
        elif realtime_voice.lower() not in gemini_ids:
            from server.realtime.providers.gemini_voice import normalize_gemini_live_voice

            realtime_voice = normalize_gemini_live_voice(realtime_voice)
    elif realtime_voice.lower() in {
        item.lower() for item in (*GEMINI_LIVE_VOICES, *GEMINI_LIVE_LIBRARY_VOICES)
    }:
        realtime_voice = DEFAULT_REALTIME_VOICE
    rv["voice"] = realtime_voice
    if speed_val is not None:
        rv["speed"] = speed_val
    stack["language"] = lang
    stack["realtime_voice"] = rv
    from server.services.saas.voice_stack_profiles import canonical_voice_tier
    raw_tier = agent.get("default_tier") or agent.get("defaultTier")
    effective_tier = canonical_voice_tier(raw_tier) if raw_tier else "medium"
    normalized, _ = normalize_pstn_stack_override(
        stack, language=lang, tier=effective_tier, default_provider="gemini"
    )
    return normalized or stack


def saas_stack_override(language: str) -> dict[str, Any]:
    """Backward-compatible minimal override (language only). Prefer saas_stack_override_for_agent."""
    raw: dict[str, Any] = {
        "pipeline": "realtime_voice",
        "language": language,
        "llm": {"provider": "gemini", "model": DEFAULT_GEMINI_LIVE_MODEL},
        "realtime_voice": {"voice": default_gemini_live_voice(language)},
    }
    normalized, _ = normalize_pstn_stack_override(
        raw, language=language, tier="medium", default_provider="gemini"
    )
    return normalized or raw
