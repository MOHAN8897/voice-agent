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
) -> dict[str, Any]:
    """
    Resolve the effective TTS configuration for a session.
    Priority: explicit call arg → runtime override → env default → language map.
    """
    settings = get_settings()
    rt = runtime_settings.get(session_id)

    resolved_model = model or rt.get("ttsModel") or settings.sarvam_tts_model
    if resolved_model not in constants.TTS_MODELS:
        resolved_model = settings.sarvam_tts_model

    resolved_speaker = speaker or rt.get("ttsSpeaker")
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


def merge_ws_tts_config(session_id: str, client_data: dict | None, *, language_code: str = "te-IN") -> dict[str, Any]:
    """Merge browser WS config payload with server-resolved runtime settings."""
    data = dict(client_data or {})
    return resolve_tts_config(
        session_id,
        language_code=data.get("language_code") or language_code,
        speaker=data.get("speaker"),
        model=None,  # model comes from WS query param
        pace=data.get("pace"),
        temperature=data.get("temperature"),
        codec=data.get("output_audio_codec"),
        sample_rate=data.get("sample_rate"),
        min_buffer_size=data.get("min_buffer_size"),
        max_chunk_length=data.get("max_chunk_length"),
        output_audio_bitrate=data.get("output_audio_bitrate"),
    )
