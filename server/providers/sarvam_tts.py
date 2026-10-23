"""Sarvam TTS adapter — wraps sarvam_ws + sarvam_tts_service."""

from __future__ import annotations

from server.providers.audio_media import parse_pcm16_wav
from server.providers.base import TTSConfig
from server.providers.sarvam_voice_catalog import validate_sarvam_voice
from server.services import sarvam_tts_service
from server.services.sarvam_ws import connect_tts_ws


class SarvamTTSAdapter:
    provider_id = "sarvam"

    @staticmethod
    def _validate_model_and_voice(config: TTSConfig) -> None:
        if not (config.model or "").strip():
            raise ValueError("Sarvam TTS requires the model selected in the resolved stack")
        validate_sarvam_voice(config.model, config.speaker, config.language)

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
