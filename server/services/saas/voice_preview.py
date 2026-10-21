"""Speech previews using the provider and voice selected by the SaaS stack."""
from __future__ import annotations

import base64
import io
import logging
import wave
from typing import Any

logger = logging.getLogger(__name__)

MAX_PREVIEW_CHARS = 400
PREVIEW_TIMEOUT_S = 25.0
GEMINI_TTS_MODEL = "gemini-3.8-flash-tts"


class VoicePreviewRateLimited(RuntimeError):
    def __init__(self, retry_after: int = 60):
        super().__init__("Gemini voice generation is rate limited (HTTP 429)")
        self.retry_after = retry_after


def pcm16_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    """Keep the small PCM wrapping helper available for internal callers/tests."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(pcm)
    return buffer.getvalue()


def normalize_preview_text(raw: str) -> str:
    line = " ".join(str(raw or "").split())[:MAX_PREVIEW_CHARS]
    if not line:
        raise ValueError("empty_preview_text")
    return line


def resolve_preview_voice(
    voice_id: str | None,
    *,
    provider: str = "gemini",
    language: str | None = None,
) -> tuple[str, str]:
    """Resolve an exact catalog voice for the active provider; reject stale IDs."""
    from server.realtime.models import default_gemini_live_voice
    from server.services.saas.voice_catalog import phone_voice_catalog

    active_provider = str(provider or "gemini").strip().lower()
    wanted = str(voice_id or "").strip()
    if not wanted:
        if active_provider == "gemini":
            wanted = default_gemini_live_voice(language)
        elif active_provider == "sarvam":
            wanted = "shubh"
        else:
            wanted = "marin"
    for row in phone_voice_catalog():
        if row.get("provider") != active_provider or str(row.get("id", "")).casefold() != wanted.casefold():
            continue
        voice = row.get("geminiVoice") if active_provider == "gemini" else row.get("id")
        return str(voice or wanted), str(row.get("label") or wanted)
    raise ValueError("voice_not_in_active_catalog")


_OPENAI_TTS_VOICE_MAP: dict[str, str] = {
    "marin": "coral",
    "cedar": "onyx",
    "alloy": "alloy",
    "ash": "ash",
    "ballad": "fable",
    "coral": "coral",
    "echo": "echo",
    "sage": "sage",
    "shimmer": "shimmer",
    "verse": "fable",
}


def resolve_openai_tts_voice(voice_id: str | None) -> str:
    try:
        return _OPENAI_TTS_VOICE_MAP[str(voice_id or "marin").casefold()]
    except KeyError:
        raise ValueError("voice_not_in_active_catalog") from None


def _gemini_audio_from_response(payload: dict[str, Any]) -> bytes:
    audio = payload.get("output_audio")
    encoded = audio.get("data") if isinstance(audio, dict) else None
    if not encoded:
        for step in payload.get("steps") or []:
            if not isinstance(step, dict):
                continue
            for content in step.get("content") or []:
                if isinstance(content, dict) and content.get("type") == "audio" and content.get("data"):
                    encoded = content["data"]
    if not isinstance(encoded, str) or not encoded:
        raise RuntimeError("Gemini voice generation returned no audio")
    try:
        audio_bytes = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error):
        raise RuntimeError("Gemini voice generation returned invalid audio data") from None
    if len(audio_bytes) < 44 or not audio_bytes.startswith(b"RIFF") or audio_bytes[8:12] != b"WAVE":
        raise RuntimeError("Gemini voice generation returned an invalid WAV file")
    return audio_bytes


async def _synthesize_gemini(line: str, voice: str, speed: float) -> bytes:
    import httpx

    from server.providers.gemini_llm import _api_key

    key = _api_key()
    if not key or key.startswith("gem-test"):
        raise RuntimeError("Gemini API key is not configured")
    pace = "normal pace" if abs(speed - 1.0) < 0.01 else ("slower pace" if speed < 1 else "brisker pace")
    payload = {
        "model": GEMINI_TTS_MODEL,
        "input": [{
            "type": "user_input",
            "content": [{
                "type": "text",
                "text": line,
                "annotations": [{
                    "type": "speech_metadata",
                    "style": f"Speak clearly and professionally at a {pace}.",
                }],
            }],
        }],
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": [{"voice": voice}]},
    }
    async with httpx.AsyncClient(timeout=PREVIEW_TIMEOUT_S) as client:
        response = await client.post(
            "https://generativelanguage.googleapis.com/v1beta/interactions",
            headers={"x-goog-api-key": key},
            json=payload,
        )
    if not response.is_success:
        if response.status_code == 429:
            headers = getattr(response, "headers", {})
            try:
                retry_after = max(1, min(3600, int(headers.get("Retry-After", "60"))))
            except (TypeError, ValueError):
                retry_after = 60
            raise VoicePreviewRateLimited(retry_after)
        error = {}
        try:
            error = response.json().get("error") or {}
        except (ValueError, AttributeError):
            pass
        code = str(error.get("status") or "").strip().casefold()
        if response.status_code == 403 or code == "permission_denied":
            raise RuntimeError("Gemini voice generation permission_denied")
        raise RuntimeError(f"Gemini voice generation failed (HTTP {response.status_code})")
    try:
        body = response.json()
    except ValueError:
        raise RuntimeError("Gemini voice generation returned invalid response data") from None
    return _gemini_audio_from_response(body)


async def _synthesize_openai(line: str, voice: str, speed: float) -> bytes:
    from server.config.env import get_settings

    api_key = get_settings().openai_api_key
    if not api_key:
        raise RuntimeError("OpenAI API key is not configured")
    import openai

    client = openai.AsyncOpenAI(api_key=api_key, timeout=PREVIEW_TIMEOUT_S)
    try:
        result = await client.audio.speech.create(
            model="tts-1",
            voice=resolve_openai_tts_voice(voice),
            input=line,
            speed=max(0.5, min(2.0, speed)),
            response_format="wav",
        )
        audio = result.content
    finally:
        await client.close()
    if len(audio) < 44 or not audio.startswith(b"RIFF") or audio[8:12] != b"WAVE":
        raise RuntimeError("OpenAI voice generation returned an invalid WAV file")
    return audio


async def _synthesize_sarvam(line: str, voice: str, speed: float, language: str | None = None) -> bytes:
    from server.services.sarvam_tts_service import synthesize

    result = await synthesize(
        text=line,
        language_code=language or "te-IN",
        speaker=voice,
        pace=speed,
    )
    audio = result.get("audio_bytes")
    if not isinstance(audio, bytes) or len(audio) < 44 or not audio.startswith(b"RIFF") or audio[8:12] != b"WAVE":
        raise RuntimeError("Sarvam voice generation returned an invalid WAV file")
    return audio


async def synthesize_preview(
    text: str,
    *,
    voice_id: str | None = None,
    language: str | None = None,
    speed: float | None = None,
    provider: str = "gemini",
    model: str | None = None,
) -> dict[str, Any]:
    """Synthesize a WAV with the currently selected provider; never cross-fallback."""
    line = normalize_preview_text(text)
    active_provider = str(provider or "gemini").strip().lower()
    if active_provider not in {"gemini", "openai", "sarvam"}:
        raise ValueError("unsupported_voice_provider")
    voice, label = resolve_preview_voice(voice_id, provider=active_provider, language=language)
    pace = max(0.5, min(2.0, float(speed) if speed is not None else 1.0))
    if active_provider == "gemini":
        preview_model = GEMINI_TTS_MODEL
    elif active_provider == "sarvam":
        preview_model = "bulbul:v3"
    else:
        preview_model = "tts-1"
    from server.services.saas.voice_catalog import phone_voice_catalog

    # Only built-in samples are public. A tenant's custom greeting stays private
    # and is never written into this shared sample directory.
    cacheable = any(
        row.get("provider") == active_provider and row.get("id") == voice
        and normalize_preview_text(row.get("sampleText") or " ") == line
        for row in phone_voice_catalog()
        if row.get("sampleText")
    )

    async def generate():
        if active_provider == "gemini":
            return await _synthesize_gemini(line, voice, pace)
        elif active_provider == "sarvam":
            return await _synthesize_sarvam(line, voice, pace, language)
        return await _synthesize_openai(line, voice, pace)

    cache_hit = False
    if cacheable:
        from server.services.saas.voice_sample_cache import get_or_create
        audio, cache_hit = await get_or_create([active_provider, preview_model, voice, language, pace, line], generate)
    else:
        audio = await generate()
    return {
        "audio": audio,
        "voice": voice,
        "label": label,
        "model": preview_model,
        "stackModel": str(model or ""),
        "truncated": False,
        "cacheable": cacheable,
        "cacheHit": cache_hit,
    }
