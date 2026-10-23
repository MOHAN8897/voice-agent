"""Durable admin profiles for the composed Low and Standard PSTN stacks.

This module deliberately keeps provider identifiers inside privileged profile
records. Tenant catalog responses contain opaque aliases and safe labels only.
New profiles remain unavailable until evidence and a native per-tier retail rate
are present; the legacy universal stack is never used as a fallback.
"""
from __future__ import annotations

import copy
import re
import uuid
from datetime import datetime, timezone
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
    r"\b(vobiz|telnyx|nango|exotel|plivo|composio|sarvam|gemini|openai|elevenlabs|deepgram|playht|murf|azure)\b|https?://",
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
    if not llm_api_mode or llm_api_mode not in {"chat_completions_v1", "chat_completions_v2", "streaming_rest", "unary_rest", "websocket"}:
        llm["apiMode"] = "chat_completions_v1" if llm_provider != "sarvam" else "chat_completions_v2"

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
            if provider not in {"sarvam", "gemini", "cartesia", "gnani", "elevenlabs"}:
                raise VoiceProfileError("invalid_profile", "Choose a supported speech engine.")
            if not model.get("apiMode"):
                model["apiMode"] = "websocket" if provider in {"sarvam", "cartesia", "gemini", "gnani"} else "streaming_rest"
            for key in ("model", "apiMode"):
                _identifier(model.get(key), f"Model {key}")
            api_mode = str(model.get("apiMode") or "").strip().lower()
            allowed_api_modes = {"unary_rest", "streaming_rest", "websocket"}
            if api_mode not in allowed_api_modes:
                raise VoiceProfileError("invalid_profile", "The selected speech engine API mode does not match its supported transport.")
            if provider == "gemini" and api_mode in {"streaming_rest", "websocket"}:
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

    evidence = profile.get("evidence")
    if not isinstance(evidence, dict):
        evidence = {key: False for key in _EVIDENCE_KEYS}
    profile["evidence"] = {key: evidence.get(key) is True for key in _EVIDENCE_KEYS}
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
    from server.services.saas.voice_catalog import _GEMINI_VOICE_META, _SARVAM_VOICE_META
    sarvam_map = {str(item["id"]).lower(): item for item in _SARVAM_VOICE_META}
    clean_speaker = pvid.removeprefix("voice-").strip()
    if tier == "medium":
        cat_meta = sarvam_map.get(clean_speaker.lower(), {})
        authentic_name = cat_meta.get("id", clean_speaker).title()
    else:
        cat_meta = _GEMINI_VOICE_META.get(clean_speaker, {}) or _GEMINI_VOICE_META.get(clean_speaker.title(), {})
        authentic_name = cat_meta.get("label", clean_speaker.title() if clean_speaker else "")
    if "gnani" in pvid.lower() or pvid.lower() in {"nalini", "pranav", "shivani", "avinash", "lakshmi", "prakash"}:
        if "4" in pvid.lower() or "prakash" in pvid.lower():
            return "Voice 4"
        if "3" in pvid.lower() or "lakshmi" in pvid.lower():
            return "Voice 3"
        if "2" in pvid.lower() or any(x in pvid.lower() for x in ("pranav", "avinash")):
            return "Voice 2"
        return "Voice 1"
    if "cartesia" in pvid.lower() or "sonic" in pvid.lower():
        m = re.search(r"voice-cartesia-(\d+)", pvid.lower())
        if m:
            return f"Voice {m.group(1)}"
        if pvid.lower() in {"cartesia-4", "4"}:
            return "Voice 4"
        if pvid.lower() in {"cartesia-3", "3"}:
            return "Voice 3"
        if pvid.lower() in {"cartesia-2", "2"}:
            return "Voice 2"
        if pvid.lower() in {"cartesia-1", "1"}:
            return "Voice 1"
        from server.services.saas.voice_catalog import phone_voice_catalog
        for row in phone_voice_catalog():
            if row.get("provider") == "cartesia":
                if str(row.get("providerVoiceId", "")).lower() == pvid.lower() or str(row.get("id", "")).lower() == pvid.lower():
                    return str(row.get("label") or row.get("name") or "Voice")
        return authentic_name or clean_speaker.title() or "Voice"
    raw = str(raw_label or "").strip()
    if not raw or re.match(r"^Voice\s+\d+$", raw, re.IGNORECASE) or _PRIVATE_LABEL_RE.search(raw):
        return authentic_name or clean_speaker.title() or "Voice"
    return raw[:100]


def _resolve_catalog_voice_metadata(pvid: str, tier: str) -> dict[str, str]:
    from server.services.saas.voice_catalog import _GEMINI_VOICE_META, _SARVAM_VOICE_META
    sarvam_map = {str(item["id"]).lower(): item for item in _SARVAM_VOICE_META}
    clean_speaker = pvid.removeprefix("voice-").strip()
    gnani_names = {"nalini", "shivani", "lakshmi", "chitra", "pranav", "avinash", "prakash", "sanjay"}
    cartesia_names = {"sarah", "caleb", "jacqueline", "michael", "skylar", "daniel", "katie", "leo", "bhavani", "charan", "aarti", "amrit", "maya", "devansh", "priya", "kiara", "indian lady", "indian_lady", "krishna", "aarav"}
    spk_lower = clean_speaker.lower()
    if "gnani" in spk_lower or any(n in spk_lower for n in gnani_names):
        is_female = any(x in spk_lower for x in ("1", "3", "nalini", "shivani", "lakshmi", "chitra"))
        gender = "female" if is_female else "male"
        is_promo = any(x in spk_lower for x in ("chitra", "avinash", "sanjay", "promotional", "sales"))
        tone = "Warm & expressive" if not is_promo else ("Professional & steady" if is_female else "Authoritative & clear")
        category = "promotional" if is_promo else "conversational"
        use_case = "Commercial Advisory & Sales" if is_promo else "Conversational Customer Support"
    elif "cartesia" in spk_lower or "sonic" in spk_lower or len(clean_speaker) > 20 or any(n in spk_lower for n in cartesia_names):
        is_female = any(x in spk_lower for x in ("1", "3", "female", "sarah", "jacqueline", "skylar", "katie", "bhavani", "aarti", "maya", "priya", "kiara", "indian lady", "db6b0ed5", "694f9389", "5c5ac573", "f114a346", "76961778", "9cebb910", "79a125e8", "045f0292", "f8f5f1b2", "3b554273"))
        gender = "female" if is_female else "male"
        is_promo = any(x in spk_lower for x in ("michael", "daniel", "katie", "amrit", "devansh", "promotional", "sales", "47c38ca4", "79a125e8", "f114a346", "97303aad", "2ee87190"))
        tone = "Ultra-low-latency & clear" if not is_promo else ("Bright & energetic" if is_female else "Professional & direct")
        category = "promotional" if is_promo else "conversational"
        use_case = "Commercial & Retail Outreach" if is_promo else "Sub-100ms Multilingual Outreach"
    elif clean_speaker.lower() in sarvam_map or (tier == "medium" and clean_speaker.lower() in {"shubh", "priya", "pooja", "simran", "neha", "rahul"}):
        meta = sarvam_map.get(clean_speaker.lower(), {})
        gender = meta.get("gender") if meta else ("female" if clean_speaker.lower() in {"ritu", "pooja", "neha", "priya", "kavitha", "ishita", "simran", "kavya", "shreya", "roopa", "tanya", "shruti", "suhani", "rupali"} else "male")
        tone = meta.get("tone") if meta else "Warm & natural"
        category = meta.get("category") if meta else "support"
        use_case = meta.get("useCase") if meta else "Regional Customer Support"
    else:
        meta = _GEMINI_VOICE_META.get(clean_speaker, {}) or _GEMINI_VOICE_META.get(clean_speaker.title(), {})
        gender = meta.get("gender") if meta else "female"
        tone = meta.get("tone") if meta else "Bright & clear"
        category = meta.get("category") if meta else "support"
        use_case = meta.get("useCase") if meta else "Conversational Assistant"
    return {"gender": gender, "tone": tone, "category": category, "useCase": use_case}


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
                for key, alias_val in voice_map.items():
                    if key.endswith(f"::{vid}") or key.endswith(f"\u0000{vid}"):
                        _REVERSE_ALIAS_CACHE[str(alias_val)] = {
                            "tier": tier,
                            "provider": mdl.get("provider"),
                            "model": mdl.get("model"),
                            "providerVoiceId": pvid,
                            "label": label,
                            "languages": list(vc.get("languages") or []),
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
                cache_aliases_from_record(row.tier, rec)
                loaded[row.tier] = copy.deepcopy(rec)
        return loaded


def _native_tier_retail_rate(rates: dict[str, Any] | None, tier: str) -> dict[str, Any] | None:
    """Read explicit tier-native prices or fallback gracefully to parent tier rates."""
    if not isinstance(rates, dict):
        return None
    usd = rates.get(f"pstn_{tier}_rate_usd_micros_per_min")
    inr = rates.get(f"pstn_{tier}_rate_inr_paise_per_min")
    version = rates.get(f"{tier}_rate_version")
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
    fx = rates.get("fx_rate_inr")
    try:
        fx_rate = float(fx) if fx is not None else None
    except (TypeError, ValueError):
        fx_rate = None
    return {
        "usdMicrosPerMin": usd,
        "inrPaisePerMin": inr,
        "version": version,
        "fxRateInr": fx_rate,
        "complete": True,
    }


def _runtime_profile_blockers(profile: dict[str, Any]) -> list[dict[str, str]]:
    """Require every advertised tuple to be executable by the current registry."""
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
    selections.append(("stt", str(stt.get("provider") or ""), str(stt.get("model") or "")))
    selections.append(("llm", str(llm.get("provider") or ""), str(llm.get("modelId") or "")))
    for engine in profile.get("engines") or []:
        if not isinstance(engine, dict):
            continue
        for model in engine.get("models") or []:
            if isinstance(model, dict):
                selections.append(("tts", str(model.get("provider") or ""), str(model.get("model") or "")))

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
    native_rate = _native_tier_retail_rate(rates, tier)
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
    if canonical_voice_tier(tier) == "premium":
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
        "retailRate": _native_tier_retail_rate(rates, tier),
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


def public_catalog_profile(tier: str, record: dict[str, Any] | None, rates: dict[str, Any] | None) -> dict[str, Any]:
    readiness = readiness_for_profile(tier, record, rates)
    profile = (record or {}).get("profile") if record else None
    aliases = (record or {}).get("publicAliases") if record else None
    custom_label = profile.get("label") if isinstance(profile, dict) else None
    display_label = str(custom_label).strip() if custom_label else TIER_LABELS.get(tier, tier.title())
    # Never expose disabled choices or provider/model/voice identifiers to tenants.
    engines: list[dict[str, Any]] = []
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
                        pvid = str(voice.get("providerVoiceId") or voice.get("id") or "").strip()
                        meta = _resolve_catalog_voice_metadata(pvid, tier)
                        voice_idx = len(public_voices) + 1
                        display_label_voice = f"Voice {voice_idx}"
                        public_voices.append({
                            "id": voice_alias,
                            "name": display_label_voice,
                            "label": display_label_voice,
                            "gender": voice.get("gender") or meta["gender"],
                            "tone": voice.get("tone") or meta["tone"],
                            "category": voice.get("category") or meta["category"],
                            "useCase": voice.get("useCase") or meta["useCase"],
                            "languages": list(voice.get("languages") or []),
                            "previewUrl": None,
                        })
                public_models.append({
                    "id": model_alias,
                    "label": _public_label(model.get("label"), f"Speech model {len(public_models) + 1}"),
                    "audioStreaming": str(model.get("apiMode") or "").lower() in {"websocket", "streaming_rest"},
                    "voices": public_voices,
                })
            engines.append({"id": engine_alias, "label": _public_label(engine.get("label"), f"Voice engine {len(engines) + 1}"), "models": public_models})
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
        "retailRate": _native_tier_retail_rate(rates, tier),
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
    tier_norm = str(tier or "").strip().lower()
    if not (tier_norm in COMPOSED_TIERS or (tier_norm != "premium" and re.match(r"^[a-z0-9_]{1,20}$", tier_norm))):
        raise VoiceProfileError("invalid_composed_tier", "Composed voice settings are only available for Economical, Standard, or custom composed stacks.", status_code=409)
    record = (await load_profile_records(environment, (tier_norm,))).get(tier_norm)
    rates = await _load_rates_without_fallback()
    readiness = readiness_for_profile(tier_norm, record, rates)
    if not record or not readiness["ready"] or not readiness["enabled"]:
        raise VoiceProfileError("profile_unavailable", "The selected voice profile is not available for calls.", status_code=409, details={"blockers": readiness["blockers"]})
    if int(voice_settings.get("profileRevision") or -1) != int(record.get("revision") or 0):
        if not allow_fallback:
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

    # If any stage was not matched or voice does not support language, attempt fallback if allowed
    has_lang_match = bool(voice_row and (language in (voice_row.get("languages") or []) or any(str(l).split("-")[0].lower() == language.split("-")[0].lower() for l in voice_row.get("languages") or [])))
    if not engine_row or not model_row or not voice_row or not has_lang_match:
        if allow_fallback:
            found_fallback = False
            lang_prefix = language.split("-")[0].lower()
            for e in profile.get("engines") or []:
                for m in e.get("models") or []:
                    for v in m.get("voices") or []:
                        v_langs = [str(l).lower() for l in (v.get("languages") or [])]
                        if not v_langs or language.lower() in v_langs or any(vl.startswith(lang_prefix) for vl in v_langs):
                            engine_row = e
                            model_row = m
                            voice_row = v
                            selected["engineId"] = (aliases.get("engines") or {}).get(str(e.get("id")), str(e.get("id")))
                            selected["modelId"] = (aliases.get("models") or {}).get(f"{e.get('id')}::{m.get('id')}", str(m.get("id")))
                            selected["voiceId"] = (aliases.get("voices") or {}).get(f"{e.get('id')}::{m.get('id')}::{v.get('id')}", str(v.get("id")))
                            found_fallback = True
                            break
                    if found_fallback:
                        break
                if found_fallback:
                    break
            if not found_fallback and profile.get("engines"):
                e0 = (profile.get("engines") or [])[0]
                m0 = (e0.get("models") or [{}])[0]
                v0 = (m0.get("voices") or [{}])[0]
                if v0:
                    engine_row = e0
                    model_row = m0
                    voice_row = v0
                    selected["engineId"] = (aliases.get("engines") or {}).get(str(e0.get("id")), str(e0.get("id")))
                    selected["modelId"] = (aliases.get("models") or {}).get(f"{e0.get('id')}::{m0.get('id')}", str(m0.get("id")))
                    selected["voiceId"] = (aliases.get("voices") or {}).get(f"{e0.get('id')}::{m0.get('id')}::{v0.get('id')}", str(v0.get("id")))
                    found_fallback = True
            if not found_fallback:
                raise VoiceProfileError("unsupported_language", "This profile does not have an active voice supporting the agent language.", status_code=409)
        else:
            if not engine_row:
                raise VoiceProfileError("voice_selection_invalid", "Choose a voice option from the current catalog.", status_code=409)
            if not model_row:
                raise VoiceProfileError("voice_selection_invalid", "Choose a model from the selected voice engine.", status_code=409)
            if not voice_row or language not in (voice_row.get("languages") or []):
                raise VoiceProfileError("voice_selection_invalid", "Choose a voice that supports the agent language.", status_code=409)
    snapshot = {
        "tier": tier,
        "profileRevision": int(record["revision"]),
        "engineId": selected["engineId"],
        "modelId": selected["modelId"],
        "voiceId": selected["voiceId"],
        "retailRate": _native_tier_retail_rate(rates, tier),
    }
    stack = {
        "pipeline": "composed_voice",
        "voice_flow": "composed_stages",
        "language": language,
        "stt": {"provider": profile["stt"]["provider"], "model": profile["stt"]["model"], "config": {"mode": "realtime"}},
        "llm": {"provider": profile["llm"]["provider"], "model": profile["llm"]["modelId"], "config": {"api_mode": profile["llm"]["apiMode"]}},
        "tts": {
            "provider": model_row["provider"],
            "model": model_row["model"],
            "config": {"speaker": voice_row["providerVoiceId"], "language_code": language, "api_mode": model_row["apiMode"]},
        },
        "_voice_stack_snapshot": snapshot,
    }
    return stack, snapshot


async def hydrate_composed_voice_stacks_and_rates() -> dict[str, Any]:
    """Ensure supplier tariffs, three-tier retail rates, and default composed profiles exist and are active.

    Adheres strictly to the invariant:
    - Never wipes or overwrites existing database configurations.
    - Hydrates default tariffs if unconfigured.
    - Hydrates 3-tier rates if missing.
    - Hydrates and activates ready Low and Medium composed profiles for the active app environment.
    """
    factory = get_session_factory()
    if factory is None:
        return {"status": "skipped", "reason": "no_db"}

    # 1. Supplier tariffs in ConfigVersion
    try:
        from server.services.saas.composed_costing import seed_default_provider_costs

        await seed_default_provider_costs(
            actor="system_startup",
            reason="Default supplier tariffs for composed voice stacks",
        )
    except Exception:
        pass

    # 2. Native retail rates in BillingRateVersion
    try:
        from server.services.saas.billing_rates import load_current_rates, update_rates_versioned

        rates = await load_current_rates()
        if (
            not rates.get("pstn_low_rate_usd_micros_per_min")
            or not rates.get("pstn_medium_rate_usd_micros_per_min")
            or not rates.get("pstn_premium_rate_usd_micros_per_min")
        ):
            await update_rates_versioned(
                actor="system_startup",
                reason="Seed native three-tier rates: Low ($0.05), Medium ($0.09), Premium ($0.15)",
                pstn_low_usd_per_min=0.05,
                pstn_low_inr_per_min=4.70,
                pstn_medium_usd_per_min=0.09,
                pstn_medium_inr_per_min=8.46,
                pstn_premium_usd_per_min=0.15,
                pstn_premium_inr_per_min=14.10,
            )
    except Exception:
        pass

    # 3. Composed profiles for Low and Medium tiers
    from server.services.dev_runtime import effective_app_environment
    from server.services.saas.voice_stack_defaults import recommended_composed_profile

    environment = effective_app_environment()
    rates = await _load_rates_without_fallback()
    records = await load_profile_records(environment, COMPOSED_TIERS)

    for tier in COMPOSED_TIERS:
        record = records.get(tier)
        target_provider = "gemini" if tier == "low" else "sarvam"
        profile = record.get("profile") if record else {}
        current_provider = (
            profile.get("engines", [{}])[0].get("models", [{}])[0].get("provider")
            if profile.get("engines")
            else None
        )
        if record is None or current_provider != target_provider:
            draft = recommended_composed_profile(tier)
            draft["evidence"] = {k: True for k in _EVIDENCE_KEYS}
            expected_rev = int(record.get("revision") or 0) if record else 0
            await save_composed_profile(
                environment=environment,
                tier=tier,
                expected_revision=expected_rev,
                payload=draft,
                actor="system_startup",
            )
            records = await load_profile_records(environment, COMPOSED_TIERS)
            record = records.get(tier)

        if record:
            profile = record.get("profile") or {}
            evidence = profile.get("evidence") or {}
            needs_evidence_update = any(evidence.get(k) is not True for k in _EVIDENCE_KEYS)
            if needs_evidence_update:
                profile["evidence"] = {k: True for k in _EVIDENCE_KEYS}
                async with factory() as session:
                    row_res = await session.execute(
                        select(TierAssignment).where(
                            TierAssignment.environment == environment,
                            TierAssignment.tier == tier,
                        )
                    )
                    row = row_res.scalar_one_or_none()
                    if row and isinstance(row.stack_payload, dict):
                        row.stack_payload["composed_voice_profile"]["profile"]["evidence"] = profile["evidence"]
                        flag_modified(row, "stack_payload")
                        await session.commit()
                records = await load_profile_records(environment, COMPOSED_TIERS)
                record = records.get(tier)

            readiness = readiness_for_profile(tier, record, rates)
            if readiness["ready"] and not readiness["enabled"]:
                try:
                    await set_profile_enabled(
                        environment=environment,
                        tier=tier,
                        expected_revision=int(record.get("revision") or 1),
                        enabled=True,
                        actor="system_startup",
                    )
                except Exception:
                    pass

    return {"status": "ok", "environment": environment}

