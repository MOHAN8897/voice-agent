"""Cartesia TTS adapter — experimental; benchmark before Telugu production use."""
from __future__ import annotations

import httpx

from server.providers.base import TTSAdapter, TTSConfig
from server.services.dev_secrets_store import dev_secrets_store


class CartesiaTTSAdapter:
    provider_id = "cartesia"

    def _api_key(self) -> str:
        return dev_secrets_store.effective_secret("cartesia_api_key") or ""

    async def synthesize_rest(self, text: str, config: TTSConfig) -> bytes:
        key = self._api_key()
        if not key:
            raise RuntimeError("Cartesia API key not configured")
        payload = {
            "model_id": config.model or "sonic-english",
            "transcript": text,
            "voice": {"mode": "id", "id": config.speaker or "default"},
            "output_format": {
                "container": "raw",
                "encoding": "pcm_s16le",
                "sample_rate": 16000,
            },
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                "https://api.cartesia.ai/tts/bytes",
                headers={"X-API-Key": key, "Cartesia-Version": "2024-06-10"},
                json=payload,
            )
            r.raise_for_status()
            return r.content
