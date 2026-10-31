"""
L1 stack resolver — server/providers/resolver.py
Sole authority for STT/LLM/TTS stack resolution at call/start (Phase 3+).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from server.config.constants import constants, normalize_supported_language
from server.config.env import Settings, get_settings
from server.providers.base import (
    ConfigMode,
    ResolvedStack,
    StackSelection,
    StageSelection,
    TierName,
)
from server.providers.registry import ProviderRegistry, get_provider_registry
from server.services.dev_secrets_store import dev_secrets_store
from server.utils.errors import AppError, ErrorCode


class StackResolver:
    def __init__(self, settings: Settings, registry: ProviderRegistry) -> None:
        self._settings = settings
        self._registry = registry

    def resolve(
        self,
        *,
        mode: ConfigMode | None = None,
        tier: TierName | None = None,
        user_selection: StackSelection | None = None,
        language: str = "te-IN",
        stack_override: dict[str, Any] | None = None,
        environment: str = "development",
        allow_composed_override: bool = False,
    ) -> ResolvedStack:
        effective_mode: ConfigMode = mode or dev_secrets_store.effective(
            "voice_agent_config_mode", self._settings.voice_agent_config_mode
        )  # type: ignore[assignment]
        effective_tier: TierName = tier or dev_secrets_store.effective(
            "voice_agent_tier", self._settings.voice_agent_tier
        )  # type: ignore[assignment]

        language = normalize_supported_language(language)

        native_override = bool(isinstance(stack_override, dict) and stack_override.get("pipeline") == "realtime_voice")
        is_profile_override = bool(
            allow_composed_override
            and isinstance(stack_override, dict)
            and stack_override.get("pipeline") in {"composed_voice", "realtime_voice"}
            and isinstance(stack_override.get("_voice_stack_snapshot"), dict)
            and stack_override["_voice_stack_snapshot"].get("tier") == effective_tier
        )
        is_composed_override = bool(is_profile_override and stack_override.get("pipeline") == "composed_voice")
        if stack_override and environment == "production" and not is_profile_override:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                message="stack_override is not allowed in production",
                status_code=400,
            )

        if native_override:
            from server.providers.llm_protocol import native_audio_provider

            llm = stack_override.get("llm") or {}
            try:
                if not isinstance(llm, dict) or not native_audio_provider(llm.get("provider"), llm.get("model"), "websocket"):
                    raise ValueError("A native audio model must be explicit")
                stack = StackSelection(llm=StageSelection(llm["provider"], llm["model"], {"api_mode": "websocket"}),
                    stt=StageSelection(llm["provider"], "native_audio", {"inactive": True}),
                    tts=StageSelection(llm["provider"], "native_audio", {"inactive": True}), language=language)
            except (ValueError, KeyError, TypeError) as exc:
                raise AppError(ErrorCode.VALIDATION_ERROR,
                    message="The selected native audio model and provider do not match", status_code=409) from exc
        elif is_composed_override:
            # A fully resolved, server-owned profile must not depend on an
            # unrelated global tier or browser session to supply base stages.
            try:
                stack = StackSelection(**{
                    stage: StageSelection(**stack_override[stage])
                    for stage in ("stt", "llm", "tts")
                }, language=language)
            except (KeyError, TypeError) as exc:
                raise AppError(ErrorCode.VALIDATION_ERROR,
                    message="The selected voice profile is incomplete", status_code=409) from exc
        elif effective_mode == "env":
            stack = self._from_tier_config(effective_tier, language, environment)
        else:
            if user_selection is None:
                stack = self._from_tier_config(effective_tier, language, environment)
            else:
                stack = user_selection

        if stack_override and not is_composed_override and not native_override:
            stack = self._apply_override(stack, stack_override)

        # A disabled or invalid selected stage is an admission error. Replacing
        # it changes the customer's tier, voice, protocol and cost assumptions.
        if is_composed_override:
            from server.providers.llm_protocol import text_llm_api_mode

            try:
                text_llm_api_mode(stack.llm.provider, stack.llm.model, stack.llm.config.get("api_mode"))
            except (ValueError, AttributeError) as exc:
                raise AppError(ErrorCode.VALIDATION_ERROR,
                    message="The selected text model and transport do not match", status_code=409) from exc
        self._validate_stack(stack, language, native_audio=native_override)
        combination_id = self._combination_id(stack)
        return ResolvedStack(
            combination_id=combination_id,
            tier=effective_tier,
            mode=effective_mode,
            stt=stack.stt,
            llm=stack.llm,
            tts=stack.tts,
            language=language,
            voice_preset=stack.voice_preset,
        )

    def _from_tier_config(self, tier: TierName, language: str, environment: str) -> StackSelection:
        from server.db.tier_store import get_cached_tier_stack

        cached = get_cached_tier_stack(environment, tier)
        if cached is not None:
            return StackSelection(
                stt=cached.stt,
                llm=cached.llm,
                tts=cached.tts,
                language=normalize_supported_language(cached.language) if cached.language else language,
                voice_preset=cached.voice_preset,
            )
        return self._from_tier_env(tier, language)

    def _from_tier_env(self, tier: TierName, language: str) -> StackSelection:
        s = self._settings
        if tier not in ("low", "medium", "premium"):
            raise AppError(ErrorCode.VALIDATION_ERROR,
                message="The selected tier has no approved stack configuration", status_code=409)
        values = {f"{stage}_{field}": getattr(s, f"voice_{tier}_{stage}_{field}", None)
                  for stage in ("stt", "llm", "tts") for field in ("provider", "model")}
        if any(not isinstance(value, str) or not value.strip() for value in values.values()):
            raise AppError(ErrorCode.VALIDATION_ERROR,
                message="The selected tier has an incomplete stack configuration", status_code=409)
        if language not in constants.SUPPORTED_LANGUAGES and language != "unknown":
            raise AppError(ErrorCode.VALIDATION_ERROR,
                message=f"Language '{language}' is not supported", status_code=400)
        stt_provider, stt_model = values["stt_provider"], values["stt_model"]
        llm_provider, llm_model = values["llm_provider"], values["llm_model"]
        tts_provider, tts_model = values["tts_provider"], values["tts_model"]

        tts_config: dict[str, Any] = {}
        if tts_provider == "sarvam":
            from server.providers.voice_inventory import default_voice

            tts_config["speaker"] = default_voice(
                "sarvam", tts_model, None if language == "unknown" else language,
                preferred=getattr(s, "sarvam_tts_speaker_te", None),
            )

        return StackSelection(
            stt=StageSelection(stt_provider, stt_model, {"mode": "realtime" if "realtime" in stt_model else "rest"}),
            llm=StageSelection(llm_provider, llm_model, {}),
            tts=StageSelection(tts_provider, tts_model, tts_config),
            language=language,
            voice_preset="telugu_natural",
        )

    def _apply_override(self, stack: StackSelection, override: dict[str, Any]) -> StackSelection:
        stt = dict(stack.stt.__dict__)
        llm = dict(stack.llm.__dict__)
        tts = dict(stack.tts.__dict__)
        for stage, value in (("stt", stt), ("llm", llm), ("tts", tts)):
            if stage in override:
                incoming = override[stage]
                if not isinstance(incoming, dict) or set(incoming) - {"provider", "model", "config"}:
                    raise AppError(ErrorCode.VALIDATION_ERROR,
                        message="The selected stage configuration is invalid", status_code=400)
                value.update(incoming)
        return StackSelection(
            stt=StageSelection(**stt),
            llm=StageSelection(**llm),
            tts=StageSelection(**tts),
            language=stack.language,
            voice_preset=stack.voice_preset,
        )

    def _validate_stack(self, stack: StackSelection, language: str, *, native_audio: bool = False) -> None:
        stages = (("llm", stack.llm),) if native_audio else (("stt", stack.stt), ("llm", stack.llm), ("tts", stack.tts))
        for stage, sel in stages:
            if (not isinstance(sel.provider, str) or not sel.provider.strip()
                or not isinstance(sel.model, str) or not sel.model.strip() or not isinstance(sel.config, dict)):
                raise AppError(ErrorCode.VALIDATION_ERROR,
                    message="The selected stage configuration is incomplete", status_code=409)
            speaker = str(sel.config.get("speaker") or "").strip()
            if stage == "tts" and speaker and sel.provider in {"sarvam", "gnani", "cartesia", "gemini"}:
                from server.providers.voice_inventory import validate_voice

                try:
                    validate_voice(sel.provider, sel.model, speaker, language)
                except ValueError as exc:
                    raise AppError(ErrorCode.VALIDATION_ERROR,
                        message="The selected speech model, voice and language do not match", status_code=409) from exc
            if not self._registry.is_provider_enabled(sel.provider, stage):
                raise AppError(
                    ErrorCode.PROVIDER_DISABLED,
                    message=f"Provider '{sel.provider}' is disabled for {stage}",
                    status_code=400,
                    provider=sel.provider,
                )
            if not self._registry.is_model_allowed(sel.provider, stage, sel.model):
                # REST catalog model may map to realtime WS variant
                if stage == "stt" and sel.model == "saaras:v3" and self._registry.is_model_allowed(sel.provider, stage, "saaras:v3-realtime"):
                    continue
                raise AppError(
                    ErrorCode.VALIDATION_ERROR,
                    message=f"Model '{sel.model}' is not allowed for {sel.provider} {stage}",
                    status_code=400,
                    provider=sel.provider,
                )
        if language not in constants.SUPPORTED_LANGUAGES and language != "unknown":
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                message=f"Language '{language}' is not supported",
                status_code=400,
            )

    @staticmethod
    def _combination_id(stack: StackSelection) -> str:
        payload = {
            "stt": {"provider": stack.stt.provider, "model": stack.stt.model},
            "llm": {"provider": stack.llm.provider, "model": stack.llm.model},
            "tts": {"provider": stack.tts.provider, "model": stack.tts.model},
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        return digest[:16]


def resolve_stack(**kwargs: Any) -> ResolvedStack:
    settings = get_settings()
    registry = get_provider_registry()
    return StackResolver(settings, registry).resolve(**kwargs)
