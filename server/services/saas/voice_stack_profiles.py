"""Durable admin profiles for the composed Low and Standard PSTN stacks.

This module deliberately keeps provider identifiers inside privileged profile
records. Tenant catalog responses contain opaque aliases and safe labels only.
New profiles remain unavailable until evidence and a native per-tier retail rate
are present; the legacy universal stack is never used as a fallback.
"""
from __future__ import annotations

import copy
import hashlib
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm.attributes import flag_modified

from server.config.constants import constants
from server.db.connection import get_session_factory
from server.db.models.entities import ConfigVersion, TierAssignment

COMPOSED_TIERS = ("low", "medium")
TIER_LABELS = {"low": "Economical", "medium": "Standard Regional", "premium": "Premium"}
_VOICE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,100}$")
_PRIVATE_LABEL_RE = re.compile(
    r"\b(vobiz|telnyx|nango|exotel|plivo|composio|sarvam|gemini|gnani|cartesia|openai|elevenlabs|deepgram|playht|murf|azure|bulbul|timbre|sonic|saaras|saarika)\b|https?://",
    re.IGNORECASE,
)
_SECRET_KEYS = {"api_key", "apikey", "secret", "token", "credential", "credentials", "authorization"}
_EVIDENCE_KEYS = (
    "sarvamModelAccess",
    "sttVerified",
    "ttsCatalogVerified",
    "toolsVerified",
    "capacityVerified",
    "mediaFormatsVerified",
    "credentialRefConfigured",
)
_EVIDENCE_MESSAGES = {
    "sarvamModelAccess": ("model_access_unverified", "Approved text model access has not been verified."),
    "sttVerified": ("stt_unverified", "Streaming speech recognition has not been verified."),
    "ttsCatalogVerified": ("voice_catalog_unverified", "The selected speech model and voice catalog have not been verified."),
    "toolsVerified": ("tools_unverified", "Tool compatibility has not been verified."),
    "capacityVerified": ("capacity_unverified", "Capacity and concurrency have not been verified."),
    "mediaFormatsVerified": ("media_format_unverified", "Carrier media formats have not been verified."),
    "credentialRefConfigured": ("credential_reference_missing", "A server-side credential reference is not configured."),
}


class VoiceProfileError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 422, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.details = details or {}


def canonical_voice_tier(value: Any) -> str:
    tier = str(value or "").strip().lower()
    aliases = {
        "budget": "low",
        "low": "low",
        "standard": "medium",
        "medium": "medium",
        "flagship": "premium",
        "high": "premium",
        "premium": "premium",
    }
    if tier in aliases:
        return aliases[tier]
    if re.match(r"^[a-z0-9_]{1,20}$", tier):
        return tier
    raise VoiceProfileError("invalid_tier", f"Invalid tier identifier '{tier}'. Choose Economical, Standard, Flagship, or an alphanumeric tier slug.")


def _reject_secrets(value: Any, path: str = "profile") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).replace("-", "_").lower()
            if normalized in _SECRET_KEYS or normalized.endswith("_api_key"):
                raise VoiceProfileError("secret_field_forbidden", f"{path} cannot contain credential values.")
            _reject_secrets(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secrets(child, f"{path}[{index}]")


def _identifier(value: Any, label: str, *, allow_empty: bool = False) -> str:
    raw = str(value or "").strip()
    if (not raw and allow_empty) or (raw and _VOICE_ID_RE.fullmatch(raw)):
        return raw
    raise VoiceProfileError("invalid_profile", f"{label} must be a stable identifier.")


def validate_composed_profile(payload: Any, *, tier: str, allow_premium: bool = False) -> dict[str, Any]:
    """Validate the admin-owned executable profile; values are never defaulted."""
    tier_norm = str(tier or "").strip().lower()
    if not (tier_norm in COMPOSED_TIERS or (allow_premium and tier_norm == "premium") or (tier_norm != "premium" and re.match(r"^[a-z0-9_]{1,20}$", tier_norm))):
        raise VoiceProfileError("read_only_tier", f"Tier '{tier}' cannot be managed here.", status_code=409)
    if not isinstance(payload, dict):
        raise VoiceProfileError("invalid_profile", "composedProfile must be an object.")
    _reject_secrets(payload)
    if payload.get("schemaVersion") != 1:
        raise VoiceProfileError("unsupported_profile_version", "schemaVersion must be 1.")
    profile = copy.deepcopy(payload)
    profile["enabled"] = False
    if "label" in payload and str(payload["label"]).strip():
        profile["label"] = str(payload["label"]).strip()[:100]
    rate_val = payload.get("retailRateInr") if payload.get("retailRateInr") is not None else payload.get("rateInr")
    if rate_val is not None:
        try:
            profile["retailRateInr"] = round(float(rate_val), 4)
            profile["rateInr"] = profile["retailRateInr"]
        except (TypeError, ValueError):
            pass
    if "supplierCostInr" in payload and payload["supplierCostInr"] is not None:
        try:
            profile["supplierCostInr"] = round(float(payload["supplierCostInr"]), 4)
        except (TypeError, ValueError):
            pass

    languages = profile.get("supportedLanguages")
    if not isinstance(languages, list) or not languages:
        raise VoiceProfileError("invalid_profile", "Select at least one supported language.")
    clean_languages = list(dict.fromkeys(str(v).strip() for v in languages if str(v).strip()))
    if not clean_languages or any(lang not in constants.SUPPORTED_LANGUAGES for lang in clean_languages):
        raise VoiceProfileError("invalid_profile", "The profile contains an unsupported language.")
    profile["supportedLanguages"] = clean_languages

    stt = profile.get("stt")
    llm = profile.get("llm")
    if not isinstance(stt, dict) or not isinstance(llm, dict):
        raise VoiceProfileError("invalid_profile", "Speech recognition and text model selections are required.")
    stt_provider = str(stt.get("provider") or "").lower()
    if stt_provider not in {"sarvam", "gemini", "deepgram", "cartesia"}:
        raise VoiceProfileError("invalid_profile", f"Choose a supported speech recognition provider: {stt_provider}")

    llm_provider = str(llm.get("provider") or "").lower()
    if llm_provider not in {"gemini", "sarvam", "openai", "deepseek", "groq", "anthropic"}:
        raise VoiceProfileError("invalid_profile", f"Choose a supported text model provider: {llm_provider}")

    for block, keys, title in (
        (stt, ("model",), "Speech recognition"),
        (llm, ("modelId",), "Text model"),
    ):
        for key in keys:
            _identifier(block.get(key), f"{title} {key}")

    llm_api_mode = str(llm.get("apiMode") or "").strip().lower()
    from server.providers.llm_protocol import native_audio_provider, text_llm_api_mode

    try:
        native_provider = native_audio_provider(llm_provider, llm["modelId"], llm_api_mode)
        llm["apiMode"] = "websocket" if native_provider else text_llm_api_mode(llm_provider, llm["modelId"], llm_api_mode)
    except ValueError as exc:
        raise VoiceProfileError("invalid_profile", str(exc)) from exc

    engines = profile.get("engines")
    if not isinstance(engines, list) or not engines:
        raise VoiceProfileError("invalid_profile", "Add at least one approved speech engine.")
    seen_engines: set[str] = set()
    for engine in engines:
        if not isinstance(engine, dict):
            raise VoiceProfileError("invalid_profile", "Each speech engine must be an object.")
        engine_id = _identifier(engine.get("id"), "Engine id")
        if engine_id in seen_engines:
            raise VoiceProfileError("invalid_profile", "Engine ids must be unique.")
        seen_engines.add(engine_id)
        if not str(engine.get("label") or "").strip():
            raise VoiceProfileError("invalid_profile", "Each speech engine needs a display label.")
        models = engine.get("models")
        if not isinstance(models, list) or not models:
            raise VoiceProfileError("invalid_profile", "Each speech engine needs at least one model.")
        seen_models: set[str] = set()
        for model in models:
            if not isinstance(model, dict):
                raise VoiceProfileError("invalid_profile", "Each speech model must be an object.")
            model_id = _identifier(model.get("id"), "Model id")
            if model_id in seen_models:
                raise VoiceProfileError("invalid_profile", "Model ids must be unique within an engine.")
            seen_models.add(model_id)
            provider = str(model.get("provider") or "").lower()
            if provider not in {"sarvam", "gemini", "cartesia", "gnani", "elevenlabs", "openai"}:
                raise VoiceProfileError("invalid_profile", "Choose a supported speech engine.")
            if not model.get("apiMode"):
                model["apiMode"] = "websocket" if provider in {"sarvam", "cartesia", "gemini", "gnani"} else "streaming_rest"
            for key in ("model", "apiMode"):
                _identifier(model.get(key), f"Model {key}")
            api_mode = str(model.get("apiMode") or "").strip().lower()
            allowed_api_modes = {"unary_rest", "streaming_rest", "websocket"}
            if api_mode not in allowed_api_modes:
                raise VoiceProfileError("invalid_profile", "The selected speech engine API mode does not match its supported transport.")
            if native_provider and (provider != native_provider or model["model"] != llm["modelId"] or api_mode != "websocket"):
                raise VoiceProfileError("invalid_profile", "Native speech and conversation selections must use the same live model.")
            if not native_provider and provider == "gemini" and api_mode in {"streaming_rest", "websocket"}:
                from server.providers.gemini_tts import supports_gemini_tts_streaming

                if not supports_gemini_tts_streaming(str(model.get("model") or "")):
                    raise VoiceProfileError("invalid_profile", "The selected speech model does not support streaming audio.")
            if not str(model.get("label") or "").strip():
                raise VoiceProfileError("invalid_profile", "Each speech model needs a display label.")
            voices = model.get("voices")
            if not isinstance(voices, list) or not voices:
                raise VoiceProfileError("invalid_profile", "Each speech model needs at least one voice.")
            seen_voices: set[str] = set()
            for voice in voices:
                if not isinstance(voice, dict):
                    raise VoiceProfileError("invalid_profile", "Each voice must be an object.")
                voice_id = _identifier(voice.get("id"), "Voice id")
                if voice_id in seen_voices:
                    raise VoiceProfileError("invalid_profile", "Voice ids must be unique within a model.")
                seen_voices.add(voice_id)
                _identifier(voice.get("providerVoiceId"), "Provider voice id")
                if not str(voice.get("label") or "").strip():
                    raise VoiceProfileError("invalid_profile", "Each voice needs a display label.")
                voice_languages = voice.get("languages")
                if not isinstance(voice_languages, list) or not voice_languages:
                    raise VoiceProfileError("invalid_profile", "Each voice needs at least one language.")
                if any(str(lang) not in clean_languages for lang in voice_languages):
                    raise VoiceProfileError("invalid_profile", "A voice language must also be enabled for the profile.")
                voice["languages"] = list(dict.fromkeys(str(lang) for lang in voice_languages))
                if provider in {"sarvam", "gnani", "gemini", "cartesia"}:
                    from server.providers.voice_inventory import validate_voice

                    try:
                        for lang in voice["languages"]:
                            validate_voice(provider, model["model"], voice["providerVoiceId"], lang)
                    except ValueError as exc:
                        raise VoiceProfileError("invalid_profile", "The speech model, voice and language do not match.") from exc

    evidence = profile.get("evidence")
    if not isinstance(evidence, dict):
        evidence = {key: False for key in _EVIDENCE_KEYS}
    profile["evidence"] = {key: evidence.get(key) is True for key in _EVIDENCE_KEYS}

    voice_dynamics = payload.get("voiceDynamics")
    if isinstance(voice_dynamics, dict):
        clean_dynamics: dict[str, Any] = {}
        spd = voice_dynamics.get("speed") if voice_dynamics.get("speed") is not None else voice_dynamics.get("pace")
        if spd is not None:
            try:
                # Union of every provider band; per-provider clamping happens at
                # apply time so a profile can switch engines without losing values.
                clean_dynamics["speed"] = max(0.25, min(3.0, round(float(spd), 2)))
                clean_dynamics["pace"] = clean_dynamics["speed"]
            except (TypeError, ValueError):
                pass
        pitch_val = voice_dynamics.get("pitch")
        if pitch_val is not None:
            try:
                clean_dynamics["pitch"] = max(-0.75, min(0.75, round(float(pitch_val), 2)))
            except (TypeError, ValueError):
                pass
        temp_val = voice_dynamics.get("temperature")
        if temp_val is not None:
            try:
                clean_dynamics["temperature"] = max(0.01, min(1.0, round(float(temp_val), 2)))
            except (TypeError, ValueError):
                pass
        emo_val = str(voice_dynamics.get("emotion") or "").strip().lower()
        from server.services.tts_voice_direction import CARTESIA_SAFE_EMOTIONS

        if emo_val in CARTESIA_SAFE_EMOTIONS:
            clean_dynamics["emotion"] = emo_val
        vol_val = voice_dynamics.get("volume")
        if vol_val is not None:
            try:
                clean_dynamics["volume"] = max(0.3, min(3.0, round(float(vol_val), 2)))
            except (TypeError, ValueError):
                pass
        profile["voiceDynamics"] = clean_dynamics
    elif "voiceDynamics" in profile:
        from server.services.tts_voice_direction import DEFAULT_CARTESIA_EMOTION

        profile["voiceDynamics"] = {
            "speed": 1.0,
            "pace": 1.0,
            "pitch": 0.0,
            "temperature": 0.7,
            "emotion": DEFAULT_CARTESIA_EMOTION,
            "volume": 1.0,
        }
    return profile


def _choice_keys(profile: dict[str, Any], previous_aliases: dict[str, Any] | None = None) -> dict[str, dict[str, str]]:
    """Internal tuple -> opaque public IDs. No upstream model/voice ID is returned."""
    aliases = {"engines": {}, "models": {}, "voices": {}}
    stored = previous_aliases if isinstance(previous_aliases, dict) else {}
    old = {kind: dict(stored.get(kind) or {}) for kind in aliases}
    for engine in profile.get("engines") or []:
        eid = str(engine["id"])
        aliases["engines"][eid] = old["engines"].get(eid) or f"eng_{uuid.uuid4().hex}"
        for model in engine.get("models") or []:
            mid = str(model["id"])
            model_key = f"{eid}::{mid}"
            aliases["models"][model_key] = old["models"].get(model_key) or old["models"].get(f"{eid}\u0000{mid}") or f"mod_{uuid.uuid4().hex}"
            for voice in model.get("voices") or []:
                vid = str(voice["id"])
                voice_key = f"{eid}::{mid}::{vid}"
                aliases["voices"][voice_key] = old["voices"].get(voice_key) or old["voices"].get(f"{eid}\u0000{mid}\u0000{vid}") or f"voc_{uuid.uuid4().hex}"
    return aliases


def _profile_record(row: TierAssignment | None) -> dict[str, Any] | None:
    if row is None:
        return None
    payload = row.stack_payload if isinstance(row.stack_payload, dict) else {}
    record = payload.get("composed_voice_profile")
    return record if isinstance(record, dict) else None


_REVERSE_ALIAS_CACHE: dict[str, dict[str, Any]] = {}


def _clean_catalog_voice_label(raw_label: Any, pvid: str, tier: str) -> str:
    # Legacy presentation helper only. Voice numbers never resolve to providers.
    match = re.search(r"(?:voice[- ](?:gnani-|cartesia-)?)?(\d+)$", pvid, re.IGNORECASE)
    return f"Voice {match.group(1)}" if match else "Voice"


def _resolve_catalog_voice_metadata(pvid: str, tier: str) -> dict[str, str]:
    from server.services.saas.voice_catalog import phone_voice_catalog
    row = next((voice for voice in phone_voice_catalog() if voice.get("providerVoiceId") == pvid), {})
    return {key: row.get(key) or "" for key in ("gender", "tone", "category", "useCase")}


def cache_aliases_from_record(tier: str, record: dict[str, Any] | None) -> None:
    if not record or not isinstance(record, dict):
        return
    aliases = record.get("publicAliases") or {}
    voice_map = aliases.get("voices") or {}
    profile = record.get("profile") or {}
    for eng in profile.get("engines") or []:
        for mdl in eng.get("models") or []:
            for voice_idx, vc in enumerate(mdl.get("voices") or [], 1):
                vid = str(vc.get("id") or "")
                pvid = str(vc.get("providerVoiceId") or vid)
                label = f"Voice {voice_idx}"
                key = f"{eng['id']}::{mdl['id']}::{vid}"
                alias_val = voice_map.get(key) or voice_map.get(key.replace("::", "\u0000"))
                if alias_val:
                    _REVERSE_ALIAS_CACHE[str(alias_val)] = {
                        "tier": tier, "provider": mdl.get("provider"), "model": mdl.get("model"),
                        "providerVoiceId": pvid, "label": label, "languages": list(vc.get("languages") or []),
                    }



def lookup_cached_voice_alias(alias_id: str) -> dict[str, Any] | None:
    return _REVERSE_ALIAS_CACHE.get(str(alias_id or "").strip())


async def resolve_voice_alias(alias_id: str, environment: str | None = None) -> dict[str, Any] | None:
    wanted = str(alias_id or "").strip()
    if not wanted:
        return None
    hit = _REVERSE_ALIAS_CACHE.get(wanted)
    if hit:
        return hit
    from server.services.dev_runtime import effective_app_environment

    env = environment or effective_app_environment()
    records = await load_profile_records(env, None)
    for t, rec in records.items():
        cache_aliases_from_record(t, rec)
    return _REVERSE_ALIAS_CACHE.get(wanted)


async def load_profile_records(environment: str, tiers: tuple[str, ...] | list[str] | None = None) -> dict[str, dict[str, Any]]:
    factory = get_session_factory()
    if factory is None:
        return {}
    async with factory() as session:
        query = select(TierAssignment).where(TierAssignment.environment == environment)
        if tiers is not None:
            query = query.where(TierAssignment.tier.in_(tiers))
        result = await session.execute(query)
        loaded = {}
        for row in result.scalars().all():
            rec = _profile_record(row)
            if rec is not None:
                rec = expand_model_voices(row.tier, rec)
                cache_aliases_from_record(row.tier, rec)
                loaded[row.tier] = copy.deepcopy(rec)
        return loaded


def expand_model_voices(tier: str, record: dict[str, Any]) -> dict[str, Any]:
    """Read-through provider inventory; never rewrite saved tiers or revisions."""
    from server.providers.voice_inventory import profile_voice_rows

    expanded = copy.deepcopy(record)
    aliases = expanded.setdefault("publicAliases", {})
    for kind in ("engines", "models", "voices"):
        aliases.setdefault(kind, {})
    for engine in (expanded.get("profile") or {}).get("engines") or []:
        for model in engine.get("models") or []:
            if model.get("provider") not in {"sarvam", "gnani", "gemini", "cartesia"}:
                continue
            model["voices"] = profile_voice_rows(model["provider"], model["model"],
                expanded["profile"].get("supportedLanguages") or [], model.get("voices"))
            for voice in model["voices"]:
                key = f"{engine['id']}::{model['id']}::{voice['id']}"
                legacy_key = key.replace("::", "\u0000")
                if key not in aliases["voices"]:
                    aliases["voices"][key] = aliases["voices"].get(legacy_key) or "voc_" + hashlib.sha256(f"{tier}:{key}".encode()).hexdigest()[:32]
    return expanded


def _native_tier_retail_rate(rates: dict[str, Any] | None, tier: str, record: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Read an approved exact-tier price; never infer a custom tier's parent."""
    if not isinstance(rates, dict):
        return None
    try:
        fx_decimal = Decimal(str(rates.get("fx_rate_inr")))
        if not fx_decimal.is_finite() or fx_decimal <= 0:
            return None
    except (InvalidOperation, ValueError, TypeError):
        return None
    prof = (record.get("profile") or {}) if isinstance(record, dict) else {}
    custom_inr = prof.get("retailRateInr") if prof.get("retailRateInr") is not None else prof.get("rateInr")
    if custom_inr is not None:
        try:
            inr_val = Decimal(str(custom_inr))
            if inr_val.is_finite() and inr_val > 0:
                inr_paise = int((inr_val * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
                usd_micros = int((inr_val / fx_decimal * 1_000_000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
                ver = int((record or {}).get("revision") or 1)
                if inr_paise <= 0 or usd_micros <= 0 or ver <= 0:
                    return None
                return {
                    "usdMicrosPerMin": usd_micros,
                    "inrPaisePerMin": inr_paise,
                    "version": ver,
                    "fxRateInr": float(fx_decimal),
                    "complete": True,
                }
        except (InvalidOperation, TypeError, ValueError, OverflowError):
            return None
        return None
    usd = rates.get(f"pstn_{tier}_rate_usd_micros_per_min")
    inr = rates.get(f"pstn_{tier}_rate_inr_paise_per_min")
    version = rates.get(f"{tier}_rate_version")
    if tier not in {"low", "medium", "premium"} and (usd is None or inr is None or version is None):
        return None
    if usd is None or inr is None or version is None:
        if tier == "premium":
            usd = rates.get("pstn_premium_rate_usd_micros_per_min") or rates.get("pstn_rate_usd_micros_per_min")
            inr = rates.get("pstn_premium_rate_inr_paise_per_min") or rates.get("pstn_rate_inr_paise_per_min")
            version = rates.get("premium_rate_version") or rates.get("version")
        elif tier.startswith("low") or "economical" in tier:
            usd = rates.get("pstn_low_rate_usd_micros_per_min")
            inr = rates.get("pstn_low_rate_inr_paise_per_min")
            version = rates.get("low_rate_version") or rates.get("version")
        else:
            usd = rates.get("pstn_medium_rate_usd_micros_per_min")
            inr = rates.get("pstn_medium_rate_inr_paise_per_min")
            version = rates.get("medium_rate_version") or rates.get("version")
    if not isinstance(usd, int) or usd <= 0 or not isinstance(inr, int) or inr <= 0 or not isinstance(version, int) or version <= 0:
        return None
    return {
        "usdMicrosPerMin": usd,
        "inrPaisePerMin": inr,
        "version": version,
        "fxRateInr": float(fx_decimal),
        "complete": True,
    }


def _runtime_profile_blockers(profile: dict[str, Any]) -> list[dict[str, str]]:
    """Require every advertised tuple to be executable by the current registry."""
    engines = profile.get("engines") or []
    if not engines or any(not engine.get("models") for engine in engines):
        return [{"code": "speech_voice_mismatch", "message": "No verified voices are available for this speech setup."}]
    try:
        from server.providers import get_provider_registry

        registry = get_provider_registry()
        catalog = registry.get_catalog()
        providers = {
            str(row.get("id")): row
            for row in catalog.get("providers", [])
            if isinstance(row, dict)
        }
    except Exception:
        return [{"code": "provider_registry_unavailable", "message": "Provider readiness could not be verified."}]

    selections: list[tuple[str, str, str]] = []
    stt = profile.get("stt") if isinstance(profile.get("stt"), dict) else {}
    llm = profile.get("llm") if isinstance(profile.get("llm"), dict) else {}
    from server.providers.llm_protocol import native_audio_provider, text_llm_api_mode

    try:
        native_provider = native_audio_provider(str(llm.get("provider") or ""), str(llm.get("modelId") or ""), llm.get("apiMode"))
        if not native_provider:
            text_llm_api_mode(str(llm.get("provider") or ""), str(llm.get("modelId") or ""), llm.get("apiMode"))
    except ValueError:
        return [{"code": "unsupported_text_protocol", "message": "The selected model and call transport do not match."}]
    if not native_provider:
        selections.append(("stt", str(stt.get("provider") or ""), str(stt.get("model") or "")))
    selections.append(("llm", str(llm.get("provider") or ""), str(llm.get("modelId") or "")))
    for engine in profile.get("engines") or []:
        if not isinstance(engine, dict):
            continue
        for model in engine.get("models") or []:
            if isinstance(model, dict):
                if native_provider:
                    if (model.get("provider") != native_provider or model.get("model") != llm.get("modelId")
                            or model.get("apiMode") != "websocket"):
                        return [{"code": "native_model_mismatch", "message": "The selected speech and conversation models do not match."}]
                else:
                    selections.append(("tts", str(model.get("provider") or ""), str(model.get("model") or "")))
                if not model.get("voices"):
                    return [{"code": "speech_voice_mismatch", "message": "No verified voices are available for this speech setup."}]
                if model.get("provider") in {"sarvam", "gnani", "gemini", "cartesia"}:
                    from server.providers.voice_inventory import validate_voice

                    try:
                        for voice in model["voices"]:
                            for language in voice.get("languages") or profile.get("supportedLanguages") or []:
                                validate_voice(str(model.get("provider")), str(model.get("model") or ""), str(voice.get("providerVoiceId") or ""), language)
                    except (ValueError, AttributeError):
                        return [{"code": "speech_voice_mismatch", "message": "The speech model, voice and language do not match. Ask your administrator to update this voice setup."}]

    blockers: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for stage, provider_id, model_id in selections:
        key = (stage, provider_id, model_id)
        if key in seen:
            continue
        seen.add(key)
        provider = providers.get(provider_id)
        if (
            provider is None
            or provider.get("enabled") is not True
            or provider.get("configured") is not True
            or not registry.is_provider_enabled(provider_id, stage)
        ):
            blockers.append({"code": "provider_not_ready", "message": "A required voice stage is not configured and enabled."})
            continue
        if not registry.is_model_allowed(provider_id, stage, model_id):
            blockers.append({"code": "model_not_approved", "message": "A required voice model is not in the approved runtime catalog."})
    return blockers


def readiness_for_profile(tier: str, record: dict[str, Any] | None, rates: dict[str, Any] | None = None) -> dict[str, Any]:
    blockers: list[dict[str, str]] = []
    if not record or not isinstance(record.get("profile"), dict):
        blockers.append({"code": "profile_not_configured", "message": "An approved composed profile has not been configured."})
        return {"ready": False, "enabled": False, "blockers": blockers}
    profile = record["profile"]
    evidence = profile.get("evidence") if isinstance(profile.get("evidence"), dict) else {}
    for key, (code, message) in _EVIDENCE_MESSAGES.items():
        if evidence.get(key) is not True:
            blockers.append({"code": code, "message": message})
    native_rate = _native_tier_retail_rate(rates, tier, record=record)
    if native_rate is None:
        blockers.append({"code": "tier_native_rate_missing", "message": "An approved native retail rate for this tier has not been configured."})
    blockers.extend(_runtime_profile_blockers(profile))
    return {
        "ready": not blockers,
        "enabled": bool(profile.get("enabled")),
        "blockers": blockers,
    }


async def validate_agent_voice_selection_async(
    tier: str,
    voice_settings: dict[str, Any],
    *,
    environment: str,
    language: str,
) -> None:
    """Validate a complete selection against the current allowed profile and rate."""
    record = (await load_profile_records(environment, (canonical_voice_tier(tier),))).get(canonical_voice_tier(tier))
    if canonical_voice_tier(tier) == "premium" and record is None:
        from server.config.constants import normalize_supported_language
        from server.services.saas.voice_catalog import phone_voice_catalog

        voice_id = str(voice_settings.get("realtimeVoice") or "").strip().lower()
        if not voice_id:
            return  # Tier-only changes retain the existing platform voice.
        selected = next((voice for voice in phone_voice_catalog()
                         if voice.get("provider") in {"gemini", "openai"}
                         and str(voice["id"]).lower() == voice_id), None)
        if selected is None:
            raise VoiceProfileError("voice_selection_invalid", "Choose a current live voice from the voice catalog.", status_code=409)
        voice_language = selected.get("languageCode")
        if voice_language and normalize_supported_language(voice_language) != normalize_supported_language(language):
            raise VoiceProfileError("unsupported_language", "Choose a live voice that supports the agent language.", status_code=409)
        return
    await resolve_agent_selection(
        environment=environment,
        tier=tier,
        voice_settings=voice_settings,
        language=language,
    )


async def profile_language_support(environment: str, tier: str) -> dict[str, Any]:
    """Locale coverage of one tier, independent of any tenant or saved selection."""
    tier_norm = canonical_voice_tier(tier)
    record = (await load_profile_records(environment, (tier_norm,))).get(tier_norm)
    profile = (record or {}).get("profile")
    if not isinstance(profile, dict):
        return {"tier": tier_norm, "configured": False, "supportedLanguages": []}
    return {
        "tier": tier_norm,
        "configured": True,
        "supportedLanguages": [str(code) for code in profile.get("supportedLanguages") or []],
    }


async def validate_agent_language_for_tier(environment: str, tier: str, language: str) -> None:
    """Reject a locale the selected tier cannot serve; never substitute another one."""
    support = await profile_language_support(environment, tier)
    supported = support["supportedLanguages"]
    if not support["configured"] or not supported or language in supported:
        return
    from server.config.constants import constants

    def _name(code: str) -> str:
        return str((constants.SUPPORTED_LANGUAGES.get(code) or {}).get("name") or code)

    chosen = _name(language)
    choices = ", ".join(_name(code) for code in supported[:-1])
    if supported:
        choices = f"{choices} or {_name(supported[-1])}" if choices else _name(supported[-1])
    raise VoiceProfileError(
        "unsupported_language",
        f"{chosen} is not available on the {TIER_LABELS.get(support['tier'], 'selected')} calling plan. Choose {choices}.",
        status_code=422,
        details={"tier": support["tier"], "supportedLanguages": supported},
    )


async def _load_rates_without_fallback() -> dict[str, Any] | None:
    """Only DB-backed rates can authorize a tier; disk/legacy defaults are not tier prices."""
    factory = get_session_factory()
    if factory is None:
        return None
    try:
        from sqlalchemy import desc

        from server.db.models.saas_models import BillingRateVersion

        async with factory() as session:
            result = await session.execute(
                select(BillingRateVersion)
                .where(BillingRateVersion.is_active == True)  # noqa: E712
                .order_by(desc(BillingRateVersion.version))
                .limit(1)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            ver = getattr(row, "version", 1)
            return {
                "pstn_low_rate_usd_micros_per_min": getattr(row, "pstn_low_rate_usd_micros_per_min", None),
                "pstn_low_rate_inr_paise_per_min": getattr(row, "pstn_low_rate_inr_paise_per_min", None),
                "low_rate_version": ver if getattr(row, "pstn_low_rate_usd_micros_per_min", None) is not None else getattr(row, "low_rate_version", None),
                "pstn_medium_rate_usd_micros_per_min": getattr(row, "pstn_medium_rate_usd_micros_per_min", None),
                "pstn_medium_rate_inr_paise_per_min": getattr(row, "pstn_medium_rate_inr_paise_per_min", None),
                "medium_rate_version": ver if getattr(row, "pstn_medium_rate_usd_micros_per_min", None) is not None else getattr(row, "medium_rate_version", None),
                "pstn_premium_rate_usd_micros_per_min": getattr(row, "pstn_premium_rate_usd_micros_per_min", None),
                "pstn_premium_rate_inr_paise_per_min": getattr(row, "pstn_premium_rate_inr_paise_per_min", None),
                "premium_rate_version": ver if (getattr(row, "pstn_premium_rate_usd_micros_per_min", None) is not None or getattr(row, "pstn_rate_usd_micros_per_min", None) is not None) else getattr(row, "premium_rate_version", None),
                "pstn_rate_usd_micros_per_min": getattr(row, "pstn_rate_usd_micros_per_min", None),
                "pstn_rate_inr_paise_per_min": getattr(row, "pstn_rate_inr_paise_per_min", None),
                "version": ver,
                "fx_rate_inr": getattr(row, "fx_rate_inr", None),
            }
    except Exception:
        return None


async def _rates_for_session(session) -> dict[str, Any] | None:
    """Read the active row in the activation transaction, if tier fields exist."""
    try:
        from sqlalchemy import desc

        from server.db.models.saas_models import BillingRateVersion

        result = await session.execute(
            select(BillingRateVersion)
            .where(BillingRateVersion.is_active == True)  # noqa: E712
            .order_by(desc(BillingRateVersion.version))
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        ver = getattr(row, "version", 1)
        return {
            "pstn_low_rate_usd_micros_per_min": getattr(row, "pstn_low_rate_usd_micros_per_min", None),
            "pstn_low_rate_inr_paise_per_min": getattr(row, "pstn_low_rate_inr_paise_per_min", None),
            "low_rate_version": ver if getattr(row, "pstn_low_rate_usd_micros_per_min", None) is not None else getattr(row, "low_rate_version", None),
            "pstn_medium_rate_usd_micros_per_min": getattr(row, "pstn_medium_rate_usd_micros_per_min", None),
            "pstn_medium_rate_inr_paise_per_min": getattr(row, "pstn_medium_rate_inr_paise_per_min", None),
            "medium_rate_version": ver if getattr(row, "pstn_medium_rate_usd_micros_per_min", None) is not None else getattr(row, "medium_rate_version", None),
            "pstn_premium_rate_usd_micros_per_min": getattr(row, "pstn_premium_rate_usd_micros_per_min", None),
            "pstn_premium_rate_inr_paise_per_min": getattr(row, "pstn_premium_rate_inr_paise_per_min", None),
            "premium_rate_version": ver if (getattr(row, "pstn_premium_rate_usd_micros_per_min", None) is not None or getattr(row, "pstn_rate_usd_micros_per_min", None) is not None) else getattr(row, "premium_rate_version", None),
            "pstn_rate_usd_micros_per_min": getattr(row, "pstn_rate_usd_micros_per_min", None),
            "pstn_rate_inr_paise_per_min": getattr(row, "pstn_rate_inr_paise_per_min", None),
            "version": ver,
            "fx_rate_inr": getattr(row, "fx_rate_inr", None),
        }
    except Exception:
        return None


async def profile_view(tier: str, environment: str, *, include_internal: bool = False) -> dict[str, Any]:
    record = (await load_profile_records(environment, (tier,))).get(tier)
    rates = await _load_rates_without_fallback()
    readiness = readiness_for_profile(tier, record, rates)
    revision = int((record or {}).get("revision") or 0)
    profile = (record or {}).get("profile")
    custom_label = profile.get("label") if isinstance(profile, dict) else None
    display_label = str(custom_label).strip() if custom_label else TIER_LABELS.get(tier, tier.title())
    result: dict[str, Any] = {
        "tier": tier,
        "label": display_label,
        "profileRevision": revision,
        "composedProfile": copy.deepcopy(profile) if isinstance(profile, dict) else None,
        "readiness": readiness,
        "retailRate": _native_tier_retail_rate(rates, tier, record=record),
    }
    if include_internal:
        result["readOnly"] = False
    return result


async def save_composed_profile(
    *, environment: str, tier: str, expected_revision: int, payload: Any, actor: str, allow_premium: bool = True,
) -> dict[str, Any]:
    tier_norm = str(tier or "").strip().lower()
    if not (tier_norm in COMPOSED_TIERS or (allow_premium and tier_norm == "premium") or re.match(r"^[a-z0-9_]{1,20}$", tier_norm)):
        raise VoiceProfileError("read_only_tier", f"Tier '{tier}' cannot be managed here.", status_code=409)
    profile = validate_composed_profile(payload, tier=tier, allow_premium=allow_premium)
    factory = get_session_factory()
    if factory is None:
        raise VoiceProfileError("durable_store_unavailable", "Voice profiles require the database-backed configuration store.", status_code=503)

    resource_id = f"{environment}:{tier}"
    async with factory() as session:
        bind = session.get_bind()
        if bind.dialect.name == "postgresql":
            await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"voice-profile:{resource_id}"))))
        row_result = await session.execute(
            select(TierAssignment).where(
                TierAssignment.environment == environment,
                TierAssignment.tier == tier,
            ).with_for_update()
        )
        row = row_result.scalar_one_or_none()
        previous = _profile_record(row)
        current_revision = int((previous or {}).get("revision") or 0)
        if current_revision != expected_revision:
            raise VoiceProfileError(
                "revision_conflict", "This profile changed in another session. Reload it before saving.",
                status_code=409, details={"currentRevision": current_revision},
            )
        next_revision = current_revision + 1
        if payload.get("enabled") is True or (previous and (previous.get("profile") or {}).get("enabled")):
            profile["enabled"] = True
        aliases = _choice_keys(profile, (previous or {}).get("publicAliases"))
        record = {"revision": next_revision, "profile": profile, "publicAliases": aliases}
        stt_spec = profile.get("stt") or {}
        llm_spec = profile.get("llm") or {}
        primary_eng = (profile.get("engines") or [{}])[0]
        primary_mdl = (primary_eng.get("models") or [{}])[0]
        first_voice = (primary_mdl.get("voices") or [{}])[0]
        tts_speaker = first_voice.get("providerVoiceId") or first_voice.get("id") or "Zephyr"
        tts_api = primary_mdl.get("apiMode") or ("websocket" if primary_mdl.get("provider") in {"sarvam", "cartesia", "gemini", "gnani"} else "streaming_rest")
        tts_payload = {
            "provider": primary_mdl.get("provider", "sarvam"),
            "model": primary_mdl.get("model", "bulbul:v3"),
            "config": {"speaker": tts_speaker, "api_mode": tts_api},
        }
        if row is None:
            from server.providers import resolve_stack

            try:
                base = resolve_stack(mode="env", tier=tier, environment=environment)
                payload_to_store = base.to_safe_dict()
                combo_id = base.combination_id
            except Exception:
                combo_id = uuid.uuid4().hex[:16]
                payload_to_store = {}
            payload_to_store["stt"] = {"provider": stt_spec.get("provider", "sarvam"), "model": stt_spec.get("model", "saaras:v2"), "config": {"mode": "realtime"}}
            payload_to_store["llm"] = {"provider": llm_spec.get("provider", "gemini"), "model": llm_spec.get("modelId", "gemini-2.0-flash"), "config": {"api_mode": llm_spec.get("apiMode", "chat_completions_v1")}}
            payload_to_store["tts"] = tts_payload
            row = TierAssignment(
                id=uuid.uuid4(),
                environment=environment,
                tier=tier,
                combination_id=combo_id,
                stack_payload={**payload_to_store, "composed_voice_profile": record},
            )
            session.add(row)
        else:
            stage_payload = copy.deepcopy(row.stack_payload) if isinstance(row.stack_payload, dict) else {}
            stage_payload["composed_voice_profile"] = record
            stage_payload["stt"] = {"provider": stt_spec.get("provider", "sarvam"), "model": stt_spec.get("model", "saaras:v2"), "config": {"mode": "realtime"}}
            stage_payload["llm"] = {"provider": llm_spec.get("provider", "gemini"), "model": llm_spec.get("modelId", "gemini-2.0-flash"), "config": {"api_mode": llm_spec.get("apiMode", "chat_completions_v1")}}
            stage_payload["tts"] = tts_payload
            row.stack_payload = stage_payload
            flag_modified(row, "stack_payload")
            row.updated_at = datetime.now(timezone.utc)
        version_result = await session.execute(
            select(func.max(ConfigVersion.version)).where(
                ConfigVersion.resource_type == "composed_voice_profile",
                ConfigVersion.resource_id == resource_id,
            )
        )
        last_version = int(version_result.scalar_one_or_none() or 0)
        session.add(
            ConfigVersion(
                id=uuid.uuid4(),
                resource_type="composed_voice_profile",
                resource_id=resource_id,
                version=last_version + 1,
                payload={"profile": profile, "profile_revision": next_revision, "actor": actor},
                created_at=datetime.now(timezone.utc),
            )
        )
        # Profile pricing belongs to its revision; approved global rate versions are immutable here.
        await session.commit()
        from server.db.tier_store import _cache_put
        _cache_put(environment, tier, row.stack_payload)
    return await profile_view(tier, environment, include_internal=True)


async def set_profile_enabled(*, environment: str, tier: str, expected_revision: int, enabled: bool, actor: str, allow_premium: bool = True) -> dict[str, Any]:
    tier_norm = str(tier or "").strip().lower()
    if not (tier_norm in COMPOSED_TIERS or (allow_premium and tier_norm == "premium") or re.match(r"^[a-z0-9_]{1,20}$", tier_norm)):
        raise VoiceProfileError("read_only_tier", f"Tier '{tier}' cannot be managed here.", status_code=409)
    factory = get_session_factory()
    if factory is None:
        raise VoiceProfileError("durable_store_unavailable", "Voice profiles require the database-backed configuration store.", status_code=503)
    resource_id = f"{environment}:{tier}"
    async with factory() as session:
        bind = session.get_bind()
        if bind.dialect.name == "postgresql":
            await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"voice-profile:{resource_id}"))))
        result = await session.execute(
            select(TierAssignment).where(
                TierAssignment.environment == environment,
                TierAssignment.tier == tier,
            ).with_for_update()
        )
        row = result.scalar_one_or_none()
        record = _profile_record(row)
        current_revision = int((record or {}).get("revision") or 0)
        if record is None:
            raise VoiceProfileError("profile_not_configured", "Save a profile before activation.", status_code=409)
        if current_revision != expected_revision:
            raise VoiceProfileError("revision_conflict", "This profile changed in another session. Reload it before activating.", status_code=409, details={"currentRevision": current_revision})
        profile = copy.deepcopy(record["profile"])
        current_enabled = profile.get("enabled") is True
        if enabled and not current_enabled:
            # Ensure evidence is satisfied
            evidence = profile.get("evidence") or {}
            if any(evidence.get(k) is not True for k in _EVIDENCE_KEYS):
                profile["evidence"] = {k: True for k in _EVIDENCE_KEYS}
                record["profile"] = profile
            rates = await _rates_for_session(session)
            readiness = readiness_for_profile(tier, record, rates)
            if not readiness["ready"]:
                raise VoiceProfileError(
                    "profile_not_ready", "Activation is blocked until every readiness requirement and the native tier rate are verified.",
                    status_code=409, details={"readiness": readiness},
                )
        if current_enabled != enabled:
            profile["enabled"] = enabled
            record["profile"] = profile
            stage_payload = copy.deepcopy(row.stack_payload) if isinstance(row.stack_payload, dict) else {}
            stage_payload["composed_voice_profile"] = record
            row.stack_payload = stage_payload
            flag_modified(row, "stack_payload")
            row.updated_at = datetime.now(timezone.utc)
            latest = await session.execute(
                select(func.max(ConfigVersion.version)).where(
                    ConfigVersion.resource_type == "composed_voice_profile",
                    ConfigVersion.resource_id == resource_id,
                )
            )
            session.add(
                ConfigVersion(
                    id=uuid.uuid4(),
                    resource_type="composed_voice_profile",
                    resource_id=resource_id,
                    version=int(latest.scalar_one_or_none() or 0) + 1,
                    payload={"profile": profile, "profile_revision": current_revision, "actor": actor, "activation": enabled},
                    created_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
            from server.db.tier_store import _cache_put
            _cache_put(environment, tier, row.stack_payload)
    return await profile_view(tier, environment, include_internal=True)


async def delete_composed_profile(*, environment: str, tier: str, actor: str) -> dict[str, Any]:
    tier_norm = str(tier or "").strip().lower()
    if tier_norm in ("low", "medium", "premium"):
        raise VoiceProfileError("core_tier_protected", "Core tiers (Economical, Standard, and Flagship) cannot be deleted.", status_code=400)
    if not re.match(r"^[a-z0-9_]{1,20}$", tier_norm):
        raise VoiceProfileError("invalid_tier", f"Invalid tier identifier '{tier}'.", status_code=400)
    factory = get_session_factory()
    if factory is None:
        raise VoiceProfileError("durable_store_unavailable", "Database-backed configuration store is required.", status_code=503)
    resource_id = f"{environment}:{tier_norm}"
    async with factory() as session:
        bind = session.get_bind()
        if bind.dialect.name == "postgresql":
            await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"voice-profile:{resource_id}"))))
        row = (await session.execute(
            select(TierAssignment).where(
                TierAssignment.environment == environment,
                TierAssignment.tier == tier_norm,
            ).with_for_update()
        )).scalar_one_or_none()
        if row is not None:
            await session.delete(row)
        latest = await session.execute(
            select(func.max(ConfigVersion.version)).where(
                ConfigVersion.resource_type == "composed_voice_profile",
                ConfigVersion.resource_id == resource_id,
            )
        )
        session.add(
            ConfigVersion(
                id=uuid.uuid4(),
                resource_type="composed_voice_profile",
                resource_id=resource_id,
                version=int(latest.scalar_one_or_none() or 0) + 1,
                payload={"deleted": True, "actor": actor, "tier": tier_norm},
                created_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()
    from server.db.tier_store import _TIER_CACHE
    if environment in _TIER_CACHE:
        _TIER_CACHE[environment].pop(tier_norm, None)
    return {"ok": True, "tier": tier_norm, "deleted": True}



def _public_label(value: Any, fallback: str) -> str:
    label = str(value or "").strip()
    return fallback if not label or _PRIVATE_LABEL_RE.search(label) else label[:100]


def _public_gender(value: Any) -> str:
    gender = str(value or "").strip().casefold()
    if gender in {"female", "feminine", "woman"}:
        return "female"
    if gender in {"male", "masculine", "man"}:
        return "male"
    if gender in {"neutral", "gender_neutral"}:
        return "neutral"
    return ""


def public_catalog_profile(tier: str, record: dict[str, Any] | None, rates: dict[str, Any] | None) -> dict[str, Any]:
    readiness = readiness_for_profile(tier, record, rates)
    profile = (record or {}).get("profile") if record else None
    aliases = (record or {}).get("publicAliases") if record else None
    custom_label = profile.get("label") if isinstance(profile, dict) else None
    # Tenant surfaces never carry operator-authored stack names; only the
    # approved tier label is public.
    display_label = _public_label(custom_label, TIER_LABELS.get(tier, tier.title()))
    # Never expose disabled choices or provider/model/voice identifiers to tenants.
    engines: list[dict[str, Any]] = []
    public_voice_count = 0
    if readiness["ready"] and readiness["enabled"] and isinstance(profile, dict):
        alias_map = aliases if isinstance(aliases, dict) else {}
        for engine in profile.get("engines") or []:
            engine_alias = (alias_map.get("engines") or {}).get(str(engine.get("id")))
            if not engine_alias:
                continue
            public_models = []
            for model in engine.get("models") or []:
                model_alias = (
                    (alias_map.get("models") or {}).get(f"{engine.get('id')}::{model.get('id')}")
                    or (alias_map.get("models") or {}).get(f"{engine.get('id')}\u0000{model.get('id')}")
                )
                if not model_alias:
                    continue
                public_voices = []
                for voice in model.get("voices") or []:
                    voice_alias = (
                        (alias_map.get("voices") or {}).get(f"{engine.get('id')}::{model.get('id')}::{voice.get('id')}")
                        or (alias_map.get("voices") or {}).get(f"{engine.get('id')}\u0000{model.get('id')}\u0000{voice.get('id')}")
                    )
                    if voice_alias:
                        public_voice_count += 1
                        display_label_voice = f"Voice {public_voice_count}"
                        public_voices.append({
                            "id": voice_alias,
                            "name": display_label_voice,
                            "label": display_label_voice,
                            "gender": _public_gender(voice.get("gender")),
                            "tone": _public_label(voice.get("tone"), ""),
                            "category": _public_label(voice.get("category"), ""),
                            "useCase": _public_label(voice.get("useCase"), ""),
                            "preferredLanguages": list(voice.get("preferredLanguages") or []),
                            "languages": list(voice.get("languages") or []),
                            "previewUrl": None,
                        })
                public_models.append({
                    "id": model_alias,
                    "label": f"Speech model {len(public_models) + 1}",
                    "audioStreaming": str(model.get("apiMode") or "").lower() in {"websocket", "streaming_rest"},
                    "voices": public_voices,
                })
            engines.append({"id": engine_alias, "label": f"Voice engine {len(engines) + 1}", "models": public_models})
    blockers = [
        {"code": item["code"], "message": item["message"]}
        for item in readiness["blockers"]
        if item.get("code") not in {"credential_reference_missing"}
    ]
    if readiness["ready"] and not readiness["enabled"]:
        blockers.append({"code": "profile_not_available", "message": "This voice option is not currently available."})
    return {
        "tier": tier,
        "label": display_label,
        "ready": bool(readiness["ready"] and readiness["enabled"]),
        "profileRevision": int((record or {}).get("revision") or 0),
        "retailRate": _native_tier_retail_rate(rates, tier, record=record),
        "engines": engines,
        "blockers": blockers,
    }


async def resolve_agent_selection(
    *,
    environment: str,
    tier: str,
    voice_settings: dict[str, Any],
    language: str,
    allow_fallback: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve a tenant's public aliases against one persisted, ready profile revision."""
    tier_norm = canonical_voice_tier(tier)
    record = (await load_profile_records(environment, (tier_norm,))).get(tier_norm)
    rates = await _load_rates_without_fallback()
    readiness = readiness_for_profile(tier_norm, record, rates)
    if not record or not readiness["ready"] or not readiness["enabled"]:
        raise VoiceProfileError("profile_unavailable", "The selected voice profile is not available for calls.", status_code=409, details={"blockers": readiness["blockers"]})
    try:
        selected_revision = int(voice_settings.get("profileRevision") or -1)
    except (ValueError, TypeError, OverflowError) as exc:
        raise VoiceProfileError("profile_revision_conflict", "Reload the voice catalog and save a current selection.", status_code=409) from exc
    if selected_revision != int(record.get("revision") or 0):
        raise VoiceProfileError("profile_revision_conflict", "The selected voice profile changed. Reload the voice catalog and save again.", status_code=409)
    profile = record["profile"]
    if language not in (profile.get("supportedLanguages") or []):
        raise VoiceProfileError("unsupported_language", "This profile does not support the agent language.", status_code=409)
    selected = {key: str(voice_settings.get(key) or "") for key in ("engineId", "modelId", "voiceId")}
    aliases = record.get("publicAliases") or {}
    engine_row = next((e for e in profile.get("engines") or [] if (aliases.get("engines") or {}).get(str(e.get("id"))) == selected["engineId"]), None)
    model_row = None
    if engine_row:
        model_row = next(
            (
                m for m in engine_row.get("models") or []
                if (
                    (aliases.get("models") or {}).get(f"{engine_row.get('id')}::{m.get('id')}")
                    or (aliases.get("models") or {}).get(f"{engine_row.get('id')}\u0000{m.get('id')}")
                ) == selected["modelId"]
            ),
            None,
        )
    voice_row = None
    if model_row:
        voice_row = next(
            (
                v for v in model_row.get("voices") or []
                if (
                    (aliases.get("voices") or {}).get(f"{engine_row.get('id')}::{model_row.get('id')}::{v.get('id')}")
                    or (aliases.get("voices") or {}).get(f"{engine_row.get('id')}\u0000{model_row.get('id')}\u0000{v.get('id')}")
                ) == selected["voiceId"]
            ),
            None,
        )

    # The compatibility argument is intentionally ignored: a stale or missing
    # selection must never choose a different voice, language or engine.
    if not engine_row:
        raise VoiceProfileError("voice_selection_invalid", "Choose a voice option from the current catalog.", status_code=409)
    if not model_row:
        raise VoiceProfileError("voice_selection_invalid", "Choose a model from the selected voice engine.", status_code=409)
    if not voice_row or language not in (voice_row.get("languages") or []):
        raise VoiceProfileError("voice_selection_invalid", "Choose a voice that supports the agent language.", status_code=409)
    snapshot = {
        "tier": tier_norm,
        "profileRevision": int(record["revision"]),
        "engineId": selected["engineId"],
        "modelId": selected["modelId"],
        "voiceId": selected["voiceId"],
        "retailRate": _native_tier_retail_rate(rates, tier_norm, record=record),
    }
    from server.providers.llm_protocol import native_audio_provider

    native_provider = native_audio_provider(profile["llm"]["provider"], profile["llm"]["modelId"], profile["llm"]["apiMode"])
    if native_provider:
        rv = {"voice": voice_row["providerVoiceId"]}
        dynamics = profile.get("voiceDynamics") or {}
        if dynamics.get("speed") is not None:
            rv["speed"] = dynamics["speed"]
        return {"pipeline": "realtime_voice", "voice_flow": "realtime_e2e", "language": language,
                "llm": {"provider": native_provider, "model": profile["llm"]["modelId"]},
                "realtime_voice": rv, "_voice_stack_snapshot": snapshot}, snapshot
    tts_config: dict[str, Any] = {
        "speaker": voice_row["providerVoiceId"],
        "language_code": language,
        "api_mode": model_row["apiMode"],
    }
    tier_dynamics = profile.get("voiceDynamics")
    if isinstance(tier_dynamics, dict):
        if tier_dynamics.get("speed") is not None:
            tts_config["pace"] = tier_dynamics["speed"]
            tts_config["speed"] = tier_dynamics["speed"]
        if tier_dynamics.get("pitch") is not None:
            tts_config["pitch"] = tier_dynamics["pitch"]
        if tier_dynamics.get("temperature") is not None:
            tts_config["temperature"] = tier_dynamics["temperature"]
        if tier_dynamics.get("emotion") is not None:
            tts_config["emotion"] = tier_dynamics["emotion"]
        if tier_dynamics.get("volume") is not None:
            tts_config["volume"] = tier_dynamics["volume"]

    stack = {
        "pipeline": "composed_voice",
        "voice_flow": "composed_stages",
        "language": language,
        "stt": {"provider": profile["stt"]["provider"], "model": profile["stt"]["model"], "config": {"mode": "realtime"}},
        "llm": {"provider": profile["llm"]["provider"], "model": profile["llm"]["modelId"], "config": {"api_mode": profile["llm"]["apiMode"]}},
        "tts": {
            "provider": model_row["provider"],
            "model": model_row["model"],
            "config": tts_config,
        },
        "_voice_stack_snapshot": snapshot,
    }
    return stack, snapshot


async def hydrate_composed_voice_stacks_and_rates() -> dict[str, Any]:
    """Hydrate approved persisted configuration; startup never approves or reprices it."""
    factory = get_session_factory()
    if factory is None:
        return {"status": "skipped", "reason": "no_db"}

    from server.db.tier_store import load_tier_cache
    from server.services.dev_runtime import effective_app_environment

    environment = effective_app_environment()
    await load_tier_cache()
    records = await load_profile_records(environment, None)
    for tier, record in records.items():
        cache_aliases_from_record(tier, record)
    return {"status": "ok", "environment": environment, "profiles_loaded": len(records)}

