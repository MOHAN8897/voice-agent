"""Sarvam TTS adapter — wraps sarvam_ws + sarvam_tts_service."""

from __future__ import annotations

from server.config.constants import constants
from server.providers.audio_media import parse_pcm16_wav
from server.providers.base import TTSConfig
from server.services import sarvam_tts_service
from server.services.sarvam_ws import connect_tts_ws


class SarvamTTSAdapter:
    provider_id = "sarvam"

    @staticmethod
    def _validate_model_and_voice(config: TTSConfig) -> None:
        if not (config.model or "").strip():
            raise ValueError("Sarvam TTS requires the model selected in the resolved stack")
        # Validate or fallback model
        if config.model not in constants.TTS_MODELS:
            config.model = "bulbul:v3"
        speakers_v3 = set(constants.TTS_SPEAKERS_V3)
        speakers_v2 = set(constants.TTS_SPEAKERS_V2)
        all_allowed = speakers_v3 | speakers_v2
        if config.speaker and config.speaker not in all_allowed:
            # If unknown speaker, fallback to safe regional default
            config.speaker = "priya" if config.language.startswith("te") else "shubh"

    def connect_stream(self, config: TTSConfig):
        if config.provider != self.provider_id:
            raise ValueError("Sarvam TTS config provider does not match the resolved stack")
        self._validate_model_and_voice(config)
        # bulbul:v4-flash only accepts specific v4 compound speakers; if standard regional speaker is used, route to bulbul:v3
        effective_model = config.model
        if effective_model == "bulbul:v4-flash" and config.speaker in constants.TTS_SPEAKERS_V3:
            effective_model = "bulbul:v3"
        return connect_tts_ws(model=effective_model)

    async def synthesize_rest(self, text: str, config: TTSConfig) -> bytes:
        if config.provider != self.provider_id:
            raise ValueError("Sarvam TTS config provider does not match the resolved stack")
        self._validate_model_and_voice(config)
        result = await sarvam_tts_service.synthesize(
            text,
            language_code=config.language,
            speaker=config.speaker,
            pace=config.pace,
            model=config.model,
            temperature=config.temperature,
        )
        if not isinstance(result, dict):
            raise TypeError("Sarvam TTS returned a malformed response")
        if str(result.get("content_type") or "").split(";", 1)[0].lower() != "audio/wav":
            raise RuntimeError("Sarvam TTS returned an unsupported audio format")
        audio = result.get("audio_bytes")
        try:
            parse_pcm16_wav(audio)
        except ValueError as exc:
            raise RuntimeError("Sarvam TTS returned invalid WAV audio") from exc
        return audio
