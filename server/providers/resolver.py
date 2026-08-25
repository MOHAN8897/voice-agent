"""
L1 stack resolver — server/providers/resolver.py
Sole authority for STT/LLM/TTS stack resolution at call/start (Phase 3+).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from server.config.constants import constants
from server.config.env import Settings, get_settings
from server.providers.base import ConfigMode, ResolvedStack, StackSelection, StageSelection, TierName
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
    ) -> ResolvedStack:
        effective_mode: ConfigMode = mode or dev_secrets_store.effective(
            "voice_agent_config_mode", self._settings.voice_agent_config_mode
        )  # type: ignore[assignment]
        effective_tier: TierName = tier or dev_secrets_store.effective(
            "voice_agent_tier", self._settings.voice_agent_tier
        )  # type: ignore[assignment]

        if stack_override and environment == "production":
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                message="stack_override is not allowed in production",
                status_code=400,
            )

        if effective_mode == "env":
            stack = self._from_tier_config(effective_tier, language, environment)
        else:
            if user_selection is None:
                stack = self._from_tier_config(effective_tier, language, environment)
            else:
                stack = user_selection

        if stack_override:
            stack = self._apply_override(stack, stack_override)

        stack = self._apply_stage_fallbacks(stack)
        self._validate_stack(stack, language)
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
                language=cached.language or language,
                voice_preset=cached.voice_preset,
            )
        return self._from_tier_env(tier, language)

    def _from_tier_env(self, tier: TierName, language: str) -> StackSelection:
        s = self._settings
        prefix = tier.upper()
        stt_provider = getattr(s, f"voice_{tier}_stt_provider")
        stt_model = getattr(s, f"voice_{tier}_stt_model")
        llm_provider = getattr(s, f"voice_{tier}_llm_provider")
        llm_model = getattr(s, f"voice_{tier}_llm_model")
        tts_provider = getattr(s, f"voice_{tier}_tts_provider")
        tts_model = getattr(s, f"voice_{tier}_tts_model")

        tts_config: dict[str, Any] = {}
        if tts_provider == "sarvam":
            lang = constants.SUPPORTED_LANGUAGES.get(language, constants.SUPPORTED_LANGUAGES["te-IN"])
            tts_config["speaker"] = lang.get("speaker", s.sarvam_tts_speaker_te)

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
        if "stt" in override:
            stt.update(override["stt"])
        if "llm" in override:
            llm.update(override["llm"])
        if "tts" in override:
            tts.update(override["tts"])
        return StackSelection(
            stt=StageSelection(**stt),
            llm=StageSelection(**llm),
            tts=StageSelection(**tts),
            language=stack.language,
            voice_preset=stack.voice_preset,
        )

    def _apply_stage_fallbacks(self, stack: StackSelection) -> StackSelection:
        from server.services.dev_fallback_store import dev_fallback_store

        chains = dev_fallback_store.get_chains()
        return StackSelection(
            stt=self._fallback_stage("stt", stack.stt, chains.get("stt") or []),
            llm=self._fallback_stage("llm", stack.llm, chains.get("llm") or []),
            tts=self._fallback_stage("tts", stack.tts, chains.get("tts") or []),
            language=stack.language,
            voice_preset=stack.voice_preset,
        )

    def _fallback_stage(self, stage: str, sel: StageSelection, chain: list[str]) -> StageSelection:
        order = [sel.provider] + [p for p in chain if p != sel.provider]
        for pid in order:
            if not self._registry.is_provider_enabled(pid, stage):
                continue
            model = sel.model
            if pid != sel.provider:
                model = self._default_model(pid, stage) or model
            if self._registry.is_model_allowed(pid, stage, model):
                config = sel.config if pid == sel.provider else {}
                return StageSelection(pid, model, config)
            if stage == "stt" and model == "saaras:v3" and self._registry.is_model_allowed(pid, stage, "saaras:v3-realtime"):
                return StageSelection(pid, "saaras:v3-realtime", sel.config if pid == sel.provider else {})
        return sel

    def _default_model(self, provider_id: str, stage: str) -> str | None:
        for p in self._registry.get_catalog().get("providers") or []:
            if p.get("id") != provider_id:
                continue
            models = (p.get("models") or {}).get(stage) or []
            if models:
                return str(models[0].get("id") or "")
        return None

    def _validate_stack(self, stack: StackSelection, language: str) -> None:
        for stage, sel in (("stt", stack.stt), ("llm", stack.llm), ("tts", stack.tts)):
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
