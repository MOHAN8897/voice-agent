"""
Language resolver — server/agent/language_resolver.py
Extensible SUPPORTED_LANGUAGES map. Phase 1: always te-IN.
"""
from __future__ import annotations

import re

from server.config.constants import constants

TELUGU_RANGE = re.compile(r"[\u0C00-\u0C7F]")
LATIN_RANGE = re.compile(r"[A-Za-z]")


def is_code_mixed(transcript: str) -> bool:
    return bool(TELUGU_RANGE.search(transcript) and LATIN_RANGE.search(transcript))


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
