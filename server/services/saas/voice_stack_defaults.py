"""Explicit Low/Standard mapping templates; never modify the working Live stack."""
from __future__ import annotations

from typing import Any

from server.services.saas.voice_stack_profiles import VoiceProfileError, _EVIDENCE_KEYS

# Shared recognition/text support determines the intersection for both tiers.
COMPOSED_LANGUAGES = [
    "te-IN", "hi-IN", "ta-IN", "kn-IN", "ml-IN", "mr-IN",
    "bn-IN", "gu-IN", "pa-IN", "en-IN",
]


def recommended_composed_profile(tier: str, *, allow_premium: bool = False) -> dict[str, Any]:
    """A reviewable draft with documented mappings, no fabricated release evidence.

    Sources: docs.sarvam.ai chat-completion/overview and change-the-speaker-voice;
    ai.google.dev/gemini-api/docs/speech-generation (verified 2026-10-22).
    Saving and activation remain explicit, versioned admin operations.
    """
    if tier == "premium" and not allow_premium:
        raise VoiceProfileError("read_only_tier", "The premium tier is read-only for composed voice profiles.", status_code=409)
    if tier == "premium":
        from server.realtime.models import DEFAULT_GEMINI_LIVE_MODEL
        from server.providers.voice_inventory import profile_voice_rows
        voices = profile_voice_rows("gemini", DEFAULT_GEMINI_LIVE_MODEL, COMPOSED_LANGUAGES)
        return {
            "schemaVersion": 1,
            "enabled": False,
            "label": "Gemini 3.8 Live (Flagship)",
            "supportedLanguages": list(COMPOSED_LANGUAGES),
            "stt": {"provider": "gemini", "model": "gemini-3.8-live-audio"},
            "llm": {"provider": "gemini", "modelId": DEFAULT_GEMINI_LIVE_MODEL, "apiMode": "websocket"},
            "engines": [{
                "id": "gemini-live-engine",
                "label": "Gemini Live Native Audio",
                "models": [{
                    "id": "gemini-3.8-live-tts",
                    "label": "Gemini 3.8 Live",
                    "provider": "gemini",
                    "model": DEFAULT_GEMINI_LIVE_MODEL,
                    "apiMode": "websocket",
                    "voices": voices,
                }],
            }],
            "evidence": {key: False for key in _EVIDENCE_KEYS},
        }
    # Economical tier (low) is Gemini TTS; Standard tier (medium) is Sarvam natural regional TTS; Custom tiers inherit appropriate base
    regional = tier == "medium" or (not tier.startswith("low") and "economical" not in tier)
    from server.providers.voice_inventory import profile_voice_rows
    voices = profile_voice_rows("sarvam" if regional else "gemini", "bulbul:v3" if regional else "gemini-3.8-flash-tts", COMPOSED_LANGUAGES)

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
