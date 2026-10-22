"""Explicit Low/Standard mapping templates; never modify the working Live stack."""
from __future__ import annotations

from typing import Any

from server.config.constants import constants
from server.services.saas.voice_stack_profiles import VoiceProfileError, _EVIDENCE_KEYS

# Shared recognition/text support determines the intersection for both tiers.
COMPOSED_LANGUAGES = [
    "te-IN", "hi-IN", "ta-IN", "kn-IN", "ml-IN", "mr-IN",
    "bn-IN", "gu-IN", "pa-IN", "en-IN",
]
# Curated voices: Conversational & Commercial/Promotional only
STANDARD_TTS_VOICES = (
    "Zephyr", "Puck", "Kore", "Charon", "Aoede", "Fenrir", "Leda", "Sulafat", "Pulcherrima",
)
SARVAM_COMPOSED_VOICES = (
    "shubh", "priya", "pooja", "simran", "neha", "rahul",
)


def recommended_composed_profile(tier: str) -> dict[str, Any]:
    """A reviewable draft with documented mappings, no fabricated release evidence.

    Sources: docs.sarvam.ai chat-completion/overview and change-the-speaker-voice;
    ai.google.dev/gemini-api/docs/speech-generation (verified 2026-10-22).
    Saving and activation remain explicit, versioned admin operations.
    """
    if tier not in {"low", "medium", "premium"}:
        raise VoiceProfileError("read_only_tier", "Unknown voice profile tier.", status_code=409)
    # Economical tier (low) is Gemini TTS; Standard tier (medium) is Sarvam natural regional TTS; Premium tier is Flagship Gemini
    regional = tier == "medium"
    speakers = SARVAM_COMPOSED_VOICES if regional else STANDARD_TTS_VOICES
    from server.services.saas.voice_catalog import _GEMINI_VOICE_META, _SARVAM_VOICE_META
    sarvam_map = {str(item["id"]).lower(): item for item in _SARVAM_VOICE_META}

    voices = []
    for speaker in speakers:
        clean_name = speaker.title() if regional else speaker
        meta = sarvam_map.get(speaker.lower()) if regional else _GEMINI_VOICE_META.get(speaker, {})
        gender = meta.get("gender") if meta else ("female" if speaker.lower() in {"pooja", "neha", "priya", "simran"} else "male")
        tone = meta.get("tone") if meta else ("Warm & conversational" if regional else "Bright & clear")
        category = meta.get("category") if meta else "conversational"
        use_case = meta.get("useCase") if meta else ("Conversational Customer Support" if regional else "Conversational Assistant")
        voices.append({
            "id": f"voice-{speaker.lower()}",
            "name": clean_name,
            "label": clean_name,
            "gender": gender,
            "tone": tone,
            "category": category,
            "useCase": use_case,
            "providerVoiceId": speaker,
            "languages": list(COMPOSED_LANGUAGES),
        })

    return {
        "schemaVersion": 1,
        "enabled": False,
        "supportedLanguages": list(COMPOSED_LANGUAGES),
        "stt": {"provider": "sarvam", "model": "saaras:v3-realtime"},
        "llm": {"provider": "sarvam", "modelId": "sarvam-105b-conversations", "apiMode": "chat_completions_v1"},
        "engines": [{
            "id": "regional-natural" if regional else "expressive-streaming",
            "label": "Regional Natural" if regional else "Expressive Streaming",
            "models": [{
                "id": "regional-v3" if regional else "expressive-lite",
                "label": "Regional Voice" if regional else "Expressive Voice",
                "provider": "sarvam" if regional else "gemini",
                "model": "bulbul:v3" if regional else "gemini-3.8-flash-tts",
                "apiMode": "websocket" if regional else "streaming_rest",
                "voices": voices,
            }],
        }],
        "evidence": {key: False for key in _EVIDENCE_KEYS},
    }
