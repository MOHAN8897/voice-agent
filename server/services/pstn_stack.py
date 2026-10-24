"""PSTN stack validation and safe normalization for telephony calls.

Test scripts dial with tier-only (no stack_override). Dev panel may send custom stacks;
this module auto-fixes common PSTN mismatches and returns clear errors for unfixable combos.
Browser /call/start is unchanged — PSTN only.
"""
from __future__ import annotations

import copy
from typing import Any

from server.config.constants import coerce_supported_language, constants
from server.services.cartesia_voices import is_cartesia_voice_id


class PstnStackValidationError(ValueError):
    """Raised when a PSTN stack cannot be made safe for telephony."""

    def __init__(self, message: str, *, details: list[str] | None = None):
        super().__init__(message)
        self.details = details or []


def _deep_get(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return cur if cur is not None else default


def _set_nested(root: dict[str, Any], section: str, key: str, value: Any) -> None:
    block = root.setdefault(section, {})
    if not isinstance(block, dict):
        block = {}
        root[section] = block
    block[key] = value


def _default_sarvam_speaker(language: str, model: str) -> str:
    from server.providers.voice_inventory import default_voice

    return default_voice("sarvam", model, language)


def _default_cartesia_voice_id(language: str, model: str) -> str:
    from server.providers.voice_inventory import default_voice

    return default_voice("cartesia", model, language)


def _cartesia_stt_ok(model: str, language: str) -> bool:
    if model == "ink-whisper":
        return True
    if model == "ink-2" and language.startswith("en"):
        return True
    return False


def _is_realtime_voice_override(out: dict[str, Any]) -> bool:
    pipeline = str(out.get("pipeline") or "").strip().lower()
    if pipeline in ("realtime_text", "classic"):
        return False
    voice_flow = str(out.get("voice_flow") or "").strip().lower()
    return pipeline in ("realtime_voice", "realtime_e2e") or voice_flow in (
        "realtime_e2e",
        "realtime_voice",
    )


def _normalize_realtime_voice_override(
    out: dict[str, Any],
    adjustments: list[str],
    *,
    language: str = "te-IN",
    default_provider: str = "openai",
) -> tuple[dict[str, Any], list[str]]:
    """Audio-to-audio Realtime PSTN — no Sarvam STT/TTS; preserve the chosen provider."""
    from server.realtime.models import (
        DEFAULT_GEMINI_LIVE_MODEL,
        DEFAULT_REALTIME_MODEL,
        DEFAULT_REALTIME_TURN_DETECTION,
        DEFAULT_REALTIME_VOICE,
        REALTIME_VOICES,
        is_gemini_live_voice_model,
        is_realtime_llm_model,
        normalize_realtime_noise_reduction,
        normalize_realtime_silence_ms,
        normalize_realtime_speed,
        normalize_realtime_turn_detection,
        normalize_realtime_vad_eagerness,
        normalize_realtime_voice,
    )

    out["pipeline"] = "realtime_voice"
    out["voice_flow"] = "realtime_e2e"
    llm = out.get("llm")
    if not isinstance(llm, dict):
        llm = {}
        out["llm"] = llm
    provider = str(llm.get("provider") or "").strip().lower()
    model = str(llm.get("model") or "").strip()
    rv = out.get("realtime_voice")
    if not isinstance(rv, dict):
        rv = {}
        out["realtime_voice"] = rv
    raw_voice = str(rv.get("voice") or "").strip()
    voice_language = coerce_supported_language(str(out.get("language") or language or "te-IN"))
    from server.providers.voice_inventory import voices_for_model

    gemini_voice_ids = {row["providerVoiceId"].lower() for row in voices_for_model("gemini", model or DEFAULT_GEMINI_LIVE_MODEL)}
    explicit_provider = provider in {"openai", "gemini"}
    if provider and not explicit_provider:
        raise PstnStackValidationError("The selected provider does not support native audio calls")
    if model and ((provider == "gemini" and not is_gemini_live_voice_model(model))
                  or (provider == "openai" and not is_realtime_llm_model(model))
                  or (not provider and not is_gemini_live_voice_model(model) and not is_realtime_llm_model(model))):
        raise PstnStackValidationError("The selected model does not match the native audio provider")
    inferred_provider = (
        "gemini"
        if is_gemini_live_voice_model(model) or raw_voice.lower() in gemini_voice_ids
        else "openai"
        if model.lower().startswith("gpt-realtime") or provider == "openai"
        else default_provider
    )
    if not explicit_provider:
        provider = inferred_provider
    if provider == "gemini":
        llm["provider"] = "gemini"
        if not is_gemini_live_voice_model(model):
            llm["model"] = DEFAULT_GEMINI_LIVE_MODEL
            adjustments.append("llm.model set to gemini-3.8-live for Gemini Live PSTN")
    else:
        llm["provider"] = "openai"
        if not is_realtime_llm_model(model):
            llm["model"] = DEFAULT_REALTIME_MODEL
            adjustments.append("llm.model set to gpt-realtime-2.1-mini for Realtime PSTN")
    if llm.get("provider") == "gemini":
        from server.realtime.models import default_gemini_live_voice
        from server.realtime.providers.gemini_voice import normalize_gemini_live_voice

        # A stale OpenAI slug cannot describe a Gemini selection. Resolve it to
        # the language's regional Gemini default instead of mapping to Puck/Aoede.
        if raw_voice and raw_voice.lower() not in gemini_voice_ids:
            voice = default_gemini_live_voice(voice_language)
            adjustments.append(
                f"realtime voice '{raw_voice}' is not published for {llm.get('model')}; using '{voice}'"
            )
        elif raw_voice:
            voice = normalize_gemini_live_voice(raw_voice, str(llm.get("model") or ""))
        else:
            voice = default_gemini_live_voice(voice_language)
    else:
        if raw_voice and raw_voice.lower() not in {item.lower() for item in REALTIME_VOICES}:
            raise PstnStackValidationError("The selected voice does not belong to the native audio model")
        voice = normalize_realtime_voice(raw_voice)
    if raw_voice and raw_voice != voice and raw_voice.lower() != str(voice).lower():
        adjustments.append(f"realtime voice replaced with {voice}")
    rv["voice"] = voice or DEFAULT_REALTIME_VOICE
    td = normalize_realtime_turn_detection(rv.get("turn_detection"))
    if str(rv.get("turn_detection") or "").strip().lower() not in ("", td):
        adjustments.append(f"turn_detection set to {td}")
    rv["turn_detection"] = td or DEFAULT_REALTIME_TURN_DETECTION
    rv["vad_eagerness"] = normalize_realtime_vad_eagerness(rv.get("vad_eagerness"))
    rv["noise_reduction"] = normalize_realtime_noise_reduction(rv.get("noise_reduction"))
    rv["speed"] = normalize_realtime_speed(rv.get("speed"))
    rv["silence_ms"] = normalize_realtime_silence_ms(rv.get("silence_ms"))
    out.pop("stt", None)
    out.pop("tts", None)
    lang = voice_language
    if str(out.get("language") or "").strip() != lang:
        adjustments.append(f"language set to {lang} for PSTN realtime")
    out["language"] = lang
    from server.services.transcription_policy import normalize_transcription_block

    tx = out.get("transcription")
    out["transcription"] = normalize_transcription_block(tx if isinstance(tx, dict) else None, adjustments=adjustments)
    return out, adjustments


def normalize_pstn_stack_override(
    stack_override: dict[str, Any] | None,
    *,
    language: str = "te-IN",
    tier: str = "medium",
    default_provider: str = "openai",
) -> tuple[dict[str, Any] | None, list[str]]:
    """
    Return (sanitized_override, adjustments).
    sanitized_override is None when input was None/empty (tier-only dial — test scripts).
    """
    if not stack_override:
        return None, []

    language = coerce_supported_language(language)
    out = copy.deepcopy(stack_override)
    adjustments: list[str] = []

    # Versioned composed profiles already contain an exact, server-resolved
    # stage tuple. Preserve it intact: the legacy normalizer intentionally
    # removes LLM overrides and rewrites classic PSTN stacks to realtime_text.
    if str(out.get("pipeline") or "").strip().lower() == "composed_voice":
        if out.get("voice_flow") != "composed_stages":
            raise PstnStackValidationError("Invalid composed PSTN profile selection")
        snapshot = out.get("_voice_stack_snapshot")
        if not isinstance(snapshot, dict) or snapshot.get("tier") != tier:
            raise PstnStackValidationError("Composed PSTN profile snapshot is missing or inconsistent")
        for stage in ("stt", "llm", "tts"):
            selection = out.get(stage)
            if not isinstance(selection, dict):
                raise PstnStackValidationError(f"Composed PSTN {stage.upper()} selection is missing")
            if not str(selection.get("provider") or "").strip() or not str(selection.get("model") or "").strip():
                raise PstnStackValidationError(f"Composed PSTN {stage.upper()} provider/model must be explicit")
            if not isinstance(selection.get("config"), dict):
                raise PstnStackValidationError(f"Composed PSTN {stage.upper()} configuration is invalid")
        if str(out.get("language") or "").strip() != language:
            raise PstnStackValidationError("Composed PSTN language must match the admitted agent language")
        return out, adjustments

    if _is_realtime_voice_override(out):
        return _normalize_realtime_voice_override(
            out, adjustments, language=language, default_provider=default_provider
        )

    stt_provider = str(_deep_get(out, "stt", "provider") or "").strip().lower()
    stt_model = str(_deep_get(out, "stt", "model") or "").strip()
    tts_provider = str(_deep_get(out, "tts", "provider") or "").strip().lower()
    tts_model = str(_deep_get(out, "tts", "model") or "").strip()
    tts_speaker = str(_deep_get(out, "tts", "config", "speaker") or "").strip()

    # --- STT ---
    stt_block = out.get("stt")
    if isinstance(stt_block, dict):
        stt_inner = stt_block.get("config")
        if not isinstance(stt_inner, dict):
            stt_inner = {}
            stt_block["config"] = stt_inner
        if stt_inner.get("stream_type") not in constants.STT_STREAM_TYPES:
            stt_inner["stream_type"] = "fast"
            adjustments.append("stt.config.stream_type set to fast for PSTN")
        if stt_inner.get("mode") not in (None, "transcribe"):
            stt_inner["mode"] = "transcribe"
            adjustments.append("stt.config.mode set to transcribe for PSTN")

    if stt_provider == "sarvam" or (not stt_provider and stt_model in constants.STT_MODELS):
        if not stt_provider:
            _set_nested(out, "stt", "provider", "sarvam")
            adjustments.append("stt.provider set to sarvam")
        if stt_model == "saaras:v3":
            _set_nested(out, "stt", "model", "saaras:v3-realtime")
            adjustments.append("stt.model upgraded saaras:v3 → saaras:v3-realtime for PSTN")
        elif stt_model and stt_model not in constants.STT_MODELS:
            raise PstnStackValidationError(
                f"Unknown Sarvam STT model '{stt_model}' for PSTN",
                details=["Use saaras:v3-realtime for live PSTN STT"],
            )

    if stt_provider == "cartesia" or stt_model in constants.CARTESIA_STT_MODELS:
        if not stt_provider:
            _set_nested(out, "stt", "provider", "cartesia")
        model = stt_model or "ink-whisper"
        if model == "ink-2" and not language.startswith("en"):
            model = "ink-whisper"
            adjustments.append(f"stt.model ink-2 not valid for {language}; using ink-whisper")
        if not _cartesia_stt_ok(model, language):
            raise PstnStackValidationError(
                f"Cartesia STT model '{model}' is not valid for PSTN language {language}",
                details=["Telugu/Hindi PSTN requires ink-whisper"],
            )
        _set_nested(out, "stt", "model", model)

    # --- TTS ---
    if tts_provider == "cartesia" or tts_model in constants.CARTESIA_TTS_MODELS or str(tts_model).startswith("sonic"):
        if not tts_provider:
            _set_nested(out, "tts", "provider", "cartesia")
        if not tts_model or tts_model not in constants.CARTESIA_TTS_MODELS:
            if str(tts_model).startswith("sonic"):
                _set_nested(out, "tts", "model", "sonic-3.5")
                adjustments.append(f"tts.model {tts_model} is not published; using sonic-3.5")
            else:
                _set_nested(out, "tts", "model", "sonic-3.5")
                adjustments.append("tts.model set to sonic-3.5 for Cartesia PSTN")
        model = str(_deep_get(out, "tts", "model") or "sonic-3.5")
        from server.providers.voice_inventory import default_voice, validate_voice

        speaker = tts_speaker
        if speaker:
            try:
                validate_voice("cartesia", model, speaker, language)
            except ValueError:
                adjustments.append(
                    f"Cartesia TTS speaker '{speaker}' is not published for {model} in {language}; using the catalog default"
                )
                speaker = ""
        if not speaker:
            speaker = default_voice("cartesia", model, language)
        tts_block = out.setdefault("tts", {})
        if not isinstance(tts_block, dict):
            tts_block = {}
            out["tts"] = tts_block
        cfg = tts_block.setdefault("config", {})
        if not isinstance(cfg, dict):
            cfg = {}
            tts_block["config"] = cfg
        cfg["speaker"] = speaker

    elif tts_provider == "sarvam" or tts_model in constants.TTS_MODELS:
        if not tts_provider:
            _set_nested(out, "tts", "provider", "sarvam")
        model = tts_model or "bulbul:v3"
        if model not in constants.TTS_MODELS:
            raise PstnStackValidationError(f"Unknown Sarvam TTS model '{model}' for PSTN")
        _set_nested(out, "tts", "model", model)
        from server.providers.voice_inventory import default_voice, validate_voice

        speaker = tts_speaker
        if speaker and is_cartesia_voice_id(speaker):
            adjustments.append("Cartesia voice id removed from Sarvam TTS; using the catalog default")
            speaker = ""
        if speaker:
            try:
                validate_voice("sarvam", model, speaker, language)
            except ValueError:
                fallback = default_voice("sarvam", model, language)
                adjustments.append(
                    f"Sarvam TTS speaker '{speaker}' is not published for {model} in {language}; using '{fallback}'"
                )
                speaker = fallback
        else:
            speaker = default_voice("sarvam", model, language)
        tts_block = out.setdefault("tts", {})
        if isinstance(tts_block, dict):
            cfg = tts_block.setdefault("config", {})
            if isinstance(cfg, dict):
                cfg["speaker"] = speaker

    return _finalize_pstn_live_override(out, adjustments, language=language)


def _finalize_pstn_live_override(
    out: dict[str, Any],
    adjustments: list[str],
    *,
    language: str = "te-IN",
    default_provider: str = "openai",
) -> tuple[dict[str, Any], list[str]]:
    """PSTN realtime_text uses session fine-tune LLM; realtime_voice keeps dial-stack llm + voice."""
    if _is_realtime_voice_override(out):
        return _normalize_realtime_voice_override(
            out, adjustments, language=language, default_provider=default_provider
        )
    if out.get("llm"):
        out.pop("llm", None)
        adjustments.append(
            "llm override removed for PSTN (live uses OpenAI Realtime + test-studio fine-tune)"
        )
    if str(out.get("pipeline") or "").strip().lower() != "realtime_text":
        out["pipeline"] = "realtime_text"
        adjustments.append("pipeline set to realtime_text for PSTN live path")
    noise_reduction = out.get("noise_reduction")
    rv = out.get("realtime_voice")
    if noise_reduction is None and isinstance(rv, dict):
        noise_reduction = rv.get("noise_reduction")
    out.pop("voice_flow", None)
    out.pop("realtime_voice", None)
    if noise_reduction is not None:
        from server.realtime.models import normalize_realtime_noise_reduction

        out["noise_reduction"] = normalize_realtime_noise_reduction(noise_reduction)
    return out, adjustments


def validate_pstn_stack_override(
    stack_override: dict[str, Any] | None,
    *,
    language: str = "te-IN",
    tier: str = "medium",
) -> dict[str, Any]:
    """Normalize or raise PstnStackValidationError. None in → None out (tier-only)."""
    normalized, _ = normalize_pstn_stack_override(
        stack_override, language=language, tier=tier
    )
    return normalized


def prepare_pstn_dial_stack(
    stack_override: dict[str, Any] | None,
    *,
    language: str = "te-IN",
    tier: str = "medium",
) -> tuple[dict[str, Any] | None, list[str]]:
    """Used by dev telephony outbound before placing a PSTN call."""
    from server.prompts.agent_voice_rules import assert_spoken_pack_available

    assert_spoken_pack_available(language)
    return normalize_pstn_stack_override(stack_override, language=language, tier=tier)
