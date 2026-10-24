"""
Canonical TTS configuration — server/services/tts_config.py
Single resolver for env defaults + per-session runtime overrides.
Used by REST TTS, TTS WebSocket proxy, and voice turn pipeline.
"""
from __future__ import annotations

from typing import Any

from server.agent.language_resolver import get_speaker_for_language
from server.config.constants import coerce_supported_language, constants, provider_language_code
from server.config.env import get_settings
from server.services.runtime_settings import runtime_settings
from server.utils.logger import log_tts


class TtsConfigError(Exception):
    """Raised when speaker/model combination is invalid — never silently fall back."""

    def __init__(self, message: str, *, speaker: str | None = None):
        super().__init__(message)
        self.speaker = speaker


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
    session_id: str | None,
    *,
    language_code: str,
    speaker: str | None,
    model: str | None,
    pace: float | None,
    sample_rate: int | None,
    stack,
    volume: float | None = None,
    emotion: str | None = None,
    allow_runtime: bool = True,
) -> dict[str, Any]:
    settings = get_settings()
    rt = runtime_settings.get(session_id) if allow_runtime and session_id is not None else {}
    resolved_model = model or (stack.tts.model if stack else None) or rt.get("ttsModel") or settings.cartesia_tts_model
    if not _is_cartesia_model(str(resolved_model)):
        raise TtsConfigError("The selected speech model is unavailable")

    stack_speaker = stack.tts.config.get("speaker") if stack and stack.tts.config else None
    configured_speaker = speaker or rt.get("ttsSpeaker") or stack_speaker
    from server.services.cartesia_voices import is_cartesia_voice_id
    from server.providers.voice_inventory import default_voice, validate_voice

    if configured_speaker and not is_cartesia_voice_id(str(configured_speaker)):
        raise TtsConfigError("Choose a voice from the selected speech model's catalog")
    if configured_speaker:
        try:
            resolved_speaker = validate_voice("cartesia", str(resolved_model), str(configured_speaker), language_code)["providerVoiceId"]
        except ValueError as exc:
            raise TtsConfigError(str(exc)) from exc
    else:
        preferred = settings.cartesia_tts_voice_id
        resolved_speaker = default_voice(
            "cartesia", str(resolved_model), language_code, preferred=str(preferred) if preferred else None
        )

    from server.services.tts_voice_direction import cartesia_generation_config

    resolved_sample_rate = int(sample_rate) if sample_rate is not None else int(rt.get("ttsSampleRate") or 24000)
    stack_config = (stack.tts.config or {}) if stack else {}
    emotion = emotion or rt.get("ttsEmotion") or stack_config.get("emotion") or settings.cartesia_tts_emotion
    speed_raw = pace
    if speed_raw is None:
        speed_raw = rt.get("ttsSpeed", rt.get("ttsPace"))
    if speed_raw is None:
        speed_raw = stack_config.get("speed", stack_config.get("pace"))
    gen = cartesia_generation_config(
        emotion=str(emotion) if emotion else None,
        speed=float(speed_raw) if speed_raw is not None else None,
        volume=(
            float(volume)
            if volume is not None
            else (rt.get("ttsVolume") if rt.get("ttsVolume") is not None else stack_config.get("volume"))
        ),
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
        "language_code": coerce_supported_language(language_code),
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
    session_id: str | None = "default",
    *,
    language_code: str = "te-IN",
    speaker: str | None = None,
    model: str | None = None,
    pace: float | None = None,
    temperature: float | None = None,
    pitch: float | None = None,
    volume: float | None = None,
    emotion: str | None = None,
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
    if session_id is None:
        # Stateless synthesis (server-owned previews) must not inherit or depend
        # on the live call stack: an unrelated tier/stack failure would otherwise
        # break every preview.
        rt = {}
        stack = None if provider_override is not None else resolved_stack
    else:
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
        pace = None
        temperature = None
        pitch = None
        volume = None
        emotion = None
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
            volume=volume,
            emotion=emotion,
            allow_runtime=not stack_is_locked,
        )

    resolved_model = _effective_tts_model(
        stack=stack,
        rt=rt,
        explicit_model=model,
        settings=settings,
    )

    if resolved_model not in constants.TTS_MODELS:
        raise TtsConfigError("The selected speech model is unavailable")

    from server.services.cartesia_voices import is_cartesia_voice_id
    from server.providers.voice_inventory import default_voice, validate_voice

    explicit_speaker = speaker or rt.get("ttsSpeaker")
    if explicit_speaker and is_cartesia_voice_id(str(explicit_speaker)):
        raise TtsConfigError("The selected voice does not match the speech provider")
    if explicit_speaker:
        resolved_speaker = str(explicit_speaker)
        try:
            validate_voice("sarvam", resolved_model, resolved_speaker, language_code)
        except ValueError as exc:
            log_tts("SPEAKER_INVALID", speaker=resolved_speaker, model=resolved_model)
            raise TtsConfigError(str(exc), speaker=resolved_speaker) from exc
    else:
        stack_speaker = stack.tts.config.get("speaker") if stack and stack.tts.config else None
        preferred = stack_speaker if stack_speaker and not is_cartesia_voice_id(str(stack_speaker)) else None
        if not preferred:
            preferred = settings.sarvam_tts_speaker_te if language_code == "te-IN" else get_speaker_for_language(language_code)
        try:
            resolved_speaker = default_voice(
                "sarvam", resolved_model, language_code, preferred=str(preferred) if preferred else None
            )
        except ValueError as exc:
            raise TtsConfigError(str(exc), speaker=str(preferred) if preferred else None) from exc

    stack_config = (stack.tts.config or {}) if stack else {}
    resolved_pace = pace if pace is not None else rt.get("ttsPace")
    if resolved_pace is None:
        resolved_pace = stack_config.get("pace", stack_config.get("speed"))
    if resolved_pace is None:
        resolved_pace = settings.sarvam_tts_pace
    resolved_pace = float(resolved_pace)
    if resolved_model in {"bulbul:v3", "bulbul:v4-flash"}:
        resolved_pace = max(0.5, min(2.0, resolved_pace))
    else:
        resolved_pace = max(0.3, min(3.0, resolved_pace))

    resolved_temp = temperature if temperature is not None else rt.get("ttsTemperature")
    if resolved_temp is None:
        resolved_temp = stack_config.get("temperature")
    if resolved_temp is None:
        resolved_temp = settings.sarvam_tts_temperature
    resolved_pitch = pitch if pitch is not None else rt.get("ttsPitch")
    resolved_volume = volume if volume is not None else rt.get("ttsVolume")
    if resolved_pitch is None:
        resolved_pitch = stack_config.get("pitch")
    if resolved_volume is None:
        resolved_volume = stack_config.get("volume", stack_config.get("loudness"))
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
        "language_code": provider_language_code(language_code, provider="sarvam", stage="tts"),
        "output_audio_codec": resolved_codec,
        "output_audio_bitrate": resolved_bitrate,
        "sample_rate": resolved_sample_rate,
        "min_buffer_size": int(resolved_min_buf),
        "max_chunk_length": int(resolved_max_chunk),
    }
    # Knob support is model-specific: v3 accepts temperature but not
    # pitch/loudness; v4-flash accepts all four; v2 accepts pitch/loudness
    # but not temperature. Never send a knob the selected model ignores.
    model_meta = constants.TTS_MODELS.get(resolved_model) or {}
    temp_range = model_meta.get("temperature")
    if resolved_temp is not None and temp_range:
        cfg["temperature"] = max(float(temp_range[0]), min(float(temp_range[1]), float(resolved_temp)))
    pitch_range = model_meta.get("pitch")
    if resolved_pitch is not None and pitch_range:
        cfg["pitch"] = max(float(pitch_range[0]), min(float(pitch_range[1]), float(resolved_pitch)))
    loudness_range = model_meta.get("loudness")
    if resolved_volume is not None and loudness_range:
        cfg["loudness"] = max(float(loudness_range[0]), min(float(loudness_range[1]), float(resolved_volume)))

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
        pitch=data.get("pitch"),
        volume=data.get("volume"),
        emotion=data.get("emotion"),
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
    """Telephony TTS — L16 RTP @ 16 kHz (Telnyx) or μ-law RTP @ 8 kHz (Vobiz)."""
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
            pitch=data.get("pitch"),
            volume=data.get("volume"),
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
        if (
            speaker
            and is_cartesia_voice_id(str(speaker))
            and _cartesia_available()
            and not locked_stack
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
            pitch=data.get("pitch"),
            volume=data.get("volume"),
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
        pitch=data.get("pitch"),
        volume=data.get("volume"),
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
