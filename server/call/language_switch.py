"""Caller language changes mid-call: English fallback, callbacks for other languages.

Agents start each call in one language pack (brain, STT, TTS voice, fixed
lines). On a call whose voice loop can re-tune its speech stages
(``ctx.supports_language_switch``), the platform:

* caller asks for English, says they cannot follow the call language, or keeps
  answering only in English for two turns -> the call switches to English
  (en-IN) for the rest of the call: one late ACTIVE LANGUAGE note for the reply
  model (``with_active_language``), and the voice loop moves STT, TTS and the
  fixed lines over (``_resolve_language`` reads ``ctx.active_language``). Asking
  for the call's own language again switches back;
* caller asks for another supported language -> a durable ``language_switch``
  callback item is recorded, the reply model confirms it in the active
  language, and the call carries on (it closes only when the caller is done);
* sustained speech in another supported language -> that callback is offered
  once; a yes records it, anything else continues;
* unsupported language -> the reply model says so politely, once.

Calls that cannot re-tune (realtime pipelines) keep the earlier behaviour:
confirm a callback in the requested language, record it, close.

An opt-out always wins: no callback is offered or recorded for a caller who
also asks not to be contacted. Detection is deterministic and cross-script; the
reply model never decides to switch on its own.
"""
from __future__ import annotations

import asyncio
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
    r"maatad\w*|matad\w*|maathad\w*|helri|heli|samjav\w*|bolun|bolaa|"
    # "call me back in Hindi", "I prefer Tamil", "more comfortable in Hindi"
    r"call\s+(?:me\s+|us\s+)?back|callback|call\s+kar\w*|call\s+chey\w*|call\s+pann\w*|call\s+maad\w*|"
    r"prefer\w*|comfortable|easier)\b|"
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

# "I don't understand Telugu", "తెలుగు రాదు", "हिंदी समझ नहीं आती": the caller cannot
# follow a named language. The negation must govern a comprehension verb, so
# "no no, I know Telugu" or "no, Telugu is fine" is not read as a barrier.
_CANNOT_FOLLOW = re.compile(
    # English and Hinglish, negation before the verb or after it.
    r"\b(?:don'?t|do\s+not|didn'?t|did\s+not|doesn'?t|can'?t|cannot|can\s+not|not|never|unable\s+to)\s+"
    r"(?:\w+\s+){0,2}?(?:understand\w*|follow\w*|know|speak|talk)\b|"
    r"\b(?:samajh\w*|samaj|aata|aati|aate)\b(?:\s+\w+){0,2}?\s+(?:nahi|nahin|nai)\b|"
    r"\b(?:nahi|nahin|nai)\s+(?:\w+\s+)?(?:aata|aati|aate|samajh\w*)\b|"
    # Romanised Dravidian forms that carry the negation themselves.
    r"\b(?:raadu|radu|teliyadu|theriyadhu|theriyathu|varadhu|puriyala\w*|puriyavillai|baralla|barolla|"
    r"gottilla|gothilla|ardham\s+ka\w*ledu|artham\s+ka\w*ledu)\b|"
    # Native scripts: self-negating verbs, or a comprehension word with a negation.
    r"రాదు|రావు|తెలియదు|தெரியாது|வராது|புரியல|புரியவில்லை|ಬರಲ್ಲ|ಬರೋದಿಲ್ಲ|ಗೊತ್ತಿಲ್ಲ|അറിയില്ല|"
    r"(?:समझ|आती|आता|అర్థం|అర్ధం|ಅರ್ಥ|മനസ്സിലാ|સમજ|આવડ|বুঝ|ਸਮਝ|ਆਉਂਦ)\S*\s*(?:\S+\s+){0,2}?"
    r"(?:नहीं|नही|కాలేదు|కావట్లేదు|కావడం\s*లేదు|ఆగల్ల|ಆಗಲ್ಲ|ಆಗ್ತಿಲ್ಲ|ആകുന്നില്ല|ഇല്ല|નથી|নয়|না|ਨਹੀਂ)|"
    r"(?:नहीं|नही)\s*(?:\S+\s+){0,1}?(?:आती|आता|समझ)",
    re.I,
)
# Plain-English confusion with no language named ("Sorry, I don't understand").
_UNNAMED_CONFUSION = re.compile(
    r"\b(?:don'?t|do\s+not|didn'?t|did\s+not|can'?t|cannot|can\s+not|not\s+able\s+to|unable\s+to)\s+"
    r"(?:understand|follow)\b|\bnot\s+understanding\b|\bno\s+understand\b",
    re.I,
)

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


def callback_offer_line(call_language: str | None, target: str) -> str:
    """The offer without the "I can only continue in X" lead: the call can switch to English."""
    return re.split(r"(?<=[.।])\s+", offer_line(call_language, target), maxsplit=1)[-1]


def _latin_english(text: str) -> bool:
    letters = [ch for ch in text or "" if ch.isalpha()]
    if len(letters) < 6:
        return False
    latin = sum(1 for ch in letters if ord(ch) < 0x0250)
    return latin / len(letters) >= 0.9 and not _ROMANISED_INDIC.search(text)


def caller_cannot_follow(text: str, language: str | None) -> bool:
    """The caller says they cannot follow ``language`` (named, or plain-English confusion)."""
    raw = _norm(text)
    base = _base(language)
    if not raw or not base:
        return False
    for clause in (c.strip() for c in _CLAUSE_SPLIT.split(raw)):
        named = any(_base(_ALIAS_TO_CODE[m.group(0).casefold()]) == base for m in _ALIAS_RE.finditer(clause))
        if named and _CANNOT_FOLLOW.search(clause):
            return True
    # "Sorry, I don't understand" said in English on a non-English call.
    return base != "en" and bool(_UNNAMED_CONFUSION.search(raw)) and _latin_english(text)


# -- Per-call state machine ----------------------------------------------------------

#: The one language every live call can fall back to mid-call.
FALLBACK_LANGUAGE = "en-IN"
ACTIVE_LANGUAGE_HEADER = "--- ACTIVE LANGUAGE ("

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
    # Live switching: the language the call speaks now ("" = its own language).
    original: str = ""
    active: str = ""
    switches: list[dict[str, str]] = field(default_factory=list)
    callbacks: tuple[str, ...] = ()


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


def can_switch_live(ctx: Any) -> bool:
    """Only a voice loop that re-tunes STT/TTS mid-call sets this capability."""
    return getattr(ctx, "supports_language_switch", False) is True


def original_language(ctx: Any, fallback: str | None = None) -> str:
    state = getattr(ctx, "language_switch_state", None)
    if isinstance(state, SwitchState) and state.original:
        return state.original
    stack_language = getattr(getattr(ctx, "resolved_stack", None), "language", "")
    return stack_language if isinstance(stack_language, str) and stack_language else str(fallback or "te-IN")


def active_language(ctx: Any, fallback: str | None = None) -> str:
    """The language this call speaks now: a mid-call switch, else ``fallback``."""
    active = getattr(ctx, "active_language", "")
    return active if isinstance(active, str) and active else str(fallback or "")


@dataclass(frozen=True)
class SwitchDecision:
    """``action``: switch (live, to ``language``), callback (record + confirm, continue),
    offer (speak + wait), hint (to the model), close (speak + record + hang up; non-live calls).
    ``switch_to`` also moves a callback turn to English when the caller cannot follow."""

    action: str
    language: str
    text: str = ""
    switch_to: str = ""
    reason: str = ""


def _legacy_decision(state: SwitchState, text: str, explicit: str | None, call_language: str) -> SwitchDecision | None:
    """Calls that cannot switch live: confirm a callback in the requested language and close."""
    if explicit:
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


def decide_language_switch(ctx: Any, transcript: str, call_language: str) -> SwitchDecision | None:
    """Pure decision for one caller turn; mutates only the per-call switch state.

    ``call_language`` is the language the call speaks now (the active one).
    """
    state = _state(ctx)
    if state.phase == PHASE_RECORDED:
        return None
    text = transcript or ""
    if _opted_out(ctx, text):
        # DND wins over any language preference: no offer, no record.
        state.phase = PHASE_DECLINED if state.phase == PHASE_OFFERED else state.phase
        return None
    explicit = detect_language_request(text, call_language)
    if explicit and not is_supported_target(explicit):
        if explicit in state.unsupported_noted:
            return None
        state.unsupported_noted = (*state.unsupported_noted, explicit)
        return SwitchDecision("hint", explicit, unsupported_hint(call_language, explicit))
    if not can_switch_live(ctx):
        return _legacy_decision(state, text, explicit, call_language)

    original = original_language(ctx, call_language)
    state.original = state.original or original
    active = call_language
    cannot_follow = caller_cannot_follow(text, active)
    # Where a caller who cannot follow goes: English, or back to the call's own language.
    escape = original if _base(active) != _base(original) else FALLBACK_LANGUAGE
    escape_ok = _base(escape) != _base(active) and (escape == original or is_supported_target(escape))
    if explicit and (_base(explicit) == "en" or _base(explicit) == _base(original)):
        state.streak, state.streak_language = 0, ""
        target = FALLBACK_LANGUAGE if _base(explicit) == "en" else original
        if is_supported_target(target) or target == original:
            return SwitchDecision("switch", target, reason="asked")
    if explicit:
        # Any other supported language: a call back in it, while this call carries on.
        state.streak, state.streak_language = 0, ""
        if explicit in state.callbacks:
            return None
        return SwitchDecision("callback", explicit, close_line(active, explicit),
                              switch_to=escape if cannot_follow and escape_ok else "", reason="asked")
    if cannot_follow and escape_ok:
        state.streak, state.streak_language = 0, ""
        return SwitchDecision("switch", escape, reason="cannot_follow")
    if state.phase == PHASE_OFFERED:
        if caller_affirmed(text) and not caller_declined(text):
            state.phase = PHASE_IDLE
            return SwitchDecision("callback", state.language, close_line(active, state.language), reason="offer_accepted")
        state.phase = PHASE_DECLINED
        return None
    spoken = utterance_language(text)
    if spoken and _base(spoken) != _base(active) and _base(spoken) != _base(original):
        state.streak = state.streak + 1 if spoken == state.streak_language else 1
        state.streak_language = spoken
    else:
        state.streak, state.streak_language = 0, ""
    if state.streak < 2 or not is_supported_target(state.streak_language):
        return None
    language, state.streak, state.streak_language = state.streak_language, 0, ""
    if _base(language) == "en":
        # Two English-only answers: the caller is more at home in English.
        return SwitchDecision("switch", FALLBACK_LANGUAGE, reason="answered_in_english")
    if state.phase == PHASE_DECLINED or language in state.callbacks:
        return None
    state.phase = PHASE_OFFERED
    state.language = language
    return SwitchDecision("offer", language, callback_offer_line(active, language))


# -- Applying a decision -------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _persist_switches(call_id: str, active: str, switches: list[dict[str, str]]) -> None:
    from server.call.call_ledger import call_ledger

    meta = call_ledger.read_meta(call_id)
    if not meta:
        return
    meta["active_language"] = active
    meta["language_switches"] = list(switches)
    call_ledger.write_meta(call_id, meta)


async def switch_active_language(ctx: Any, language: str, *, reason: str) -> str:
    """Move the live call to ``language``; returns the language it was speaking."""
    from server.services.pstn_debug import log_pstn

    state = _state(ctx)
    previous = active_language(ctx, original_language(ctx))
    state.original = state.original or original_language(ctx, previous)
    state.active = "" if language == state.original else language
    state.phase = PHASE_IDLE if state.phase == PHASE_OFFERED else state.phase
    state.switches.append({"from": previous, "to": language, "reason": reason, "at": _now_iso()})
    ctx.active_language = state.active
    call_id = str(getattr(ctx, "call_id", "") or "")
    log_pstn("language_switch.live", call_id=call_id, previous=previous, active=language, reason=reason)
    if call_id:
        try:
            await asyncio.to_thread(_persist_switches, call_id, language, state.switches)
        except Exception as exc:  # noqa: BLE001 -- bookkeeping must not break the turn.
            log_pstn("language_switch.meta_failed", call_id=call_id, error_type=type(exc).__name__)
    listener = getattr(ctx, "language_switch_listener", None)
    if callable(listener):
        try:
            listener(language)
        except Exception as exc:  # noqa: BLE001
            log_pstn("language_switch.listener_failed", call_id=call_id, error_type=type(exc).__name__)
    return previous


def switch_hint(language: str, previous: str, reason: str) -> str:
    asked = "asked to continue in" if reason == "asked" else "is more comfortable in"
    return (
        f"[Internal] The caller {asked} {language_name(language)}. From this reply on, speak natural "
        f"{language_name(language)} ({language}) as the ACTIVE LANGUAGE note says. Acknowledge the switch in a few "
        "words, then continue from where the conversation was and answer anything they asked. Do not repeat the "
        f"opening and do not ask them to speak {language_name(previous)}."
    )


def callback_hint(confirmation: str, requested: str, saved: bool, language: str) -> str:
    if not saved:
        from server.call.call_end_policy import callback_save_failed_for

        return (
            f"[Internal] The caller asked for a call back in {language_name(requested)}, but it could not be saved. "
            f"In {language_name(language)}, say once: '{callback_save_failed_for(language)}' Then keep helping. "
            "Do not promise a callback."
        )
    return (
        f"[Internal] A call back in {language_name(requested)} is now recorded for this caller. Begin your reply "
        f"with exactly: '{confirmation}' Then keep helping in {language_name(language)}: answer anything else they "
        "asked. Do not promise a time and do not end the call unless the caller is done."
    )


async def record_language_callback(ctx: Any, requested: str, original: str, transcript: str) -> bool:
    from server.services.pstn_debug import log_pstn

    call_id = str(getattr(ctx, "call_id", "") or "")
    try:
        from server.services.saas.language_switch_service import record_language_switch

        saved = await asyncio.wait_for(record_language_switch(
            ctx, requested_language=requested, original_language=original, request_text=transcript,
        ), timeout=3.0)
    except Exception as exc:  # noqa: BLE001 -- the caller must never hear a false promise.
        log_pstn("language_switch.save_failed", call_id=call_id, error_type=type(exc).__name__)
        saved = None
    if saved:
        log_pstn("language_switch.recorded", call_id=call_id, requested=requested, original=original)
        try:
            from server.call.contact_preference import record_contact_preference

            await record_contact_preference(call_id or None, "callback")
        except Exception:
            pass
    return bool(saved)


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
    """One caller turn: None (normal reply), {"hint", "active_language"} for the model, or a server-spoken turn."""
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
    if decision.action == "switch":
        previous = await switch_active_language(ctx, decision.language, reason=decision.reason)
        return {"hint": switch_hint(decision.language, previous, decision.reason), "active_language": decision.language}
    if decision.action == "callback":
        state = _state(ctx)
        active = call_language
        hints = []
        if decision.switch_to:
            previous = await switch_active_language(ctx, decision.switch_to, reason="cannot_follow")
            hints.append(switch_hint(decision.switch_to, previous, "cannot_follow"))
            active = decision.switch_to
        saved = await record_language_callback(ctx, decision.language, original_language(ctx, call_language), transcript)
        if saved:
            state.callbacks = (*state.callbacks, decision.language)
        hints.append(callback_hint(close_line(active, decision.language), decision.language, saved, active))
        return {"hint": "\n".join(hints), "active_language": active}
    if decision.action == "offer":
        return {"text": decision.text, "language": decision.language,
                "end_call": {"should_end": False, "reason": "none", "farewell": "", "contact_preference": "none"}}
    end_call = await apply_language_switch_close(ctx, decision, call_language, transcript)
    return {"text": end_call["farewell"], "language": decision.language, "end_call": end_call}


# -- Reply-model input ----------------------------------------------------------------

def active_language_note(active: str, original: str) -> str:
    """The late note that carries the active spoken pack; the cached brain stays untouched."""
    from server.prompts.agent_voice_rules import spoken_pack_for

    name, before = language_name(active), language_name(original)
    return (
        f"{ACTIVE_LANGUAGE_HEADER}{active}) ---\n"
        f"This call has switched from {before} to {name}. Reply only in natural {name} for the rest of the call "
        f"unless a newer note says otherwise. This overrides every earlier language instruction (primary language, "
        f"selected session language, language mismatch, 'Language: {original}'). Business facts and the script "
        f"still apply; say them in {name}.\n\n"
        + spoken_pack_for(active, include_brevity=False, core_only=True)
    )


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(part.get("text") or "") for part in content if isinstance(part, dict))
    return ""


def with_active_language(messages: list[dict[str, Any]] | None, ctx: Any) -> list[dict[str, Any]] | None:
    """Replace (never stack) the single ACTIVE LANGUAGE note, placed just before the caller's turn.

    Messages before it, including the cached compiled brain, are left untouched.
    """
    if not messages:
        return messages
    kept = [m for m in messages if not _message_text(m).startswith(ACTIVE_LANGUAGE_HEADER)]
    active = active_language(ctx)
    original = original_language(ctx, active)
    if not active or _base(active) == _base(original):
        return kept
    note = {"type": "message", "role": "developer",
            "content": [{"type": "input_text", "text": active_language_note(active, original)}]}
    index = len(kept) - 1 if kept and kept[-1].get("role") == "user" else len(kept)
    return [*kept[:index], note, *kept[index:]]
