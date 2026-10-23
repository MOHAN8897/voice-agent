"""Cartesia TTS adapter — experimental; benchmark before Telugu production use."""
from __future__ import annotations

import httpx

from server.config.constants import constants
from server.config.env import get_settings
from server.providers.base import TTSConfig
from server.services.dev_secrets_store import dev_secrets_store


_CARTESIA_VOICE_MAP = {
    "sarah": "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4",
    "voice-sarah": "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4",
    "voice-cartesia-1": "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4",
    "voice-cartesia-sarah": "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4",
    "caleb": "a0e99841-438c-4a64-b679-ae501e7d6091",
    "voice-caleb": "a0e99841-438c-4a64-b679-ae501e7d6091",
    "voice-cartesia-2": "a0e99841-438c-4a64-b679-ae501e7d6091",
    "voice-cartesia-caleb": "a0e99841-438c-4a64-b679-ae501e7d6091",
    "jacqueline": "694f9389-aac1-45b6-b726-9d9369183238",
    "voice-jacqueline": "694f9389-aac1-45b6-b726-9d9369183238",
    "voice-cartesia-3": "694f9389-aac1-45b6-b726-9d9369183238",
    "voice-cartesia-jacqueline": "694f9389-aac1-45b6-b726-9d9369183238",
    "michael": "47c38ca4-ff9b-4e89-a2e1-456956b46452",
    "voice-michael": "47c38ca4-ff9b-4e89-a2e1-456956b46452",
    "voice-cartesia-4": "47c38ca4-ff9b-4e89-a2e1-456956b46452",
    "voice-cartesia-michael": "47c38ca4-ff9b-4e89-a2e1-456956b46452",
    "skylar": "5c5ac573-455b-4d85-8ccb-a78c187bc954",
    "voice-skylar": "5c5ac573-455b-4d85-8ccb-a78c187bc954",
    "voice-cartesia-5": "5c5ac573-455b-4d85-8ccb-a78c187bc954",
    "voice-cartesia-skylar": "5c5ac573-455b-4d85-8ccb-a78c187bc954",
    "daniel": "79a125e8-cd45-4c13-8a67-188112f4dd22",
    "voice-daniel": "79a125e8-cd45-4c13-8a67-188112f4dd22",
    "voice-cartesia-6": "79a125e8-cd45-4c13-8a67-188112f4dd22",
    "voice-cartesia-daniel": "79a125e8-cd45-4c13-8a67-188112f4dd22",
    "katie": "f114a346-765b-4ff2-8067-1601d0a52026",
    "voice-katie": "f114a346-765b-4ff2-8067-1601d0a52026",
    "voice-cartesia-7": "f114a346-765b-4ff2-8067-1601d0a52026",
    "voice-cartesia-katie": "f114a346-765b-4ff2-8067-1601d0a52026",
    "leo": "b7d50908-b47d-4404-be6c-033100685600",
    "voice-leo": "b7d50908-b47d-4404-be6c-033100685600",
    "voice-cartesia-8": "b7d50908-b47d-4404-be6c-033100685600",
    "voice-cartesia-leo": "b7d50908-b47d-4404-be6c-033100685600",
    # Indian / Indic language-specific voices
    "voice-cartesia-priya": "045f0292-0731-4a4c-971d-64594fc2c35a",
    "cartesia-priya": "045f0292-0731-4a4c-971d-64594fc2c35a",
    "kiara": "f8f5f1b2-f02d-4d8e-a40d-fd850a487b3d",
    "voice-kiara": "f8f5f1b2-f02d-4d8e-a40d-fd850a487b3d",
    "voice-cartesia-kiara": "f8f5f1b2-f02d-4d8e-a40d-fd850a487b3d",
    "indian-lady": "3b554273-4299-48b9-9aaf-eefd438e3941",
    "indian_lady": "3b554273-4299-48b9-9aaf-eefd438e3941",
    "voice-indian-lady": "3b554273-4299-48b9-9aaf-eefd438e3941",
    "voice-cartesia-indian-lady": "3b554273-4299-48b9-9aaf-eefd438e3941",
    "devansh": "87a983d8-3471-4c4b-9ade-f1d10a4110ac",
    "voice-devansh": "87a983d8-3471-4c4b-9ade-f1d10a4110ac",
    "voice-cartesia-devansh": "87a983d8-3471-4c4b-9ade-f1d10a4110ac",
    "krishna": "efa653e5-314d-46ca-9f90-70ac7d6ca71e",
    "voice-krishna": "efa653e5-314d-46ca-9f90-70ac7d6ca71e",
    "voice-cartesia-krishna": "efa653e5-314d-46ca-9f90-70ac7d6ca71e",
    "aarav": "39d518b7-fd0b-4676-9b8b-29d64ff31e12",
    "voice-aarav": "39d518b7-fd0b-4676-9b8b-29d64ff31e12",
    "voice-cartesia-aarav": "39d518b7-fd0b-4676-9b8b-29d64ff31e12",
    "bhavani": "76961778-84da-4b51-8d42-2e8e6e6a5e8a",
    "voice-bhavani": "76961778-84da-4b51-8d42-2e8e6e6a5e8a",
    "voice-cartesia-bhavani": "76961778-84da-4b51-8d42-2e8e6e6a5e8a",
    "charan": "82c2afc8-4f0d-4c3e-9c3e-8e8e8e8e8e8e",
    "voice-charan": "82c2afc8-4f0d-4c3e-9c3e-8e8e8e8e8e8e",
    "voice-cartesia-charan": "82c2afc8-4f0d-4c3e-9c3e-8e8e8e8e8e8e",
    "aarti": "9cebb910-d4b7-4a4a-85a4-12c79137724c",
    "voice-aarti": "9cebb910-d4b7-4a4a-85a4-12c79137724c",
    "voice-cartesia-aarti": "9cebb910-d4b7-4a4a-85a4-12c79137724c",
    "amrit": "97303aad-0000-0000-0000-000000000001",
    "voice-amrit": "97303aad-0000-0000-0000-000000000001",
    "voice-cartesia-amrit": "97303aad-0000-0000-0000-000000000001",
    "maya": "79a125e8-cd45-4c13-8a67-0491c5ad1b8a",
    "voice-maya": "79a125e8-cd45-4c13-8a67-0491c5ad1b8a",
    "voice-cartesia-maya": "79a125e8-cd45-4c13-8a67-0491c5ad1b8a",
}


def resolve_cartesia_voice_id(speaker: str | None) -> str:
    settings = get_settings()
    spk = str(speaker or "").strip().lower()
    if spk in _CARTESIA_VOICE_MAP:
        return _CARTESIA_VOICE_MAP[spk]
    import re
    if re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", spk):
        return spk
    return str(speaker or settings.cartesia_tts_voice_id or constants.CARTESIA_DEFAULT_VOICE_ID)


def _resolve_voice_id(config: TTSConfig) -> str:
    return resolve_cartesia_voice_id(config.speaker)



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
