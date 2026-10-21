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
        if not config.model.strip():
            raise ValueError("Sarvam TTS requires the model selected in the resolved stack")
        if config.model not in constants.TTS_MODELS:
            raise ValueError("Sarvam TTS model is not in the configured provider catalog")
        speakers = (
            constants.TTS_SPEAKERS_V3 if config.model == "bulbul:v3" else constants.TTS_SPEAKERS_V2
        )
        if config.speaker not in speakers:
            raise ValueError("Sarvam TTS voice is not in the selected model's configured catalog")

    def connect_stream(self, config: TTSConfig):
        if config.provider != self.provider_id:
            raise ValueError("Sarvam TTS config provider does not match the resolved stack")
        self._validate_model_and_voice(config)
        return connect_tts_ws(model=config.model)

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
