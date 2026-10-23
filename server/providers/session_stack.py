"""
Session-scoped stack resolution — interim until Phase 3 call/start.
"""
from __future__ import annotations

from server.config.constants import constants, normalize_supported_language
from server.config.env import Settings, get_settings
from server.providers import resolve_stack
from server.providers.base import ResolvedStack, StackSelection, StageSelection
from server.services.cartesia_voices import is_cartesia_voice_id
from server.services.dev_secrets_store import dev_secrets_store
from server.services.runtime_settings import runtime_settings
from server.utils.errors import AppError, ErrorCode


def _cartesia_available(settings: Settings) -> bool:
    enabled = bool(dev_secrets_store.effective("enable_cartesia", settings.enable_cartesia))
    key = (dev_secrets_store.effective_secret("cartesia_api_key") or settings.cartesia_api_key or "").strip()
    return bool(enabled and key)


def infer_stt_from_runtime(*, model: str, default_provider: str, default_model: str, cartesia_on: bool) -> tuple[str, str]:
    raw = (model or default_model or "").strip()
    if raw in constants.CARTESIA_STT_MODELS or raw.lower().startswith("ink"):
        if cartesia_on:
            return "cartesia", raw
        raise AppError(ErrorCode.PROVIDER_DISABLED, message="The selected speech provider is unavailable", status_code=409)
    if raw in constants.STT_MODELS:
        return "sarvam", raw
    return default_provider, raw or default_model


def infer_tts_from_runtime(
    *,
    model: str,
    speaker: str | None,
    default_provider: str,
    default_model: str,
    cartesia_on: bool,
) -> tuple[str, str]:
    raw = (model or default_model or "").strip()
    cartesia_model = raw in constants.CARTESIA_TTS_MODELS or raw.lower().startswith("sonic")
    cartesia_voice = bool(speaker and is_cartesia_voice_id(str(speaker)))
    if cartesia_model or cartesia_voice:
        if cartesia_on:
            if not cartesia_model:
                raise AppError(ErrorCode.VALIDATION_ERROR, message="The selected voice and speech model do not match", status_code=409)
            return "cartesia", raw
        raise AppError(ErrorCode.PROVIDER_DISABLED, message="The selected speech provider is unavailable", status_code=409)
    if raw in constants.TTS_MODELS:
        return "sarvam", raw
    return default_provider, raw or default_model


def resolve_stack_for_session(session_id: str, *, language: str = "te-IN") -> ResolvedStack:
    """
    Resolve L1 stack for a live session.
    Uses env tier bundles in env mode; runtime overrides in frontend mode.
    """
    settings = get_settings()
    runtime = runtime_settings.get(session_id)
    lang = normalize_supported_language(runtime.get("sttLanguage") or language)
    config_mode = dev_secrets_store.effective("voice_agent_config_mode", settings.voice_agent_config_mode)
    tier = dev_secrets_store.effective("voice_agent_tier", settings.voice_agent_tier)
    app_env = dev_secrets_store.effective("app_environment", settings.app_environment)

    if config_mode == "env":
        return resolve_stack(
            mode="env",
            tier=tier,
            language=lang,
            environment=app_env,
        )

    cartesia_on = _cartesia_available(settings)
    base = resolve_stack(mode="env", tier=tier, language=lang, environment=app_env)
    default_stt_provider, default_stt_model = base.stt.provider, base.stt.model
    default_tts_provider, default_tts_model = base.tts.provider, base.tts.model
    llm_provider, llm_model = base.llm.provider, runtime.get("openaiModel") or base.llm.model
    if llm_model != base.llm.model:
        from server.providers import get_provider_registry

        registry = get_provider_registry()
        matches = [p["id"] for p in registry.get_catalog().get("providers", [])
                   if registry.is_provider_enabled(p["id"], "llm") and registry.is_model_allowed(p["id"], "llm", llm_model)]
        if len(matches) != 1:
            raise AppError(ErrorCode.VALIDATION_ERROR, message="The selected text model has no unambiguous enabled provider", status_code=409)
        llm_provider = matches[0]

    stt_provider, stt_model = infer_stt_from_runtime(
        model=str(runtime.get("sttModel") or default_stt_model),
        default_provider=default_stt_provider,
        default_model=default_stt_model,
        cartesia_on=cartesia_on,
    )
    tts_provider, tts_model = infer_tts_from_runtime(
        model=str(runtime.get("ttsModel") or default_tts_model),
        speaker=runtime.get("ttsSpeaker"),
        default_provider=default_tts_provider,
        default_model=default_tts_model,
        cartesia_on=cartesia_on,
    )

    speaker = runtime.get("ttsSpeaker")
    if speaker and is_cartesia_voice_id(str(speaker)) and tts_provider != "cartesia":
        speaker = None
    if not speaker:
        if tts_provider == base.tts.provider:
            speaker = base.tts.config.get("speaker") or base.tts.config.get("voice_id")
        if not speaker and tts_provider == "cartesia":
            speaker = settings.cartesia_tts_voice_id or constants.CARTESIA_DEFAULT_VOICE_ID
        elif not speaker and tts_provider == "sarvam":
            speaker = settings.sarvam_tts_speaker_te
    selection = StackSelection(
        stt=StageSelection(
            stt_provider,
            stt_model,
            {
                "mode": runtime.get("sttMode") or "transcribe",
                "stream_type": runtime.get("sttStreamType") or "fast",
            },
        ),
        llm=StageSelection(
            llm_provider,
            llm_model,
            dict(base.llm.config) if llm_model == base.llm.model else {},
        ),
        tts=StageSelection(
            tts_provider,
            tts_model,
            {**(base.tts.config if tts_provider == base.tts.provider else {}), **({"speaker": speaker} if speaker else {})},
        ),
        language=lang,
        voice_preset=runtime.get("voicePresetId"),
    )
    return resolve_stack(
        mode="frontend",
        tier=tier,
        user_selection=selection,
        language=lang,
        environment=app_env,
    )
