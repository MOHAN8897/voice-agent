"""Cartesia TTS adapter — experimental; benchmark before Telugu production use."""
from __future__ import annotations

import httpx

from server.config.constants import constants
from server.config.env import get_settings
from server.providers.base import TTSConfig
from server.services.dev_secrets_store import dev_secrets_store


def _resolve_voice_id(config: TTSConfig) -> str:
    settings = get_settings()
    return config.speaker or settings.cartesia_tts_voice_id or constants.CARTESIA_DEFAULT_VOICE_ID


class CartesiaTTSAdapter:
    provider_id = "cartesia"

    def _api_key(self) -> str:
        return dev_secrets_store.effective_secret("cartesia_api_key") or ""

    def connect_stream(self, config: TTSConfig):
        from server.services.cartesia_tts_ws import connect_cartesia_tts_ws

        return connect_cartesia_tts_ws(model=config.model)

    async def synthesize_rest(self, text: str, config: TTSConfig) -> bytes:
        settings = get_settings()
        key = self._api_key()
        if not key:
            raise RuntimeError("Cartesia API key not configured")
        payload = {
            "model_id": config.model or settings.cartesia_tts_model or "sonic-3.5",
            "transcript": text,
            "voice": {"mode": "id", "id": _resolve_voice_id(config)},
            "output_format": {
                "container": "raw",
                "encoding": "pcm_s16le",
                "sample_rate": 16000,
            },
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                "https://api.cartesia.ai/tts/bytes",
                headers={
                    "X-API-Key": key,
                    "Cartesia-Version": settings.cartesia_api_version or "2026-08-14",
                },
                json=payload,
            )
            r.raise_for_status()
            return r.content
