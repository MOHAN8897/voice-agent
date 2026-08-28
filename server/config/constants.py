"""
Central constants — server/config/constants.py
Single source for limits, timeouts, language map, provider catalogs (verified vs docs Aug 2026).
"""
from __future__ import annotations


class Constants:
    # Audio
    MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10 MB
    MAX_AUDIO_DURATION_S = 30  # Sarvam REST limit
    PREFERRED_SAMPLE_RATE = 16000

    # TTS
    TTS_MAX_CHARS_REST = 2500
    TTS_MAX_CHARS_STREAM = 3500

    # STT
    STT_LANGUAGE_DEFAULT = "te-IN"

    # ---- Provider catalogs (verified from docs.sarvam.ai Aug 2026) ----
    # STT models — saaras:v3 recommended; saaras:v4 latest (Global English); saarika legacy
    STT_MODELS: dict[str, dict] = {
        "saaras:v3": {"label": "Saaras v3 (recommended)", "modes": ["transcribe", "translate", "verbatim", "translit", "codemix"]},
        "saaras:v3-realtime": {"label": "Saaras v3 Realtime (WS)", "modes": ["transcribe", "translate", "verbatim", "translit", "codemix"], "realtime": True},
        "saaras:v4": {"label": "Saaras v4 (latest, Global English)", "modes": ["transcribe", "translate", "verbatim", "translit", "codemix"]},
        "saarika:v2.5": {"label": "Saarika v2.5 (legacy)", "modes": ["transcribe"]},
    }
    STT_MODES = ["transcribe", "translate", "verbatim", "translit", "codemix"]
    STT_STREAM_TYPES = ["fast", "balanced", "simulated"]  # realtime WS only

    # TTS models — bulbul:v3 supports temperature (0.01-1.0), pace 0.5-2.0, NO pitch/loudness
    TTS_MODELS: dict[str, dict] = {
        "bulbul:v3": {"label": "Bulbul v3 (recommended, temperature)", "pace": [0.5, 2.0], "temperature": [0.01, 1.0], "pitch": None, "loudness": None},
        "bulbul:v2": {"label": "Bulbul v2 (legacy, pitch/loudness)", "pace": [0.3, 3.0], "temperature": None, "pitch": [-0.75, 0.75], "loudness": [0.3, 3.0]},
    }
    TTS_SPEAKERS_V3 = [
        "shubh", "aditya", "ritu", "priya", "neha", "rahul", "pooja", "rohan", "simran",
        "kavya", "amit", "dev", "ishita", "shreya", "ratan", "varun", "manan", "sumit",
        "roopa", "kabir", "aayan", "ashutosh", "advait", "anand", "tanya", "tarun",
        "sunny", "mani", "gokul", "vijay", "shruti", "suhani", "mohit", "kavitha",
        "rehan", "soham", "rupali",
    ]
    TTS_SPEAKERS_V2 = ["anushka", "manisha", "vidya", "arya", "abhilash", "karun", "hitesh"]
    TTS_CODECS = ["mp3", "wav", "aac", "opus", "flac", "linear16", "mulaw", "alaw"]
    TTS_BITRATES = ["32k", "64k", "96k", "128k", "192k"]
    TTS_SAMPLE_RATES = [8000, 16000, 22050, 24000]

    # Supported languages — extensible by config
    SUPPORTED_LANGUAGES: dict[str, dict[str, str]] = {
        "te-IN": {"sttCode": "te-IN", "ttsCode": "te-IN", "speaker": "shubh", "name": "Telugu"},
        "hi-IN": {"sttCode": "hi-IN", "ttsCode": "hi-IN", "speaker": "shubh", "name": "Hindi"},
        "en-IN": {"sttCode": "en-IN", "ttsCode": "en-IN", "speaker": "shubh", "name": "English"},
    }

    # Tiers (L1 stack bundles — assignments configured via env / Dev Portal)
    TIER_NAMES = ("low", "medium", "premium")

    # App
    APP_VERSION = "0.4.0-phase3"

    # Cartesia catalogs (docs.cartesia.ai — Aug 2026)
    CARTESIA_STT_MODELS: dict[str, dict] = {
        "ink-2": {
            "label": "Ink 2 (English, streaming)",
            "languages": ["en", "en-IN"],
            "modes": ["transcribe"],
            "realtime": True,
        },
        "ink-whisper": {
            "label": "Ink Whisper (multilingual incl. Telugu)",
            "languages": ["en", "te", "hi", "multilingual"],
            "modes": ["transcribe"],
            "realtime": True,
        },
    }
    CARTESIA_TTS_MODELS: dict[str, dict] = {
        "sonic-3.5": {"label": "Sonic 3.5 (42 languages incl. Telugu)"},
        "sonic-3.5-2026-05-04": {"label": "Sonic 3.5 snapshot (2026-05-04)"},
    }
    CARTESIA_STT_WS = "wss://api.cartesia.ai/stt/websocket"
    CARTESIA_TTS_WS = "wss://api.cartesia.ai/tts/websocket"
    CARTESIA_API_VERSION = "2026-08-14"
    # Fallback when CARTESIA_TTS_VOICE_ID unset (Cartesia "Skylar")
    CARTESIA_DEFAULT_VOICE_ID = "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4"

    # Sarvam endpoints
    SARVAM_STT_REALTIME_WS = "wss://api.sarvam.ai/speech-to-text-realtime/ws"
    SARVAM_TTS_WS = "wss://api.sarvam.ai/text-to-speech/ws"


constants = Constants()
