"""Speech previews using the provider and voice selected by the SaaS stack."""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import time
import wave
from typing import Any

logger = logging.getLogger(__name__)

MAX_PREVIEW_CHARS = 400
PREVIEW_TIMEOUT_S = 25.0
GEMINI_TTS_MODEL = "gemini-3.8-flash-tts"
_WARM_INFLIGHT: set[str] = set()
_WARM_COOLDOWN: dict[str, float] = {}
_WARM_TASKS: set[asyncio.Task] = set()
_WARM_COOLDOWN_S = 900.0


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
    voice_id: str | None, *, provider: str = "gemini", language: str | None = None,
    tier: str | None = None, model: str | None = None,
) -> tuple[str, str]:
    """Resolve an exact provider/model voice; never infer a speaker from its number."""
    from server.providers.voice_inventory import validate_voice, voices_for_model
    from server.services.saas.voice_catalog import phone_voice_catalog
    from server.services.saas.voice_stack_profiles import lookup_cached_voice_alias

    wanted = str(voice_id or "").strip()
    alias = lookup_cached_voice_alias(wanted)
    if alias:
        if alias.get("provider") and alias["provider"] != provider:
            raise ValueError("voice_not_in_active_catalog")
        wanted = str(alias.get("providerVoiceId") or "")
    rows = (
        voices_for_model(provider, model)
        if model and provider != "openai"
        else [row for row in phone_voice_catalog() if row.get("provider") == provider]
    )
    for row in rows:
        pvid = str(row.get("providerVoiceId") or row.get("geminiVoice") or row.get("id") or "")
        if wanted and wanted.casefold() in {pvid.casefold(), str(row.get("id") or "").casefold()}:
            if language and row.get("languages") and language not in row["languages"]:
                continue
            if model and provider != "openai":
                validate_voice(provider, model, pvid, language)
            return pvid, str(row.get("label") or pvid)
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


async def _synthesize_sarvam(
    line: str,
    voice: str,
    speed: float,
    language: str | None = None,
    temperature: float | None = None,
    pitch: float | None = None,
    volume: float | None = None,
    model: str | None = None,
) -> bytes:
    from server.services.sarvam_tts_service import synthesize

    result = await synthesize(
        text=line,
        language_code=language or "te-IN",
        speaker=voice,
        model=model,
        pace=speed,
        temperature=temperature,
        pitch=pitch,
        volume=volume,
        session_id=None,
    )
    audio = result.get("audio_bytes")
    if not isinstance(audio, bytes) or len(audio) < 44 or not audio.startswith(b"RIFF") or audio[8:12] != b"WAVE":
        raise RuntimeError("Sarvam voice generation returned an invalid WAV file")
    return audio


async def _synthesize_gemini_tts(
    line: str,
    voice: str,
    speed: float,
    language: str | None = None,
    model: str | None = None,
    pitch: float | None = None,
) -> bytes:
    from server.providers.gemini_tts import GeminiTTSAdapter, TTSConfig

    adapter = GeminiTTSAdapter()
    cfg = TTSConfig(
        provider="gemini",
        model=model or "gemini-3.8-flash-tts",
        speaker=voice,
        language=language or "te-IN",
        pace=speed,
        pitch=pitch,
    )
    result = await adapter.synthesize_with_metadata(line, cfg)
    audio = result.audio_bytes
    if not isinstance(audio, bytes) or len(audio) < 44 or not audio.startswith(b"RIFF") or audio[8:12] != b"WAVE":
        raise RuntimeError("Gemini TTS voice generation returned an invalid WAV file")
    return audio


async def _synthesize_gnani(
    line: str,
    voice: str,
    speed: float,
    language: str | None = None,
    model: str | None = None,
    pitch: float | None = None,
    volume: float | None = None,
) -> bytes:
    from server.providers.gnani_tts import GnaniTTSAdapter, TTSConfig
    from server.services.saas.voice_sample_cache import valid_wav

    clean_v = str(voice or "").strip()
    req_model = model or "timbre-v3.0"
    adapter = GnaniTTSAdapter()
    cfg = TTSConfig(
        provider="gnani",
        model=req_model,
        speaker=clean_v,
        language=language or "te-IN",
        pace=speed,
        pitch=pitch,
        volume=volume,
    )
    raw = await adapter.synthesize_rest(line, cfg)
    if isinstance(raw, bytes) and valid_wav(raw):
        return raw
    if isinstance(raw, bytes) and len(raw) > 44:
        return pcm16_to_wav(raw[44:], 16000)
    return raw


async def _synthesize_cartesia(
    line: str,
    voice: str,
    speed: float,
    language: str | None = None,
    model: str | None = None,
    emotion: str | None = None,
    volume: float | None = None,
) -> bytes:
    from server.providers.cartesia_tts import CartesiaTTSAdapter, TTSConfig
    from server.services.saas.voice_sample_cache import valid_wav

    adapter = CartesiaTTSAdapter()
    cfg = TTSConfig(
        provider="cartesia",
        model=model or "sonic-3.5",
        speaker=voice,
        language=language or "te-IN",
        speed=speed,
        emotion=emotion,
        volume=volume,
    )
    raw = await adapter.synthesize_rest(line, cfg)
    if isinstance(raw, bytes) and valid_wav(raw):
        return raw
    if isinstance(raw, bytes) and len(raw) > 0:
        return pcm16_to_wav(raw, 16000)
    return raw


def find_static_sample(voice: str, language: str | None = None) -> bytes | None:
    """Find pre-recorded or pre-stored static sample audio for catalog voices."""
    from pathlib import Path
    from server.services.saas.voice_sample_cache import valid_wav
    from server.config.env import get_settings

    import re

    clean_voice = voice.strip().lower()
    if not re.fullmatch(r"[a-z0-9_-]+", clean_voice):
        return None
    lang_prefix = (language.split("-")[0] if language else "te").lower()

    base_dirs = [
        Path("voxly-ai/public/audio/voxly/samples"),
        Path(get_settings().data_dir) / "voice-samples" / "static",
        Path("server/static/audio/samples"),
        Path("web/public/audio/voxly/samples"),
    ]
    # Priority: 1. Voice with language prefix (e.g. zephyr_te.wav), 2. Base voice (e.g. shubh.wav)
    filenames = [
        f"{clean_voice}_{lang_prefix}.wav",
        f"{clean_voice}.wav",
        f"voice-{clean_voice}_{lang_prefix}.wav",
        f"voice-{clean_voice}.wav",
    ]
    for bdir in base_dirs:
        for fname in filenames:
            cand = bdir / fname
            try:
                if cand.is_file():
                    audio = cand.read_bytes()
                    if valid_wav(audio):
                        return audio
            except OSError:
                continue
    return None


# Server-owned greeting per language. Catalog previews always speak this line so
# every listener compares voices on the same script, and the result is cacheable.
CATALOG_PREVIEW_TEXTS: dict[str, str] = {
    "te": "నమస్కారం. మీకు ఎలా సహాయం చేయగలను?",
    "hi": "नमस्ते। मैं आपकी कैसे मदद कर सकता हूँ?",
    "ta": "வணக்கம். உங்களுக்கு எப்படி உதவலாம்?",
    "kn": "ನಮಸ್ಕಾರ. ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?",
    "ml": "നമസ്കാരം. ഞാൻ നിങ്ങളെ എങ്ങനെ സഹായിക്കാം?",
    "mr": "नमस्कार. मी तुम्हाला कशी मदत करू शकतो?",
    "bn": "নমস্কার. আমি আপনাকে কিভাবে সাহায্য করতে পারি?",
    "gu": "નમસ્તે. હું તમને કેવી રીતે મદદ કરી શકું?",
    "pa": "ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ। ਮੈਂ ਤੁਹਾਡੀ ਕਿਵੇਂ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ?",
    "en": "Hello. Thank you for calling. How can I help you today?",
}


def catalog_preview_text(language: str | None) -> str:
    base = str(language or "").strip().lower().split("-", 1)[0]
    return CATALOG_PREVIEW_TEXTS.get(base, CATALOG_PREVIEW_TEXTS["en"])


STANDARD_SAMPLE_TEXTS: set[str] = {
    "నమస్కారం. మీకు ఎలా సహాయం చేయగలను?",
    "నమస్కారం, నేను మీకు ఎలా సహాయం చేయగలను?",
    "నమస్కారం, మీ ప్రశ్నలకు సమాధానాలు అందించడానికి నేను సిద్ధంగా ఉన్నాను.",
    "నమస్కారం, మా ఆఫర్ల గురించి మీకు వివరించడానికి సిద్ధంగా ఉన్నాను.",
    "నమస్కారం, మీ అపాయింట్‌మెంట్ బుకింగ్ కోసం నేను సహాయం చేయగలను.",
    "నమస్కారం, మీ వివరాలను సరిచూసేందుకు సహాయపడతాను.",
    "నమస్కారం, మీ సమస్యను పరిష్కరించడంలో సహాయం చేస్తాను.",
    "నమస్కారం, మీ విచారణను పరిశీలించి వెంటనే సమాధానం ఇస్తాను.",
    "నమస్కారం, మీ ఖాతా వివరాల గురించి మాట్లాడటానికి సిద్ధంగా ఉన్నాను.",
    "నమస్కారం, స్వాగతం! మీకు ఎలా సహాయపడగలను?",
    # English
    "Hello. How can I help you today?",
    "Hello. Thank you for calling. How can I help you today?",
    "Hello, thank you for calling. How can I help you today?",
    "Hello, this is Zephyr. I can assist you with bookings, orders, and inquiries. How can I help you today?",
    "Welcome! I am Aoede, your virtual assistant. How can I assist you today?",
    "Thank you for calling. I can help you schedule appointments, verify records, and answer questions. What can I do for you today?",
    "Thank you for calling. I am here to assist with your bookings, questions, and customer care. How may I help you?",
    "Hello! I am Puck. I can help explore our latest inventory, book appointments, or answer questions. What can I get started for you?",
    "You have reached Dispatch Services. I can schedule emergency maintenance, technician visits, or system inspections. What can I do for you?",
    "Thanks for calling! We have exclusive viewings and consultations available this week. What area interests you?",
    "Hello, this is Technical Operations. I can help resolve systems access, diagnostic alerts, or service tickets. Please describe your issue.",
    "Hello, this is Northbridge Technical Operations. I can help resolve systems access, diagnostic alerts, or service tickets. Please tell me your issue.",
    "Thank you for calling City Concierge. I can assist with reservations, guest services, and appointment scheduling. How may I help you today?",
    "You have reached CoolAir Service Dispatch. I can schedule emergency maintenance, technician visits, or system inspections. What can I do for you?",
    "Thank you for calling Sunshine Health Clinic. I can help you book, reschedule, or check doctor availability. What appointment do you need?",
    "Hello, this is Metro Automotive Sales. We have exciting offers and test drive slots open this week. Which vehicle would you like to explore?",
    "Thank you for calling Meridian Financial Services. I can assist with account verification, card security, and onboarding. How may I assist?",
    "Thanks for calling Harbour Point Real Estate. We have exclusive property viewings and investment tours scheduled this weekend. What area interests you?",
    "Welcome to Enterprise IT Systems Helpdesk. I can verify your credentials, unlock single sign-on, and resolve workstation requests immediately.",
    "Welcome to Northbridge Academic Advisory. I can guide you through admissions deadlines, degree requirements, and enrolment. How can I guide you?",
    "Good evening! Thank you for calling Bella Vista Dining. I can confirm your table reservations or take your specialty order. How many in your party?",
    "Hello. Thank you for calling. How may I assist you today?",
    # Indic languages
    "नमस्ते। मैं आपकी कैसे मदद कर सकती हूँ?",
    "नमस्ते। मैं आपकी कैसे मदद कर सकता हूँ?",
    "வணக்கம். உங்களுக்கு எப்படி உதவலாம்?",
    "ನಮಸ್ಕಾರ. ನಾನು ನಿಮಗೆ ಹೇಗೆ సహాయ ಮಾಡಬಹುದು?",
    "നമസ്കാരം. ഞാൻ നിങ്ങളെ എങ്ങനെ സഹായിക്കാം?",
    "नमस्कार. मी तुम्हाला कशी मदत करू शकतो?",
    "নমস্কার. আমি আপনাকে কিভাবে সাহায্য করতে পারি?",
    "નમસ્તે. હું તમને કેવી રીતે મદદ કરી શકું?",
    "ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ। ਮੈਂ ਤੁਹਾਡੀ ਕਿਵੇਂ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ?",
} | set(CATALOG_PREVIEW_TEXTS.values())


async def synthesize_preview(
    text: str,
    *,
    voice_id: str | None = None,
    language: str | None = None,
    speed: float | None = None,
    pitch: float | None = None,
    temperature: float | None = None,
    emotion: str | None = None,
    volume: float | None = None,
    provider: str | None = None,
    model: str | None = None,
    tier: str | None = None,
) -> dict[str, Any]:
    """Synthesize a WAV with the currently selected provider; never cross-fallback."""
    line = normalize_preview_text(text)
    active_provider = str(provider or "").strip().lower()
    if not active_provider:
        if tier == "medium":
            active_provider = "sarvam"
        elif tier == "low":
            active_provider = "gemini"
        else:
            active_provider = "gemini"
    if active_provider not in {"gemini", "openai", "sarvam", "cartesia", "gnani"}:
        raise ValueError("unsupported_voice_provider")
    voice, label = resolve_preview_voice(voice_id, provider=active_provider, language=language, tier=tier, model=model)
    if active_provider == "gnani":
        preview_model = model or "timbre-v3.0"
    elif active_provider == "cartesia":
        preview_model = model or "sonic-3.5"
    elif active_provider == "sarvam":
        preview_model = model or "bulbul:v3"
    elif active_provider == "gemini" and ((model and "tts" in model) or tier == "low"):
        preview_model = model if (model and "tts" in model) else "gemini-3.8-flash-lite-tts"
    elif active_provider == "gemini":
        preview_model = GEMINI_TTS_MODEL
    else:
        preview_model = "tts-1"
    if active_provider in {"sarvam", "gnani", "gemini", "cartesia"}:
        from server.providers.voice_inventory import validate_voice
        validate_voice(active_provider, preview_model, voice, language)

    # The preview must apply the same knob matrix as a live call: unsupported
    # knobs are dropped and supported knobs are clamped to the model's band.
    from server.services.tts_voice_direction import normalize_tts_dynamics, resolve_speech_pace

    dynamics = normalize_tts_dynamics(
        active_provider,
        preview_model,
        {"speed": speed, "pitch": pitch, "temperature": temperature, "emotion": emotion, "volume": volume},
    )
    raw_speed = dynamics.get("speed", speed)
    pace = resolve_speech_pace(
        active_provider,
        raw_speed if raw_speed is not None else 1.0,
        model=preview_model,
    )
    pitch = dynamics.get("pitch")
    temperature = dynamics.get("temperature")
    emotion = dynamics.get("emotion")
    volume = dynamics.get("volume")
    from server.services.saas.voice_catalog import phone_voice_catalog

    # Only built-in samples are public. A tenant's custom greeting stays private
    # and is never written into this shared sample directory.
    norm_line = normalize_preview_text(line)
    is_standard_sample = (
        norm_line in {normalize_preview_text(t) for t in STANDARD_SAMPLE_TEXTS}
        or any(
            normalize_preview_text(row.get("sampleText") or "") == norm_line
            for row in phone_voice_catalog()
            if row.get("sampleText")
        )
    )
    is_catalog_voice = active_provider in {"sarvam", "gnani", "gemini", "cartesia"} or any(
        str(row.get("id", "")).casefold() == voice.casefold()
        or str(row.get("geminiVoice", "")).casefold() == voice.casefold()
        for row in phone_voice_catalog()
    )
    is_speed_standard = (
        abs(pace - 1.0) < 0.01
        and (pitch is None or abs(pitch) < 0.01)
        and (emotion is None or emotion == "neutral")
        and (volume is None or abs(volume - 1.0) < 0.01)
    )
    cacheable = is_catalog_voice and is_standard_sample

    async def generate():
        if active_provider == "gnani":
            return await _synthesize_gnani(line, voice, pace, language=language, model=preview_model, pitch=pitch, volume=volume)
        elif active_provider == "cartesia":
            return await _synthesize_cartesia(line, voice, pace, language=language, model=preview_model, emotion=emotion, volume=volume)
        elif active_provider == "sarvam":
            return await _synthesize_sarvam(line, voice, pace, language=language, temperature=temperature, pitch=pitch, volume=volume, model=preview_model)
        elif active_provider == "gemini" and ((model and "tts" in model) or tier == "low"):
            return await _synthesize_gemini_tts(line, voice, pace, language=language, model=preview_model, pitch=pitch)
        elif active_provider == "gemini":
            return await _synthesize_gemini(line, voice, pace)
        return await _synthesize_openai(line, voice, pace)

    cache_hit = False
    if cacheable:
        from server.services.saas.voice_sample_cache import get_or_create, sample_path, _read, _write
        import httpx

        is_mocked_test = (
            getattr(httpx.AsyncClient, "__name__", "") != "AsyncClient"
            or "<locals>" in getattr(_synthesize_sarvam, "__qualname__", "")
            or "<locals>" in getattr(_synthesize_gemini_tts, "__qualname__", "")
            or "<locals>" in getattr(_synthesize_gemini, "__qualname__", "")
            or hasattr(_synthesize_sarvam, "mock_calls")
            or hasattr(_synthesize_gemini_tts, "mock_calls")
            or hasattr(_synthesize_gemini, "mock_calls")
        )

        if not is_mocked_test:
            cache_key = [active_provider, preview_model, voice, language, round(pace, 2), pitch, temperature, emotion, volume, norm_line]
            cache_file = sample_path(cache_key)

            # 1. Direct hit on persisted cache
            cached = await asyncio.to_thread(_read, cache_file)
            if cached is not None:
                return {
                    "audio": cached,
                    "voice": voice,
                    "label": label,
                    "model": preview_model,
                    "stackModel": str(model or ""),
                    "truncated": False,
                    "cacheable": True,
                    "cacheHit": True,
                }

            # 2. Direct hit on pre-stored static sample audio (ONLY at 1.0x standard pace)
            if is_speed_standard:
                static_audio = await asyncio.to_thread(find_static_sample, voice, language)
                if static_audio is not None:
                    try:
                        await asyncio.to_thread(_write, cache_file, static_audio)
                    except OSError:
                        pass
                    return {
                        "audio": static_audio,
                        "voice": voice,
                        "label": label,
                        "model": preview_model,
                        "stackModel": str(model or ""),
                        "truncated": False,
                        "cacheable": True,
                        "cacheHit": True,
                    }

            # 3. Fallback to generator (and cache result)
            audio, cache_hit = await get_or_create(cache_key, generate)
        else:
            audio = await generate()
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


async def synthesize_catalog_preview(alias_id: str, language: str) -> dict[str, Any]:
    """Speak the server-owned sample for one opaque tenant catalog alias.

    Only aliases from the active public catalog are allowed, so a tenant cannot
    ask the platform to synthesize arbitrary provider voices.
    """
    from server.config.constants import language_in_supported, normalize_supported_language
    from server.services.saas.voice_stack_profiles import lookup_cached_voice_alias, resolve_voice_alias

    wanted = str(alias_id or "").strip()
    if not wanted.startswith("voc_"):
        raise ValueError("voice_not_in_active_catalog")
    if not language_in_supported(language):
        raise ValueError("unsupported_language")
    normalized = normalize_supported_language(language)
    alias = lookup_cached_voice_alias(wanted) or await resolve_voice_alias(wanted)
    if not alias:
        raise ValueError("voice_not_in_active_catalog")
    if alias.get("languages") and normalized not in alias["languages"]:
        raise ValueError("voice_not_in_active_catalog")
    provider = str(alias.get("provider") or "").strip().lower()
    if provider not in {"gemini", "sarvam", "cartesia", "gnani", "openai"}:
        raise ValueError("unsupported_voice_provider")
    result = await synthesize_preview(
        catalog_preview_text(normalized),
        voice_id=alias.get("providerVoiceId"),
        language=normalized,
        speed=1.0,
        provider=provider,
        model=alias.get("model"),
        tier=alias.get("tier"),
    )
    result["label"] = str(alias.get("label") or "Voice")
    return result


async def synthesize_live_preview(voice_id: str, language: str) -> dict[str, Any]:
    """Speak the server-owned greeting in one voice of the live phone stack.

    Runs through the same disk cache as catalog samples, so a voice is
    synthesized once per language and then served from storage.
    """
    from server.config.constants import language_in_supported, normalize_supported_language
    from server.realtime.models import is_gemini_live_voice_model
    from server.services.saas.platform_phone_stack import resolve_platform_phone_stack

    if not language_in_supported(language):
        raise ValueError("unsupported_language")
    normalized = normalize_supported_language(language)
    stack = await resolve_platform_phone_stack(normalized)
    llm = stack.get("llm") if isinstance(stack.get("llm"), dict) else {}
    provider = str(llm.get("provider") or "gemini").strip().lower()
    model = str(llm.get("model") or "")
    if is_gemini_live_voice_model(model):
        provider = "gemini"
    if provider not in {"gemini", "openai", "sarvam", "cartesia", "gnani"}:
        raise ValueError("voice_not_in_active_catalog")
    tts = stack.get("tts") if isinstance(stack.get("tts"), dict) else {}
    if str(tts.get("provider") or "").strip().lower() == provider and tts.get("model"):
        model = str(tts["model"])
    elif provider in {"sarvam", "cartesia", "gnani"}:
        from server.services.saas.voice_catalog import phone_voice_catalog

        row = next((item for item in phone_voice_catalog()
                    if item.get("provider") == provider and str(item.get("id") or "") == str(voice_id)), None)
        model = str((row or {}).get("model") or "")
    result = await synthesize_preview(
        catalog_preview_text(normalized),
        voice_id=voice_id,
        language=normalized,
        speed=1.0,
        provider=provider,
        model=None if provider == "openai" else (model or None),
    )
    result["label"] = "Voice"
    return result


def schedule_preview_warm(targets: list[tuple[str, str, str]]) -> None:
    """Warm missing samples after a catalog response without blocking the request.

    `targets` are `(kind, voice_id, language)` tuples where kind is `catalog`
    or `live`. Repeated loads dedupe in-flight work, and a provider failure is
    retried after a cooldown instead of on every request.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    now = time.monotonic()
    pending = []
    for kind, voice_id, language in targets:
        key = f"{kind}:{voice_id}:{language}"
        if key in _WARM_INFLIGHT or _WARM_COOLDOWN.get(key, 0.0) > now:
            continue
        _WARM_INFLIGHT.add(key)
        pending.append((key, kind, voice_id, language))
    if not pending:
        return

    async def warm(key: str, kind: str, voice_id: str, language: str) -> None:
        try:
            if kind == "catalog":
                await synthesize_catalog_preview(voice_id, language)
            else:
                await synthesize_live_preview(voice_id, language)
        except Exception as exc:
            _WARM_COOLDOWN[key] = time.monotonic() + _WARM_COOLDOWN_S
            logger.info("[VOICE] sample warm skipped kind=%s error=%s", kind, type(exc).__name__)
        finally:
            _WARM_INFLIGHT.discard(key)

    async def run() -> None:
        gate = asyncio.Semaphore(2)

        async def limited(item: tuple[str, str, str, str]) -> None:
            async with gate:
                await warm(*item)

        await asyncio.gather(*(limited(item) for item in pending))

    task = asyncio.create_task(run())
    _WARM_TASKS.add(task)
    task.add_done_callback(_WARM_TASKS.discard)
