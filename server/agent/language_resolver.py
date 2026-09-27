"""
Language resolver — server/agent/language_resolver.py
Extensible SUPPORTED_LANGUAGES map. Phase 1: always te-IN.
"""
from __future__ import annotations

import re

from server.config.constants import constants

TELUGU_RANGE = re.compile(r"[\u0C00-\u0C7F]")
DEVANAGARI_RANGE = re.compile(r"[\u0900-\u097F]")
LATIN_RANGE = re.compile(r"[A-Za-z]")


def is_code_mixed(transcript: str) -> bool:
    return bool(TELUGU_RANGE.search(transcript) and LATIN_RANGE.search(transcript))


def infer_spoken_language_from_text(text: str, *, agent_language: str = "te-IN") -> str | None:
    """Heuristic for PSTN Realtime when the caller clearly uses another product language."""
    raw = (text or "").strip()
    if len(raw) < 6:
        return None
    telugu = len(TELUGU_RANGE.findall(raw))
    hindi = len(DEVANAGARI_RANGE.findall(raw))
    latin = len(LATIN_RANGE.findall(raw))
    letters = telugu + hindi + latin
    if letters < 4:
        return None
    if telugu >= max(2, hindi, latin // 2):
        return "te-IN"
    if hindi >= max(2, telugu, latin // 2):
        return "hi-IN"
    if latin >= 4 and telugu == 0 and hindi == 0:
        agent = (agent_language or "te-IN").strip().lower()
        if agent.startswith("en"):
            return "en-US" if agent == "en-us" else "en-IN"
        return "en-IN"
    return None


def resolve_language(
    detected_language: str | None,
    transcript: str,
) -> dict:
    """
    Returns LanguageContext dict: {inputLanguage, responseLanguage, confidence, isCodeMixed}
    Phase 1 Telugu-first: responseLanguage always te-IN.
    Future: map hi-IN→hi-IN, en-IN→en-IN.
    """
    detected = detected_language or constants.STT_LANGUAGE_DEFAULT
    mixed = is_code_mixed(transcript)
    # Confidence heuristic: if transcript has Telugu chars but detected is unknown, still te-IN
    confidence = 0.95 if detected == "te-IN" else 0.85 if mixed else 0.7
    return {
        "inputLanguage": detected,
        "responseLanguage": "te-IN",  # Phase 1 fixed; Phase 4 makes configurable
        "confidence": confidence,
        "isCodeMixed": mixed,
    }


def get_speaker_for_language(language_code: str) -> str:
    entry = constants.SUPPORTED_LANGUAGES.get(language_code)
    if entry:
        return entry["speaker"]
    return constants.SUPPORTED_LANGUAGES["te-IN"]["speaker"]
