"""
Language resolver — server/agent/language_resolver.py
Extensible SUPPORTED_LANGUAGES map. Phase 1: always te-IN.
"""
from __future__ import annotations

import re

from server.config.constants import constants

TELUGU_RANGE = re.compile(r"[\u0C00-\u0C7F]")
DEVANAGARI_RANGE = re.compile(r"[\u0900-\u097F]")
TAMIL_RANGE = re.compile(r"[\u0B80-\u0BFF]")
KANNADA_RANGE = re.compile(r"[\u0C80-\u0CFF]")
MALAYALAM_RANGE = re.compile(r"[\u0D00-\u0D7F]")
GUJARATI_RANGE = re.compile(r"[\u0A80-\u0AFF]")
BENGALI_RANGE = re.compile(r"[\u0980-\u09FF]")
PUNJABI_RANGE = re.compile(r"[\u0A00-\u0A7F]")
LATIN_RANGE = re.compile(r"[A-Za-z]")

_TENGLISH_KEYWORDS = re.compile(r"\b(kavali|ledu|vaddu|undi|chala|meeru|cheppandi|matladali|andi|vastanu|ayindi|namaskaram|eppudu|ekkada)\b", re.I)
_HINGLISH_KEYWORDS = re.compile(r"\b(karo|chahiye|nahi|karna|bolo|batao|mera|meri|mujhe|accha|theek|kripya|namaste|kaise|kab)\b", re.I)


def latin_only_word(text: str) -> bool:
    raw = (text or "").strip()
    if not raw or TELUGU_RANGE.search(raw) or DEVANAGARI_RANGE.search(raw):
        return False
    letters = [c for c in raw if c.isalpha()]
    return bool(letters) and all(LATIN_RANGE.match(c) for c in letters)


def is_code_mixed(transcript: str) -> bool:
    has_indic = bool(
        TELUGU_RANGE.search(transcript)
        or DEVANAGARI_RANGE.search(transcript)
        or TAMIL_RANGE.search(transcript)
        or KANNADA_RANGE.search(transcript)
    )
    return bool(has_indic and LATIN_RANGE.search(transcript))


_SHORT_ACK = re.compile(
    r"^(?:ok(?:ay)?|thanks?|thank you|yes|yeah|yep|sure|hello|hi|hey)[.!?,\s]*$",
    re.I,
)


def infer_spoken_language_from_text(text: str, *, agent_language: str = "te-IN") -> str | None:
    """Heuristic for PSTN Realtime when the caller clearly uses another product language."""
    raw = (text or "").strip()
    if len(raw) < 12 or _SHORT_ACK.match(raw):
        return None
    if len(raw.split()) <= 2 and latin_only_word(raw):
        return None

    # Check distinct native Indic script counts
    telugu = len(TELUGU_RANGE.findall(raw))
    hindi = len(DEVANAGARI_RANGE.findall(raw))
    tamil = len(TAMIL_RANGE.findall(raw))
    kannada = len(KANNADA_RANGE.findall(raw))
    malayalam = len(MALAYALAM_RANGE.findall(raw))
    gujarati = len(GUJARATI_RANGE.findall(raw))
    bengali = len(BENGALI_RANGE.findall(raw))
    punjabi = len(PUNJABI_RANGE.findall(raw))
    latin = len(LATIN_RANGE.findall(raw))

    if tamil >= max(2, latin // 2):
        return "ta-IN"
    if kannada >= max(2, latin // 2):
        return "kn-IN"
    if malayalam >= max(2, latin // 2):
        return "ml-IN"
    if gujarati >= max(2, latin // 2):
        return "gu-IN"
    if bengali >= max(2, latin // 2):
        return "bn-IN"
    if punjabi >= max(2, latin // 2):
        return "pa-IN"
    if telugu >= max(2, hindi, latin // 2):
        return "te-IN"
    if hindi >= max(2, telugu, latin // 2):
        return "hi-IN"

    if latin >= 4 and not (telugu or hindi or tamil or kannada or malayalam or gujarati or bengali or punjabi):
        # Check for romanized Indic (Tenglish or Hinglish) before defaulting to English
        if _TENGLISH_KEYWORDS.search(raw):
            return "te-IN"
        if _HINGLISH_KEYWORDS.search(raw):
            return "hi-IN"
        agent = (agent_language or "te-IN").strip().lower()
        if agent.startswith("en"):
            return "en-US" if agent == "en-us" else "en-IN"
        return "en-IN"
    return None


def resolve_language(
    detected_language: str | None,
    transcript: str,
    agent_language: str | None = None,
) -> dict:
    """
    Returns LanguageContext dict: {inputLanguage, responseLanguage, confidence, isCodeMixed}
    Supports te-IN, hi-IN, ta-IN, kn-IN, en-IN, etc.
    """
    agent_lang = agent_language or "te-IN"
    detected = detected_language or agent_lang or constants.STT_LANGUAGE_DEFAULT
    mixed = is_code_mixed(transcript)
    confidence = 0.95 if detected == agent_lang else 0.85 if mixed else 0.7
    # Use detected language if supported, else default to agent's configured language
    resp_lang = detected if detected in constants.SUPPORTED_LANGUAGES else agent_lang
    return {
        "inputLanguage": detected,
        "responseLanguage": resp_lang,
        "confidence": confidence,
        "isCodeMixed": mixed,
    }


def get_speaker_for_language(language_code: str) -> str:
    entry = constants.SUPPORTED_LANGUAGES.get(language_code)
    if entry:
        return entry["speaker"]
    return constants.SUPPORTED_LANGUAGES["te-IN"]["speaker"]
