"""Cartesia STT adapter — Ink 2 / Ink Whisper via WebSocket."""
from __future__ import annotations

from server.config.constants import constants
from server.providers.base import STTConfig, TranscriptResult
from server.services.cartesia_ws import connect_cartesia_stt_realtime


class CartesiaSTTAdapter:
    provider_id = "cartesia"

    def supported_languages(self) -> list[str]:
        langs: set[str] = set()
        for meta in constants.CARTESIA_STT_MODELS.values():
            langs.update(meta.get("languages") or [])
        langs.update(constants.SUPPORTED_LANGUAGES.keys())
        return sorted(langs)

    async def transcribe_rest(self, audio: bytes, config: STTConfig) -> TranscriptResult:
        raise NotImplementedError("Cartesia STT REST is not wired — use realtime WebSocket")

    def connect_realtime(self, config: STTConfig):
        return connect_cartesia_stt_realtime(
            language_code=config.language,
            sample_rate=config.sample_rate,
            model=config.model,
        )
