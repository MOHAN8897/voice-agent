"""Caller asks for another language: offer a callback in it, never switch mid-call.

Agents run one language pack per call (brain, STT, TTS voice, pre-generated
lines). When a caller asks for a different language ("in English please",
"Hindi lo matladandi", "हिंदी में बात करो") or keeps speaking a different
language for two turns, the platform:

* explicit request for a supported language -> confirms in the call's language
  that a call back in the requested language will be arranged, records a
  durable ``language_switch`` callback item, then closes politely;
* sustained foreign-language speech -> offers that callback once and waits;
  a yes records and closes, anything else continues in the call language;
* unsupported language -> the reply model is told to say so politely and
  continue in the call language (no callback).

An opt-out always wins: no callback is offered or recorded for a caller who
also asks not to be contacted. Detection is deterministic and cross-script so
the reply model never sees an instruction to switch.
"""
from __future__ import annotations

import asyncio
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

# -- Language names, as callers say them, in every script we serve -----------------

_ALIASES: dict[str, tuple[str, ...]] = {
    "en-IN": ("english", "inglish", "angrezi", "angreji", "angrezee", "अंग्रेज़ी", "अंग्रेजी", "इंग्लिश",
              "ఇంగ్లీష్", "ఇంగ్లిష్", "ఇంగ్లీషు", "ఆంగ్లం", "ஆங்கிலம்", "இங்கிலீஷ்", "இங்கிலிஷ்",
              "ಇಂಗ್ಲಿಷ್", "ಇಂಗ್ಲೀಷ್", "ಆಂಗ್ಲ", "ઇંગ્લિશ", "અંગ્રેજી", "ഇംഗ്ലീഷ്", "इंग्रजी",
              "ইংরেজি", "ইংলিশ", "ਅੰਗਰੇਜ਼ੀ", "ਇੰਗਲਿਸ਼"),
    "hi-IN": ("hindi", "hindhi", "हिंदी", "हिन्दी", "హిందీ", "హింది", "இந்தி", "ஹிந்தி", "ಹಿಂದಿ",
              "હિન્દી", "હિંદી", "ഹിന്ദി", "হিন্দি", "ਹਿੰਦੀ"),
    "te-IN": ("telugu", "telgu", "तेलुगु", "तेलगु", "తెలుగు", "தெலுங்கு", "ತೆಲುಗು", "તેલુગુ",
              "തെലുങ്ക്", "তেলুগু", "ਤੇਲਗੂ"),
    "ta-IN": ("tamil", "thamizh", "tamizh", "तमिल", "తమిళం", "తమిళ్", "తమిళ", "தமிழ்", "தமிழ",
              "ತಮಿಳು", "ತಮಿಳ್", "તમિલ", "തമിഴ്", "তামিল", "ਤਮਿਲ"),
    "kn-IN": ("kannada", "kannad", "कन्नड़", "कन्नड", "కన్నడ", "கன்னடம்", "கன்னட", "ಕನ್ನಡ",
              "કન્નડ", "കന്നഡ", "কন্নড়"),
    "ml-IN": ("malayalam", "मलयालम", "మలయాళం", "మలయాళ", "மலையாளம்", "ಮಲಯಾಳಂ", "ಮಲಯಾಳ",
              "મલયાલમ", "മലയാളം", "মালায়ালম"),
    "gu-IN": ("gujarati", "gujrati", "गुजराती", "గుజరాతీ", "குஜராத்தி", "ಗುಜರಾತಿ", "ગુજરાતી",
              "ഗുജറാത്തി", "গুজরাটি"),
    "mr-IN": ("marathi", "मराठी", "మరాఠీ", "మరాఠి", "மராத்தி", "ಮರಾಠಿ", "મરાઠી", "മറാത്തി", "মারাঠি"),
    "bn-IN": ("bengali", "bangla", "bengoli", "बंगाली", "बांग्ला", "బెంగాలీ", "வங்காளம்", "பெங்காலி",
              "ಬಂಗಾಳಿ", "બંગાળી", "ബംഗാളി", "বাংলা", "বাঙালি"),
    "pa-IN": ("punjabi", "panjabi", "पंजाबी", "పంజాబీ", "பஞ்சாபி", "ಪಂಜಾಬಿ", "પંજાબી", "പഞ്ചാബി", "ਪੰਜਾਬੀ"),
    # Recognised so the caller hears an honest "not available", never a switch.
    "ur-IN": ("urdu", "उर्दू", "ఉర్దూ", "உருது", "ಉರ್ದು", "ઉર્દૂ", "ഉറുദു", "اردو"),
    "or-IN": ("odia", "oriya", "ओड़िया", "उड़िया", "ఒడియా", "ஒடியா", "ಒಡಿಯಾ", "ଓଡ଼ିଆ"),
    "as-IN": ("assamese", "असमिया", "অসমীয়া"),
    "fr-FR": ("french",),
    "es-ES": ("spanish",),
    "ar-AE": ("arabic",),
}

ENGLISH_NAMES: dict[str, str] = {
    "en-IN": "English", "en-US": "English", "hi-IN": "Hindi", "te-IN": "Telugu", "ta-IN": "Tamil",
    "kn-IN": "Kannada", "ml-IN": "Malayalam", "gu-IN": "Gujarati", "mr-IN": "Marathi",
    "bn-IN": "Bengali", "pa-IN": "Punjabi", "ur-IN": "Urdu", "or-IN": "Odia", "as-IN": "Assamese",
    "fr-FR": "French", "es-ES": "Spanish", "ar-AE": "Arabic",
}

#: How a target language is named inside a sentence spoken in the call language.
_NATIVE_NAMES: dict[str, dict[str, str]] = {
    "hi": {"en": "English", "hi": "हिंदी", "te": "तेलुगु", "ta": "तमिल", "kn": "कन्नड़", "ml": "मलयालम",
           "gu": "गुजराती", "mr": "मराठी", "bn": "बांग्ला", "pa": "पंजाबी"},
    "te": {"en": "English", "hi": "హిందీ", "te": "తెలుగు", "ta": "తమిళ్", "kn": "కన్నడ", "ml": "మలయాళం",
           "gu": "గుజరాతీ", "mr": "మరాఠీ", "bn": "బెంగాలీ", "pa": "పంజాబీ"},
    "ta": {"en": "English", "hi": "ஹிந்தி", "te": "தெலுங்கு", "ta": "தமிழ்", "kn": "கன்னடம்",
           "ml": "மலையாளம்", "gu": "குஜராத்தி", "mr": "மராத்தி", "bn": "பெங்காலி", "pa": "பஞ்சாபி"},
    "kn": {"en": "English", "hi": "ಹಿಂದಿ", "te": "ತೆಲುಗು", "ta": "ತಮಿಳು", "kn": "ಕನ್ನಡ", "ml": "ಮಲಯಾಳಂ",
           "gu": "ಗುಜರಾತಿ", "mr": "ಮರಾಠಿ", "bn": "ಬಂಗಾಳಿ", "pa": "ಪಂಜಾಬಿ"},
    "ml": {"en": "English", "hi": "ഹിന്ദി", "te": "തെലുങ്ക്", "ta": "തമിഴ്", "kn": "കന്നഡ", "ml": "മലയാളം"},
    "gu": {"en": "English", "hi": "હિન્દી", "te": "તેલુગુ", "ta": "તમિલ", "gu": "ગુજરાતી"},
    "mr": {"en": "English", "hi": "हिंदी", "mr": "मराठी"},
    "bn": {"en": "English", "hi": "হিন্দি", "bn": "বাংলা"},
    "pa": {"en": "English", "hi": "ਹਿੰਦੀ", "pa": "ਪੰਜਾਬੀ"},
}

# {L} is the requested language named for a listener of the call language.
_CLOSE_LINES: dict[str, str] = {
    "en": "Sure, I'll arrange a call back for you in {L}.",
    "hi": "ज़रूर, हम आपको {L} में वापस call करेंगे।",
    "te": "తప్పకుండా, మీకు {L} లో మళ్ళీ call చేస్తాం.",
    "ta": "கண்டிப்பா, உங்களுக்கு {L}ல மறுபடியும் call பண்றோம்.",
    "kn": "ಖಂಡಿತ, ನಿಮಗೆ {L}ನಲ್ಲಿ ಮತ್ತೆ call ಮಾಡ್ತೀವಿ.",
    "ml": "തീർച്ചയായും, {L} ഭാഷയിൽ നിങ്ങളെ വീണ്ടും call ചെയ്യാം.",
    "gu": "ચોક્કસ, અમે તમને {L}માં ફરીથી call કરીશું.",
    "mr": "नक्की, आम्ही तुम्हाला {L}मध्ये परत call करू.",
    "bn": "অবশ্যই, আমরা আপনাকে {L}-তে আবার call করব।",
    "pa": "ਜ਼ਰੂਰ, ਅਸੀਂ ਤੁਹਾਨੂੰ {L} ਵਿੱਚ ਦੁਬਾਰਾ call ਕਰਾਂਗੇ।",
}
_OFFER_LINES: dict[str, str] = {
    "en": "On this call I can only continue in English. Shall I arrange a call back for you in {L}?",
    "hi": "इस call पर बात हिंदी में ही हो पाएगी। क्या हम आपको {L} में वापस call करें?",
    "te": "ఈ call లో తెలుగులోనే మాట్లాడగలను. మీకు {L} లో మళ్ళీ call చేయమంటారా?",
    "ta": "இந்த call-ல தமிழ்ல மட்டும் தான் பேச முடியும். உங்களுக்கு {L}ல மறுபடியும் call பண்ணட்டுமா?",
    "kn": "ಈ call ನಲ್ಲಿ ಕನ್ನಡದಲ್ಲೇ ಮಾತಾಡೋಕೆ ಆಗುತ್ತೆ. ನಿಮಗೆ {L}ನಲ್ಲಿ ಮತ್ತೆ call ಮಾಡ್ಲಾ?",
    "ml": "ഈ call-ൽ മലയാളത്തിൽ മാത്രമേ സംസാരിക്കാൻ കഴിയൂ. {L} ഭാഷയിൽ വീണ്ടും call ചെയ്യട്ടെ?",
    "gu": "આ call પર વાત ગુજરાતીમાં જ થઈ શકશે. શું અમે તમને {L}માં ફરીથી call કરીએ?",
    "mr": "या call वर बोलणं मराठीतच होऊ शकेल. तुम्हाला {L}मध्ये परत call करू का?",
    "bn": "এই call-এ কথা বাংলাতেই হবে। আপনাকে কি {L}-তে আবার call করব?",
    "pa": "ਇਸ call ਤੇ ਗੱਲ ਪੰਜਾਬੀ ਵਿੱਚ ਹੀ ਹੋ ਸਕੇਗੀ। ਕੀ ਅਸੀਂ ਤੁਹਾਨੂੰ {L} ਵਿੱਚ ਦੁਬਾਰਾ call ਕਰੀਏ?",
}

# -- Request cues -------------------------------------------------------------------

# Speaking/switching verbs in English, Hindi/Hinglish, Telugu, Tamil, Kannada and
# the other served languages, native and romanised.
_REQUEST_VERB = re.compile(
    r"\b(?:speak|talk|converse|continue|switch|change|reply|respond|explain|say\s+it|tell\s+me|"
    r"language|bhasha|bhasa|baat|bat\s+kar|bolo|boliye|bol\s*(?:ie|iye|o|na)|samjhao|samjhaiye|batao|bataiye|"
    r"matlad\w*|maatlad\w*|matladu\w*|cheppandi|cheppu|chepp\w*|pesu\w*|pesunga|pesungo|sollunga|sollu\w*|"
    r"maatad\w*|matad\w*|maathad\w*|helri|heli|samjav\w*|bolun|bolaa)\b|"
    r"बात|बोल|समझा|बता|भाषा|आती\s*है\s*क्या|"
    r"మాట్లాడ|చెప్ప|భాష|బాష|వచ్చా|వస్తుందా|"
    r"பேச|சொல்ல|மொழி|தெரியுமா|வருமா|"
    r"ಮಾತಾಡ|ಮಾತನಾಡ|ಹೇಳ|ಭಾಷೆ|ಬರುತ್ತಾ|"
    r"സംസാരി|പറയ|ഭാഷ|"
    r"વાત|બોલ|ભાષા|"
    r"কথা|বলুন|বলো|ভাষা|"
    r"ਗੱਲ|ਬੋਲ|ਭਾਸ਼ਾ",
    re.I,
)
# "English please", "in Hindi only" — short asks with no verb.
_POLITE_ASK = re.compile(r"\b(?:please|pls|plz|only|just|madam|sir|kya|can\s+you|could\s+you|in)\b|ప్లీజ్|प्लीज़|ப்ளீஸ்|\?", re.I)
# "I don't speak Hindi", "హిందీ రాదు", "தமிழ் தெரியாது" — a statement about the caller.
_NEGATION = re.compile(
    r"\b(?:don'?t|do\s+not|doesn'?t|can'?t|cannot|can\s+not|not|no|never|nahi|nahin|nai|raadu|radu|"
    r"teliyadu|theriyadhu|theriyathu|varadhu|baralla|gottilla)\b|"
    r"नहीं|नही|मत|"
    r"రాదు|రావు|తెలియదు|వద్దు|"
    r"தெரியாது|வராது|வேண்டாம்|"
    r"ಬರಲ್ಲ|ಬರೋದಿಲ್ಲ|ಗೊತ್ತಿಲ್ಲ|ಬೇಡ|"
    r"അറിയില്ല|വേണ്ട|"
    r"નથી|નહીં",
    re.I,
)
_CLAUSE_SPLIT = re.compile(r"[,.;!?।|]+|\b(?:but|lekin|par|kani|aana|anaa|aanaa|magar)\b|लेकिन|पर\s|కానీ|ஆனால்|ஆனா|ಆದರೆ|ಆದ್ರೆ", re.I)

# -- Affirmation / decline after an offer -------------------------------------------

_YES = re.compile(
    r"\b(?:yes|yeah|yep|ya|yup|ok|okay|sure|please|fine|alright|right|haan|haa|han|ha|ji|theek|thik|"
    r"avunu|avnu|sare|saree|cheyyandi|aamaa|aama|aam|sari|seri|pannunga|houdu|haudu|madi|hoy|athe|"
    r"hoon|hanji|hā)\b|"
    r"हाँ|हां|जी|ठीक|ज़रूर|जरूर|कर\s*दीजिए|करिए|"
    r"అవును|సరే|చేయండి|తప్పకుండా|"
    r"ஆமா|ஆம்|சரி|பண்ணுங்க|"
    r"ಹೌದು|ಸರಿ|ಮಾಡಿ|"
    r"അതെ|ശരി|"
    r"હા|બરાબર|"
    r"হ্যাঁ|ঠিক|"
    r"ਹਾਂ|ਠੀਕ",
    re.I,
)
_NO = re.compile(
    r"\b(?:no|nope|nah|not\s+needed|don'?t|nahi|nahin|vaddu|vaddhu|venda|vendam|beda|illa)\b|"
    r"नहीं|मत|ज़रूरत\s*नहीं|"
    r"వద్దు|అక్కర్లేదు|అవసరం\s*లేదు|"
    r"வேண்டாம்|வேணாம்|இல்லை|"
    r"ಬೇಡ|ಬೇಡಿ|ಇಲ್ಲ|"
    r"വേണ്ട|ഇല്ല|"
    r"ના|નહીં|"
    r"না|ਨਹੀਂ",
    re.I,
)

# -- Script detection for sustained foreign-language speech -------------------------

_SCRIPT_RANGES: tuple[tuple[str, int, int], ...] = (
    ("hi-IN", 0x0900, 0x097F),  # Devanagari (Hindi is the common case; Marathi shares it)
    ("bn-IN", 0x0980, 0x09FF),
    ("pa-IN", 0x0A00, 0x0A7F),
    ("gu-IN", 0x0A80, 0x0AFF),
    ("ta-IN", 0x0B80, 0x0BFF),
    ("te-IN", 0x0C00, 0x0C7F),
    ("kn-IN", 0x0C80, 0x0CFF),
    ("ml-IN", 0x0D00, 0x0D7F),
)
_ENGLISH_FUNCTION_WORDS = frozenset(
    "i you we he she it they is are was were am be been the a an this that these those what which who "
    "how why when where can could would will should do does did have has had my your our their me us "
    "to of for in on with about from please want need know tell want speak understand not".split()
)
# Romanised Hindi/Telugu/Tamil markers: Latin text with these is code-mix, not English.
_ROMANISED_INDIC = re.compile(
    r"\b(?:hai|hain|kya|nahi|nahin|aap|mujhe|mera|meri|karo|kijiye|chahiye|accha|acha|theek|"
    r"nenu|meeru|naaku|emi|enti|ledu|undi|kavali|cheppandi|andi|"
    r"naan|neenga|enna|illa|irukku|venum|sollunga|"
    r"naanu|neevu|enu|beku|illa|ide)\b",
    re.I,
)


def _base(code: str | None) -> str:
    return str(code or "").split("-")[0].lower()


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text or "").casefold()).strip()


def _alias_pattern() -> re.Pattern[str]:
    pairs = sorted(((alias, code) for code, names in _ALIASES.items() for alias in names), key=lambda p: -len(p[0]))
    parts = []
    for alias, _code in pairs:
        escaped = re.escape(alias.casefold())
        # Latin aliases need word boundaries ("english" inside "englishman" is fine either way);
        # native aliases often carry case suffixes (హిందీలో, हिंदी में), so no right boundary.
        parts.append(rf"\b{escaped}" if alias.isascii() else escaped)
    return re.compile("|".join(parts), re.I)


_ALIAS_RE = _alias_pattern()
_ALIAS_TO_CODE = {alias.casefold(): code for code, names in _ALIASES.items() for alias in names}


def language_name(code: str | None, *, spoken_in: str | None = None) -> str:
    """Display name of ``code``; native-script form when spoken inside ``spoken_in``."""
    base = _base(code)
    if spoken_in:
        native = _NATIVE_NAMES.get(_base(spoken_in), {}).get(base)
        if native:
            return native
    return ENGLISH_NAMES.get(str(code or ""), ENGLISH_NAMES.get(f"{base}-IN", str(code or "")))


def code_for_language_name(name: str | None) -> str | None:
    """Map a free-text language name ("Hindi", "తెలుగు", "hi-IN") to a platform code."""
    raw = _norm(name or "")
    if not raw:
        return None
    from server.config.constants import normalize_supported_language, constants

    normalized = normalize_supported_language(raw)
    if normalized in constants.SUPPORTED_LANGUAGES:
        return normalized
    match = _ALIAS_RE.search(raw)
    return _ALIAS_TO_CODE.get(match.group(0).casefold()) if match else None


def is_supported_target(code: str | None) -> bool:
    """Only languages the platform offers (enabled list + spoken pack) can be promised."""
    if not code:
        return False
    try:
        from server.services.saas.platform_languages import is_enabled
        from server.prompts.agent_voice_rules import SPOKEN_PACKS

        return is_enabled(code) and (code in SPOKEN_PACKS or code.startswith("en-"))
    except Exception:
        return False


def detect_language_request(text: str, call_language: str | None) -> str | None:
    """The language the caller explicitly asks to speak, if any (not the call's own).

    Returns a code even for languages the platform does not support, so the
    caller can be told honestly; callers decide support with ``is_supported_target``.
    """
    raw = _norm(text)
    if not raw or not _ALIAS_RE.search(raw):
        return None
    call_base = _base(call_language)
    requested: list[str] = []
    for clause in (c.strip() for c in _CLAUSE_SPLIT.split(raw)):
        if not clause:
            continue
        mentions = list(_ALIAS_RE.finditer(clause))
        if not mentions:
            continue
        words = clause.split()
        short_ask = len(words) <= 4 and (bool(_POLITE_ASK.search(clause)) or len(words) <= 2)
        for index, match in enumerate(mentions):
            # Each mention owns the words between its neighbours: in "not Telugu,
            # speak English" only Telugu is negated; "I don't speak Hindi" and
            # "హిందీ రాదు" describe the caller and ask for nothing.
            start = mentions[index - 1].end() if index else 0
            end = mentions[index + 1].start() if index + 1 < len(mentions) else len(clause)
            segment = clause[start:end]
            if _NEGATION.search(segment):
                continue
            if not (_REQUEST_VERB.search(segment) or short_ask):
                continue
            code = _ALIAS_TO_CODE[match.group(0).casefold()]
            if _base(code) != call_base and code not in requested:
                requested.append(code)
    if not requested:
        return None
    # "Not Telugu, speak English": the last named non-call language is the ask.
    return requested[-1]


def utterance_language(text: str) -> str | None:
    """Dominant language of one caller turn, or None when short/mixed/ambiguous."""
    letters = [ch for ch in unicodedata.normalize("NFC", text or "") if ch.isalpha()]
    if len(letters) < 6:
        return None
    counts: dict[str, int] = {}
    latin = 0
    for ch in letters:
        cp = ord(ch)
        if cp < 0x0250:
            latin += 1
            continue
        for code, low, high in _SCRIPT_RANGES:
            if low <= cp <= high:
                counts[code] = counts.get(code, 0) + 1
                break
    if counts:
        code, n = max(counts.items(), key=lambda kv: kv[1])
        return code if n / len(letters) >= 0.6 else None
    if latin / len(letters) < 0.95:
        return None
    words = re.findall(r"[a-z']+", text.casefold())
    if len(words) < 4 or _ROMANISED_INDIC.search(text):
        return None
    function = sum(1 for w in words if w in _ENGLISH_FUNCTION_WORDS)
    return "en-IN" if function / len(words) >= 0.3 else None


def caller_affirmed(text: str) -> bool:
    raw = _norm(text)
    return bool(raw) and bool(_YES.search(raw)) and not bool(_NO.search(raw))


def caller_declined(text: str) -> bool:
    return bool(_NO.search(_norm(text)))


def close_line(call_language: str | None, target: str) -> str:
    base = _base(call_language)
    template = _CLOSE_LINES.get(base, _CLOSE_LINES["en"])
    return template.replace("{L}", language_name(target, spoken_in=call_language))


def offer_line(call_language: str | None, target: str) -> str:
    base = _base(call_language)
    template = _OFFER_LINES.get(base, _OFFER_LINES["en"])
    return template.replace("{L}", language_name(target, spoken_in=call_language))


def unsupported_hint(call_language: str | None, target: str) -> str:
    return (
        f"[Internal] The caller asked to speak {language_name(target)}, which this service does not offer. "
        f"Do not switch language. In {language_name(call_language)} ({call_language}), say politely, once, that "
        f"{language_name(target)} is not available yet, then continue helping in {language_name(call_language)}. "
        "Do not promise a callback in that language."
    )


# -- Per-call state machine ----------------------------------------------------------

PHASE_IDLE = "idle"
PHASE_OFFERED = "offered"
PHASE_DECLINED = "declined"
PHASE_RECORDED = "recorded"


@dataclass
class SwitchState:
    phase: str = PHASE_IDLE
    language: str = ""
    streak_language: str = ""
    streak: int = 0
    unsupported_noted: tuple[str, ...] = ()


def _state(ctx: Any) -> SwitchState:
    state = getattr(ctx, "language_switch_state", None)
    if not isinstance(state, SwitchState):
        state = SwitchState()
        try:
            ctx.language_switch_state = state
        except AttributeError:
            pass
    return state


def _opted_out(ctx: Any, text: str) -> bool:
    if str(getattr(ctx, "contact_preference", "") or "") == "do_not_call":
        return True
    try:
        from server.call.close_decision import opt_out_evidence
        from server.call.end_call_validate import caller_stop_contact

        return bool(opt_out_evidence(text) or caller_stop_contact(text))
    except Exception:
        return False


@dataclass(frozen=True)
class SwitchDecision:
    """``action``: close (speak + record + hang up), offer (speak + wait), hint (to the model)."""

    action: str
    language: str
    text: str = ""


def decide_language_switch(ctx: Any, transcript: str, call_language: str) -> SwitchDecision | None:
    """Pure decision for one caller turn; mutates only the per-call switch state."""
    state = _state(ctx)
    if state.phase == PHASE_RECORDED:
        return None
    text = transcript or ""
    if _opted_out(ctx, text):
        # DND wins over any language preference: no offer, no record.
        state.phase = PHASE_DECLINED if state.phase == PHASE_OFFERED else state.phase
        return None
    explicit = detect_language_request(text, call_language)
    if explicit:
        if not is_supported_target(explicit):
            if explicit in state.unsupported_noted:
                return None
            state.unsupported_noted = (*state.unsupported_noted, explicit)
            return SwitchDecision("hint", explicit, unsupported_hint(call_language, explicit))
        state.language = explicit
        return SwitchDecision("close", explicit, close_line(call_language, explicit))
    if state.phase == PHASE_OFFERED:
        if caller_affirmed(text) and not caller_declined(text):
            return SwitchDecision("close", state.language, close_line(call_language, state.language))
        state.phase = PHASE_DECLINED
        return None
    if state.phase == PHASE_DECLINED:
        return None
    spoken = utterance_language(text)
    if spoken and _base(spoken) != _base(call_language):
        state.streak = state.streak + 1 if spoken == state.streak_language else 1
        state.streak_language = spoken
    else:
        state.streak, state.streak_language = 0, ""
    if state.streak >= 2 and is_supported_target(state.streak_language):
        state.phase = PHASE_OFFERED
        state.language = state.streak_language
        return SwitchDecision("offer", state.language, offer_line(call_language, state.language))
    return None


async def apply_language_switch_close(ctx: Any, decision: SwitchDecision, call_language: str, transcript: str) -> dict[str, Any]:
    """Record the request durably, then return the server-owned close for the turn."""
    from server.call.call_end_policy import callback_save_failed_for, server_farewell_for
    from server.services.pstn_debug import log_pstn

    state = _state(ctx)
    call_id = str(getattr(ctx, "call_id", "") or "")
    saved = None
    try:
        from server.services.saas.language_switch_service import record_language_switch

        saved = await asyncio.wait_for(record_language_switch(
            ctx, requested_language=decision.language, original_language=call_language, request_text=transcript,
        ), timeout=3.0)
    except Exception as exc:  # noqa: BLE001 -- the caller must never hear a false promise.
        log_pstn("language_switch.save_failed", call_id=call_id, error_type=type(exc).__name__)
    farewell = server_farewell_for(call_language, policy=getattr(ctx, "call_end_policy", None))
    state.phase = PHASE_RECORDED
    if saved:
        text = f"{decision.text} {farewell}".strip()
        log_pstn("language_switch.recorded", call_id=call_id, requested=decision.language, original=call_language)
    else:
        text = f"{callback_save_failed_for(call_language)} {farewell}".strip()
    try:
        from server.call.contact_preference import record_contact_preference

        await record_contact_preference(call_id or None, "callback" if saved else "none")
    except Exception:
        pass
    if ctx is not None:
        ctx.agent_hangup_armed = True
    return {
        "should_end": True,
        "reason": "goal_complete",
        "farewell": text,
        "contact_preference": "callback" if saved else "none",
        "language_switch": decision.language,
    }


async def server_language_switch_turn(ctx: Any, transcript: str, call_language: str) -> dict[str, Any] | None:
    """One caller turn: None (normal reply), {"hint"} for the model, or a server-spoken turn."""
    if ctx is None or getattr(ctx, "status", "active") != "active" or not (transcript or "").strip():
        return None
    try:
        decision = decide_language_switch(ctx, transcript, call_language)
    except Exception:  # noqa: BLE001 -- detection must never break a live turn.
        return None
    if decision is None:
        return None
    if decision.action == "hint":
        return {"hint": decision.text}
    if decision.action == "offer":
        return {"text": decision.text, "language": decision.language,
                "end_call": {"should_end": False, "reason": "none", "farewell": "", "contact_preference": "none"}}
    end_call = await apply_language_switch_close(ctx, decision, call_language, transcript)
    return {"text": end_call["farewell"], "language": decision.language, "end_call": end_call}
