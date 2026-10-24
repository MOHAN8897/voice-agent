"""Cartesia TTS adapter — experimental; benchmark before Telugu production use."""
from __future__ import annotations

import httpx

from server.config.constants import constants
from server.config.env import get_settings
from server.providers.base import TTSConfig
from server.services.dev_secrets_store import dev_secrets_store


# Kept as an empty compatibility export for callers; no invented name-to-UUID map.
_CARTESIA_VOICE_MAP: dict[str, str] = {}


def resolve_cartesia_voice_id(speaker: str | None) -> str:
    from server.providers.voice_inventory import inventory

    wanted = str(speaker or "").strip()
    rows = inventory().get("cartesia", {}).get("voices", [])
    match = next((row for row in rows if row["providerVoiceId"] == wanted), None)
    if match is None:
        raise ValueError("Choose an Indian voice from the current speech catalog")
    return str(match["providerVoiceId"])


def _resolve_voice_id(config: TTSConfig) -> str:
    from server.providers.voice_inventory import validate_voice

    voice = resolve_cartesia_voice_id(config.speaker)
    validate_voice("cartesia", config.model, voice, config.language)
    return voice



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
        from server.services.tts_voice_direction import cartesia_generation_config

        payload = {
            "model_id": config.model or settings.cartesia_tts_model or "sonic-3.5",
            "transcript": text,
            "language": config.language.split("-")[0],
            "voice": {"mode": "id", "id": _resolve_voice_id(config)},
            "output_format": {
                "container": "raw",
                "encoding": "pcm_s16le",
                "sample_rate": 16000,
            },
            "generation_config": cartesia_generation_config(
                emotion=config.emotion,
                speed=config.speed,
                volume=config.volume,
            ),
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
