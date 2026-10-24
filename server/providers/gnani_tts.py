"""Gnani.ai (Vachana) TTS adapter — enterprise Indian speech engine."""
from __future__ import annotations

import base64
import httpx

from server.config.constants import constants
from server.config.env import get_settings
from server.providers.base import TTSConfig
from server.services.dev_secrets_store import dev_secrets_store


def _resolve_voice_id(config: TTSConfig, *, language: str | None = None) -> str:
    from server.services.gnani_tts_ws import _resolve_gnani_voice

    return _resolve_gnani_voice(config.speaker, model=config.model, language=language)


class GnaniTTSAdapter:
    provider_id = "gnani"

    def _api_key(self) -> str:
        settings = get_settings()
        return dev_secrets_store.effective_secret("gnani_api_key") or settings.gnani_api_key or ""

    def connect_stream(self, config: TTSConfig):
        from server.services.gnani_tts_ws import connect_gnani_tts_ws

        return connect_gnani_tts_ws(model=config.model)

    async def synthesize_rest(self, text: str, config: TTSConfig) -> bytes:
        key = self._api_key()
        if not key:
            raise RuntimeError("Gnani API key not configured")

        from server.services.gnani_tts_ws import _gnani_language_code

        model = str(config.model or constants.GNANI_DEFAULT_MODEL)
        from server.prompts.tts_delivery_rules import sanitize_tts_tags

        text = sanitize_tts_tags(text, provider="gnani", model=model)
        if not text:
            raise ValueError("Speech text must contain words, not only audio tags")
        lang = _gnani_language_code(config.language, model=model)
        voice = _resolve_voice_id(config, language=lang)
        from server.providers.voice_inventory import provider_language

        lang = provider_language("gnani", model, voice, lang)
        pace = max(0.85, min(1.15, float(config.pace or 1.0)))

        payload = {
            "text": text,
            "voice": voice,
            "model": model,
            "language": lang,
            "speed": pace,
            "audio_config": {
                "sample_rate": 16000,
                "num_channels": 1,
                "sample_width": 2,
                "encoding": "linear_pcm",
                "container": "wav",
            },
        }
        # The published TTSRequest supports speed, not numeric pitch or volume.
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                constants.GNANI_TTS_REST,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key-ID": key,
                },
                json=payload,
            )
            if not r.is_success:
                err_text = r.text
                if r.status_code in (401, 402, 429) or "credit" in err_text.lower():
                    raise RuntimeError(f"HTTP {r.status_code} Gnani credits exhausted or unauthorized: {err_text}")
                r.raise_for_status()

            # May return raw WAV bytes or JSON with base64 audio
            content = r.content
            if content.startswith(b"RIFF") and content[8:12] == b"WAVE":
                return content
            try:
                data = r.json()
                b64 = data.get("audio") or data.get("data")
                if b64:
                    raw = base64.b64decode(b64)
                    if raw.startswith(b"RIFF"):
                        return raw
                    from server.services.saas.voice_preview import pcm16_to_wav
                    return pcm16_to_wav(raw, 16000)
            except Exception:
                pass
            return content
