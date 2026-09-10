"""
Canonical TTS configuration — server/services/tts_config.py
Single resolver for env defaults + per-session runtime overrides.
Used by REST TTS, TTS WebSocket proxy, and voice turn pipeline.
"""
from __future__ import annotations

from typing import Any

from server.agent.language_resolver import get_speaker_for_language
from server.config.constants import constants
from server.config.env import get_settings
from server.services.runtime_settings import runtime_settings
from server.utils.logger import log_tts


class TtsConfigError(Exception):
    """Raised when speaker/model combination is invalid — never silently fall back."""

    def __init__(self, message: str, *, speaker: str | None = None):
        super().__init__(message)
        self.speaker = speaker


def _validate_speaker(model: str, speaker: str) -> None:
    ok = speaker in constants.TTS_SPEAKERS_V3 if model == "bulbul:v3" else speaker in constants.TTS_SPEAKERS_V2
    if not ok:
        raise TtsConfigError(
            f"Speaker '{speaker}' is incompatible with model '{model}'",
            speaker=speaker,
        )


def _stack_for_session(session_id: str, call_id: str | None, language_code: str):
    settings = get_settings()
    if not settings.use_provider_registry:
        return None
    if call_id:
        from server.call.call_context import get as get_call_ctx

        ctx = get_call_ctx(call_id)
        if ctx:
            return ctx.resolved_stack
    from server.providers import resolve_stack_for_session

    return resolve_stack_for_session(session_id, language=language_code)


def _is_cartesia_model(model: str) -> bool:
    return model in constants.CARTESIA_TTS_MODELS or str(model).startswith("sonic")


def _cartesia_available() -> bool:
    """True when Cartesia is enabled (env or dev_secrets) and an API key is present."""
    from server.services.dev_secrets_store import dev_secrets_store

    settings = get_settings()
    enabled = bool(dev_secrets_store.effective("enable_cartesia", settings.enable_cartesia))
    key = dev_secrets_store.effective_secret("cartesia_api_key") or (settings.cartesia_api_key or "")
    return enabled and bool(str(key).strip())


def _is_cartesia_stack(
    stack,
    rt: dict[str, Any],
    *,
    speaker: str | None,
    model: str | None,
) -> bool:
    from server.services.cartesia_voices import is_cartesia_voice_id

    if not _cartesia_available():
        return False

    if stack and stack.tts.provider == "cartesia":
        return True
    if stack and _is_cartesia_model(str(stack.tts.model or "")):
        return True
    rt_model = str(rt.get("ttsModel") or "")
    rt_speaker = str(rt.get("ttsSpeaker") or "")
    if _is_cartesia_model(rt_model):
        return True
    if is_cartesia_voice_id(rt_speaker):
        return True
    if speaker and is_cartesia_voice_id(str(speaker)):
        return True
    if model and _is_cartesia_model(str(model)):
        return True
    return False


def _effective_tts_model(
    *,
    stack,
    rt: dict[str, Any],
    explicit_model: str | None,
    settings,
) -> str:
    """Pick model without letting a Sarvam WS query param override a Cartesia stack."""
    if stack and _is_cartesia_stack(stack, rt, speaker=None, model=explicit_model):
        if _is_cartesia_model(str(stack.tts.model or "")):
            return str(stack.tts.model)
        rt_model = str(rt.get("ttsModel") or "")
        if _is_cartesia_model(rt_model):
            return rt_model
        if explicit_model and _is_cartesia_model(str(explicit_model)):
            return str(explicit_model)
        return settings.cartesia_tts_model or "sonic-3.5"
    if explicit_model:
        return explicit_model
    if stack and stack.tts.model:
        return str(stack.tts.model)
    return str(rt.get("ttsModel") or settings.sarvam_tts_model)


def _resolve_cartesia_tts_config(
    session_id: str,
    *,
    language_code: str,
    speaker: str | None,
    model: str | None,
    pace: float | None,
    sample_rate: int | None,
    stack,
    allow_runtime: bool = True,
) -> dict[str, Any]:
    settings = get_settings()
    rt = runtime_settings.get(session_id) if allow_runtime else {}
    resolved_model = model or (stack.tts.model if stack else None) or rt.get("ttsModel") or settings.cartesia_tts_model
    if not _is_cartesia_model(str(resolved_model)):
        resolved_model = settings.cartesia_tts_model or "sonic-3.5"

    stack_speaker = stack.tts.config.get("speaker") if stack and stack.tts.config else None
    resolved_speaker = speaker or rt.get("ttsSpeaker") or stack_speaker or settings.cartesia_tts_voice_id or constants.CARTESIA_DEFAULT_VOICE_ID

    from server.services.cartesia_voices import is_cartesia_voice_id

    if not is_cartesia_voice_id(str(resolved_speaker)):
        resolved_speaker = settings.cartesia_tts_voice_id or constants.CARTESIA_DEFAULT_VOICE_ID

    from server.services.tts_voice_direction import cartesia_generation_config

    resolved_sample_rate = int(sample_rate) if sample_rate is not None else int(rt.get("ttsSampleRate") or 24000)
    emotion = rt.get("ttsEmotion") or settings.cartesia_tts_emotion
    # Prefer Cartesia speed; fall back to explicit pace arg / runtime only when set.
    speed_raw = rt.get("ttsSpeed")
    if speed_raw is None and pace is not None:
        speed_raw = pace
    elif speed_raw is None and rt.get("ttsPace") is not None:
        speed_raw = rt.get("ttsPace")
    gen = cartesia_generation_config(
        emotion=str(emotion) if emotion else None,
        speed=float(speed_raw) if speed_raw is not None else None,
        volume=float(rt["ttsVolume"]) if rt.get("ttsVolume") is not None else None,
    )

    cfg: dict[str, Any] = {
        "provider": "cartesia",
        "model": resolved_model,
        "speaker": str(resolved_speaker),
        "pace": gen["speed"],
        "speed": gen["speed"],
        "volume": gen["volume"],
        "emotion": gen["emotion"],
        "generation_config": gen,
        "language_code": language_code if language_code in constants.SUPPORTED_LANGUAGES else "te-IN",
        "output_audio_codec": "linear16",
        "output_audio_bitrate": "128k",
        "sample_rate": resolved_sample_rate,
        "min_buffer_size": 30,
        "max_chunk_length": 80,
    }
    log_tts(
        "CONFIG",
        provider="cartesia",
        model=cfg["model"],
        speaker=cfg["speaker"],
        emotion=cfg["emotion"],
        speed=cfg["speed"],
        sample_rate=cfg["sample_rate"],
        session=session_id,
    )
    return cfg


def resolve_tts_config(
    session_id: str = "default",
    *,
    language_code: str = "te-IN",
    speaker: str | None = None,
    model: str | None = None,
    pace: float | None = None,
    temperature: float | None = None,
    codec: str | None = None,
    sample_rate: int | None = None,
    min_buffer_size: int | None = None,
    max_chunk_length: int | None = None,
    output_audio_bitrate: str | None = None,
    call_id: str | None = None,
    provider_override: str | None = None,
    resolved_stack: Any | None = None,
) -> dict[str, Any]:
    """
    Resolve the effective TTS configuration for a session.
    Active calls use their immutable resolved stack. Outside a call, priority is
    explicit argument → runtime override → provider stack → environment default.
    """
    settings = get_settings()
    rt = runtime_settings.get(session_id)
    stack = (
        resolved_stack or _stack_for_session(session_id, call_id, language_code)
        if provider_override is None
        else None
    )
    stack_is_locked = bool(stack is not None and (call_id or resolved_stack is not None))
    if stack_is_locked:
        # Session controls can change while a call is active (and can retain stale
        # values from a previous stack). Never let those values change the provider,
        # model, or voice recorded in this call's resolved-stack metadata.
        rt = {}
        model = None
        speaker = None
    if provider_override is not None:
        if provider_override != "sarvam":
            raise TtsConfigError(f"Unsupported TTS fallback provider: {provider_override}")
        # A fallback must not inherit the failed provider's model or voice ID.
        rt = {}
        model = settings.sarvam_tts_model
        speaker = None

    if provider_override is None and _is_cartesia_stack(stack, rt, speaker=speaker, model=model):
        resolved_model = _effective_tts_model(
            stack=stack,
            rt=rt,
            explicit_model=model,
            settings=settings,
        )
        return _resolve_cartesia_tts_config(
            session_id,
            language_code=language_code,
            speaker=speaker,
            model=resolved_model,
            pace=pace,
            sample_rate=sample_rate,
            stack=stack,
            allow_runtime=not stack_is_locked,
        )

    resolved_model = _effective_tts_model(
        stack=stack,
        rt=rt,
        explicit_model=model,
        settings=settings,
    )

    if resolved_model not in constants.TTS_MODELS:
        resolved_model = settings.sarvam_tts_model

    from server.services.cartesia_voices import is_cartesia_voice_id

    resolved_speaker = speaker or rt.get("ttsSpeaker")
    if resolved_speaker and is_cartesia_voice_id(str(resolved_speaker)):
        log_tts(
            "CARTESIA_SPEAKER_IGNORED",
            speaker=str(resolved_speaker)[:8],
            reason="cartesia unavailable or stack is sarvam",
            session=session_id,
        )
        resolved_speaker = None
    if not resolved_speaker:
        stack_speaker = stack.tts.config.get("speaker") if stack and stack.tts.config else None
        if stack_speaker and not is_cartesia_voice_id(str(stack_speaker)):
            resolved_speaker = stack_speaker
    if not resolved_speaker:
        if language_code == "te-IN":
            resolved_speaker = settings.sarvam_tts_speaker_te
        else:
            resolved_speaker = get_speaker_for_language(language_code)
    resolved_speaker = str(resolved_speaker).lower()

    try:
        _validate_speaker(resolved_model, resolved_speaker)
    except TtsConfigError:
        log_tts("SPEAKER_INVALID", speaker=resolved_speaker, model=resolved_model)
        raise

    resolved_pace = pace if pace is not None else rt.get("ttsPace", settings.sarvam_tts_pace)
    resolved_pace = float(resolved_pace)
    if resolved_model == "bulbul:v3":
        resolved_pace = max(0.5, min(2.0, resolved_pace))
    else:
        resolved_pace = max(0.3, min(3.0, resolved_pace))

    resolved_temp = temperature if temperature is not None else rt.get("ttsTemperature")
    if resolved_temp is None:
        resolved_temp = settings.sarvam_tts_temperature
    resolved_codec = codec or rt.get("ttsCodec") or "mp3"
    resolved_sample_rate = sample_rate or rt.get("ttsSampleRate") or 24000
    resolved_min_buf = min_buffer_size if min_buffer_size is not None else rt.get("ttsMinBuffer", 30)
    resolved_max_chunk = max_chunk_length if max_chunk_length is not None else rt.get("ttsMaxChunk", 80)
    resolved_bitrate = output_audio_bitrate or rt.get("ttsBitrate") or "128k"

    cfg: dict[str, Any] = {
        "provider": "sarvam",
        "model": resolved_model,
        "speaker": resolved_speaker,
        "pace": resolved_pace,
        "language_code": language_code if language_code in constants.SUPPORTED_LANGUAGES else "te-IN",
        "output_audio_codec": resolved_codec,
        "output_audio_bitrate": resolved_bitrate,
        "sample_rate": resolved_sample_rate,
        "min_buffer_size": int(resolved_min_buf),
        "max_chunk_length": int(resolved_max_chunk),
    }
    if resolved_temp is not None and resolved_model == "bulbul:v3":
        cfg["temperature"] = max(0.01, min(1.0, float(resolved_temp)))

    log_tts(
        "CONFIG",
        model=cfg["model"],
        speaker=cfg["speaker"],
        pace=cfg["pace"],
        temperature=cfg.get("temperature"),
        codec=cfg["output_audio_codec"],
        sample_rate=cfg["sample_rate"],
        session=session_id,
    )
    return cfg


def merge_ws_tts_config(
    session_id: str,
    client_data: dict | None,
    *,
    language_code: str = "te-IN",
    call_id: str | None = None,
    ws_model: str | None = None,
) -> dict[str, Any]:
    """Merge browser WS config payload with server-resolved runtime settings."""
    data = dict(client_data or {})
    cfg = resolve_tts_config(
        session_id,
        language_code=data.get("language_code") or language_code,
        speaker=None,
        model=ws_model,
        call_id=call_id,
        pace=data.get("pace"),
        temperature=data.get("temperature"),
        codec=data.get("output_audio_codec"),
        sample_rate=data.get("sample_rate"),
        min_buffer_size=data.get("min_buffer_size"),
        max_chunk_length=data.get("max_chunk_length"),
        output_audio_bitrate=data.get("output_audio_bitrate"),
    )
    # Browser PCM player cannot decode mp3/aac — streaming WS is always linear16.
    cfg["output_audio_codec"] = "linear16"
    return cfg


def merge_pstn_tts_config(
    session_id: str,
    client_data: dict | None = None,
    *,
    language_code: str = "te-IN",
    call_id: str | None = None,
    ws_model: str | None = None,
    wire_mode: str = "rtp_l16",
    resolved_stack: Any | None = None,
) -> dict[str, Any]:
    """Telephony TTS — L16 RTP @ 16 kHz (Telnyx) or μ-law RTP @ 8 kHz (Exotel/Plivo)."""
    data = dict(client_data or {})
    if wire_mode == "mp3":
        cfg = resolve_tts_config(
            session_id,
            language_code=data.get("language_code") or language_code,
            speaker=None,
            model=ws_model,
            call_id=call_id,
            resolved_stack=resolved_stack,
            pace=data.get("pace"),
            temperature=data.get("temperature"),
            codec="mp3",
            sample_rate=24000,
            min_buffer_size=data.get("min_buffer_size"),
            max_chunk_length=data.get("max_chunk_length"),
            output_audio_bitrate=data.get("output_audio_bitrate"),
        )
        cfg["output_audio_codec"] = "mp3"
        cfg["sample_rate"] = 24000
        log_tts(
            "CONFIG PSTN",
            provider=cfg.get("provider"),
            model=cfg.get("model"),
            speaker=cfg.get("speaker"),
            codec=cfg["output_audio_codec"],
            sample_rate=cfg["sample_rate"],
            session=session_id,
            call_id=call_id,
            wire_mode=wire_mode,
        )
        return cfg
    if wire_mode == "rtp_l16":
        speaker = data.get("speaker")
        from server.services.cartesia_voices import is_cartesia_voice_id

        locked_stack = resolved_stack or (
            _stack_for_session(session_id, call_id, language_code) if call_id else None
        )
        locked_cartesia = bool(
            locked_stack
            and (
                locked_stack.tts.provider == "cartesia"
                or _is_cartesia_model(str(locked_stack.tts.model or ""))
            )
        )
        if (
            speaker
            and is_cartesia_voice_id(str(speaker))
            and _cartesia_available()
            and (not locked_stack or locked_cartesia)
        ):
            cfg = _resolve_cartesia_tts_config(
                session_id,
                language_code=data.get("language_code") or language_code,
                speaker=str(speaker),
                model=ws_model or "sonic-3.5",
                pace=data.get("pace"),
                sample_rate=16000,
                stack=locked_stack,
                allow_runtime=not bool(locked_stack),
            )
            cfg["output_audio_codec"] = "linear16"
            cfg["speech_sample_rate"] = "16000"
            cfg["sample_rate"] = 16000
            cfg.pop("output_audio_bitrate", None)
            log_tts(
                "CONFIG PSTN",
                provider=cfg.get("provider"),
                model=cfg.get("model"),
                speaker=cfg.get("speaker"),
                codec=cfg["output_audio_codec"],
                speech_sample_rate=cfg["speech_sample_rate"],
                session=session_id,
                call_id=call_id,
                wire_mode=wire_mode,
            )
            return cfg
        cfg = resolve_tts_config(
            session_id,
            language_code=data.get("language_code") or language_code,
            speaker=data.get("speaker"),
            model=ws_model,
            call_id=call_id,
            resolved_stack=resolved_stack,
            pace=data.get("pace"),
            temperature=data.get("temperature"),
            codec="linear16",
            sample_rate=16000,
            min_buffer_size=data.get("min_buffer_size"),
            max_chunk_length=data.get("max_chunk_length"),
            output_audio_bitrate=data.get("output_audio_bitrate"),
        )
        cfg["output_audio_codec"] = "linear16"
        cfg["speech_sample_rate"] = "16000"
        cfg.pop("output_audio_bitrate", None)
        if cfg.get("provider") == "cartesia":
            cfg["sample_rate"] = 16000
        else:
            cfg.pop("sample_rate", None)
        log_tts(
            "CONFIG PSTN",
            provider=cfg.get("provider"),
            model=cfg.get("model"),
            speaker=cfg.get("speaker"),
            codec=cfg["output_audio_codec"],
            speech_sample_rate=cfg["speech_sample_rate"],
            session=session_id,
            call_id=call_id,
            wire_mode=wire_mode,
        )
        return cfg
    cfg = resolve_tts_config(
        session_id,
        language_code=data.get("language_code") or language_code,
        speaker=None,
        model=ws_model,
        call_id=call_id,
        resolved_stack=resolved_stack,
        pace=data.get("pace"),
        temperature=data.get("temperature"),
        codec="mulaw",
        sample_rate=8000,
        min_buffer_size=data.get("min_buffer_size"),
        max_chunk_length=data.get("max_chunk_length"),
        output_audio_bitrate=data.get("output_audio_bitrate"),
    )
    if cfg.get("provider") == "cartesia":
        cfg["output_audio_codec"] = "linear16"
        # Cartesia telephony path: generate 16 kHz PCM, then μ-law encode locally @ 8 kHz.
        cfg["speech_sample_rate"] = "16000"
        cfg["sample_rate"] = 16000
    else:
        # Request linear16 @ 8 kHz — we μ-law encode locally for Telnyx PCMU RTP.
        # Sarvam mulaw chunks are unreliable; local G.711 encode is deterministic.
        cfg["output_audio_codec"] = "linear16"
        cfg["speech_sample_rate"] = "8000"
        cfg.pop("sample_rate", None)
    # Sarvam WS expects speech_sample_rate (not sample_rate).
    cfg.pop("output_audio_bitrate", None)
    if cfg.get("provider") != "cartesia":
        cfg.pop("sample_rate", None)
    log_tts(
        "CONFIG PSTN",
        provider=cfg.get("provider"),
        model=cfg.get("model"),
        speaker=cfg.get("speaker"),
        codec=cfg["output_audio_codec"],
        speech_sample_rate=cfg["speech_sample_rate"],
        session=session_id,
        call_id=call_id,
        wire_mode=wire_mode,
    )
    return cfg
