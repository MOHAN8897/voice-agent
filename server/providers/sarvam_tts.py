"""Sarvam TTS adapter — wraps sarvam_ws + sarvam_tts_service."""
from __future__ import annotations

from server.providers.base import TTSAdapter, TTSConfig
from server.services import sarvam_tts_service
from server.services.sarvam_ws import connect_tts_ws


class SarvamTTSAdapter:
    provider_id = "sarvam"

    def connect_stream(self, config: TTSConfig):
        return connect_tts_ws(model=config.model)

    async def synthesize_rest(self, text: str, config: TTSConfig) -> bytes:
        result = await sarvam_tts_service.synthesize(
            text,
            language_code=config.language,
            speaker=config.speaker,
            pace=config.pace,
            model=config.model,
            temperature=config.temperature,
        )
        return result["audio_bytes"]
