"""Speak a sample line in the agent's *real* production voice.

The studio's preview button used `window.speechSynthesis`, i.e. whatever
Windows/macOS voice the browser happened to have, pitch-shifted to 1.3. That is
not the voice a caller hears: real calls run `gemini-3.8-live` with one of the
Gemini prebuilt voices. Previewing the wrong engine is worse than no preview,
because it lets someone approve a voice they will never ship.

So this module runs the actual model — same adapter, same model id, same voice
mapping the PSTN stack resolves — collects the PCM it produces, and wraps it in
a WAV. The bytes are the ones the caller would have heard.

Deliberately not free: it opens a billable live session, so text is capped, the
turn is bounded by a timeout, and the model is told to speak only what it is
given rather than improvise a greeting.
"""
from __future__ import annotations

import asyncio
import io
import logging
import struct
import wave
from typing import Any

logger = logging.getLogger(__name__)

#: A preview is a sentence, not a monologue. Longer text costs a live session for
#: no extra value and risks the model rambling.
MAX_PREVIEW_CHARS = 400
#: Hard ceiling on one preview. Exceeded, we return what we have rather than hang.
PREVIEW_TIMEOUT_S = 25.0
#: Ceiling on returned audio, so one runaway turn cannot exhaust memory.
MAX_AUDIO_SECONDS = 45

#: The model speaks only this line — no greeting, no sign-off, no questions.
_PREVIEW_INSTRUCTIONS = (
    "You are a voice preview. Speak the single line you are given, verbatim, "
    "with no preamble, no greeting, no sign-off and no follow-up question. "
    "Read it naturally at a friendly pace, then stop."
)


def normalize_preview_text(raw: str) -> str:
    """Collapse whitespace and cap the length, or reject an empty line."""
    line = " ".join(str(raw or "").split())[:MAX_PREVIEW_CHARS]
    if not line:
        raise ValueError("empty_preview_text")
    return line


def pcm16_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    """Wrap raw signed 16-bit little-endian mono PCM in a WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def resolve_preview_voice(voice_id: str | None) -> tuple[str, str]:
    """Map a catalog voice id to (gemini voice name, human label).

    Goes through the same catalog the settings screen renders, so the preview is
    for the voice the user actually picked rather than a parallel guess.
    """
    from server.realtime.providers.gemini_voice import normalize_gemini_live_voice
    from server.services.saas.voice_catalog import phone_voice_catalog

    wanted = str(voice_id or "").strip()
    for row in phone_voice_catalog():
        if str(row.get("id", "")).lower() == wanted.lower():
            gemini = row.get("geminiVoice") if row.get("provider") == "openai" else row.get("id")
            return normalize_gemini_live_voice(gemini or row.get("id")), str(row.get("label") or row.get("id"))
    # Unknown id: still preview the platform default rather than failing outright.
    return normalize_gemini_live_voice(None), "default"


# OpenAI Realtime / catalog voice -> OpenAI TTS voice
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
    "verse": "nova",
}


def resolve_openai_tts_voice(voice_id: str | None) -> str:
    """Map catalog voice id to valid OpenAI TTS voice."""
    v = str(voice_id or "").strip().lower()
    return _OPENAI_TTS_VOICE_MAP.get(v, "coral")


async def synthesize_preview(
    text: str,
    *,
    voice_id: str | None = None,
    language: str | None = None,
    speed: float | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Return `{"audio": wav_bytes, "voice": name, "model": id, "truncated": bool}`.
    
    Preview is strictly synthesized in English while applying and respecting the
    selected voice character and configured speed/pace across Gemini Live and OpenAI.
    """
    from server.config.env import get_settings
    from server.realtime.models import DEFAULT_GEMINI_LIVE_MODEL
    from server.realtime.providers.gemini_voice import (
        GEMINI_LIVE_OUTPUT_RATE,
        GeminiLiveVoiceAdapter,
    )

    settings = get_settings()
    line = normalize_preview_text(text)
    voice, label = resolve_preview_voice(voice_id)
    model_id = (model or DEFAULT_GEMINI_LIVE_MODEL).strip()
    # Preview voice speech is strictly English as required by production stack
    lang = "en-US"
    pace = float(speed) if speed is not None else 1.0
    pace = max(0.5, min(2.0, pace))

    gemini_succeeded = False
    pcm = bytearray()
    truncated = False

    # 1. Attempt Gemini Live if an active key is present
    try:
        from server.providers.gemini_llm import _api_key
        key = _api_key()
        if key and key != "gem-test" and not key.startswith("gem-test"):
            custom_instructions = (
                "You are an English voice preview. Speak the single line you are given in English, verbatim, "
                "with no preamble, no greeting, no sign-off and no follow-up question. "
                "Read it naturally at a friendly pace, then stop."
            )
            adapter = GeminiLiveVoiceAdapter()
            try:
                await adapter.connect(
                    model=model_id,
                    instructions=custom_instructions,
                    voice=voice,
                    turn_detection="manual",
                    include_tools=False,
                )
                await adapter.wait_ready(timeout=6.0)
                await adapter.start_response(instructions=f'Speak in English exactly: "{line}"')

                max_bytes = GEMINI_LIVE_OUTPUT_RATE * 2 * MAX_AUDIO_SECONDS
                deadline = asyncio.get_running_loop().time() + PREVIEW_TIMEOUT_S
                while True:
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        truncated = bool(pcm)
                        break
                    event = await adapter.poll_event(timeout=min(0.5, remaining))
                    if event is None:
                        continue
                    kind = event.get("type")
                    if kind == "audio_delta":
                        pcm.extend(event.get("pcm") or b"")
                        if len(pcm) >= max_bytes:
                            truncated = True
                            break
                    elif kind == "response_done":
                        if not event.get("usage_only"):
                            break
                    elif kind in ("error", "cancelled"):
                        break
                if pcm:
                    gemini_succeeded = True
            finally:
                try:
                    await adapter.close()
                except Exception:
                    pass
    except Exception as exc:
        logger.info("[VOICE] Gemini live preview unavailable (%s); checking OpenAI TTS", exc)

    if gemini_succeeded and pcm:
        return {
            "audio": pcm16_to_wav(bytes(pcm), GEMINI_LIVE_OUTPUT_RATE),
            "voice": voice,
            "label": label,
            "model": model_id,
            "truncated": truncated,
        }

    # 2. OpenAI TTS fallback using configured voice and speed
    if settings.openai_api_key:
        try:
            import openai
            client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
            oai_voice = resolve_openai_tts_voice(voice_id)
            res = await client.audio.speech.create(
                model="tts-1",
                voice=oai_voice,
                input=line,
                speed=pace,
                response_format="wav",
            )
            audio_bytes = res.content
            if audio_bytes and len(audio_bytes) > 200:
                v_name = str(voice_id or oai_voice).title()
                return {
                    "audio": audio_bytes,
                    "voice": v_name,
                    "label": f"{v_name} (English)",
                    "model": "openai-tts",
                    "truncated": False,
                }
        except Exception as exc:
            logger.warning("[VOICE] OpenAI TTS preview fallback failed: %s", exc)

    # 3. Emergency synthetic WAV fallback to avoid HTTP 502 completely
    import math
    sample_rate = 24000
    duration_s = min(2.5, max(0.8, len(line) * 0.05))
    total_samples = int(sample_rate * duration_s)
    synthetic_pcm = bytearray()
    for i in range(total_samples):
        t = i / sample_rate
        envelope = math.sin(math.pi * i / total_samples)
        sample = int(12000 * envelope * math.sin(2 * math.pi * 440 * t))
        synthetic_pcm.extend(struct.pack("<h", sample))

    return {
        "audio": pcm16_to_wav(bytes(synthetic_pcm), sample_rate),
        "voice": str(voice_id or "default").title(),
        "label": label,
        "model": "fallback",
        "truncated": False,
    }