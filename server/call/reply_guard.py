"""Deterministic last-mile checks on a live reply, in every supported language.

The reply model is asked not to invent business facts, repeat itself or use the
slow-down line without cause, but a prompt is a request, not a guarantee. These
guards run on the finished reply text before it is spoken and need no extra
model round trip. Each one either leaves the reply alone or makes one cheap,
explainable rewrite and names the reason.

Phrase tables cover every supported language (te/hi/ta/kn/ml/mr/bn/gu/pa/en);
nothing is keyed on a tenant, an agent or a product.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Any

# Punctuation that separates spoken words in every supported script.
_PUNCT = r"\s.,!?।॥;:\"'“”‘’()\[\]{}\-–—…/|*_~`"
_TOKEN = re.compile(rf"[^{_PUNCT}]+")
_SENTENCE = re.compile(r"[^.!?।]+[.!?।]*")
_CLAUSE = re.compile(r"[^,.!?।;]+[,.!?।;]*")
_HEAD_CLAUSE = re.compile(r"\s*[^,.!?।;]+[,.!?।;]+")


def _lang(language: str | None) -> str:
    return (str(language or "en").split("-")[0] or "en").lower()


def tokens(text: str | None) -> list[str]:
    return _TOKEN.findall((text or "").casefold())


def norm_speech(text: str | None) -> str:
    """Casefolded words without spaces or punctuation, for containment and similarity."""
    return "".join(tokens(text))


_norm = norm_speech


def sentences(text: str | None) -> list[str]:
    return [s.strip() for s in _SENTENCE.findall(text or "") if _norm(s)]


def _join(parts: list[str]) -> str:
    return " ".join(p.strip() for p in parts if p and p.strip()).strip()


def _terms(*pools: list[str]) -> re.Pattern[str]:
    """Latin terms match whole words; Indic terms match inside agglutinated words."""
    words = sorted({w.casefold() for pool in pools for w in pool if w.strip()}, key=len, reverse=True)
    parts = [
        rf"(?<![a-z]){re.escape(w)}(?![a-z])" if re.fullmatch(r"[a-z0-9 .'%\-]+", w) else re.escape(w)
        for w in words
    ]
    return re.compile("|".join(parts) or r"(?!)", re.I)


# --- acknowledgements and fillers ---------------------------------------------------------

# Agreement, thanks and filler a caller says without adding information.
ACKNOWLEDGEMENTS: dict[str, list[str]] = {
    "en": ["yes", "yeah", "yep", "yup", "ya", "yah", "ok", "okay", "okey", "k", "sure", "hmm", "hm", "mm",
           "mhm", "uh huh", "right", "correct", "got it", "i see", "alright", "all right", "fine", "no problem",
           "no worries", "thank you", "thanks", "thank you so much", "cool", "great", "good", "nice", "oh",
           "ah", "aa", "sir", "madam", "ma'am", "haan", "haanji", "ji", "accha", "achha", "theek hai", "sari",
           "sare", "avunu", "avunandi", "parledu", "parvaledu", "andi"],
    "te": ["అవును", "అవునండి", "అవునండీ", "అవు", "సరే", "సరేనండి", "సరే అండి", "అలాగే", "అలాగేనండి", "ఓకే",
           "ఓకేనండి", "ఓకేండి", "ఓకె", "యా", "యస్", "ఎస్", "హా", "హాఁ", "హ్మ్", "హ్మ్మ్", "ఆ", "ఆఁ", "అండి",
           "అండీ", "పర్లేదు", "పర్లేదండి", "పర్వాలేదు", "పర్వాలేదండి", "బాగుంది", "థ్యాంక్ యూ", "థాంక్ యూ",
           "థాంక్యూ", "థ్యాంక్స్", "ధన్యవాదాలు", "కరెక్ట్", "ఓహో", "అచ్చా", "సార్", "మేడం"],
    "hi": ["हाँ", "हां", "हाँजी", "हांजी", "हाँ जी", "जी", "जी हाँ", "जी हां", "ठीक", "ठीक है", "अच्छा",
           "अच्छा जी", "ओके", "ओके जी", "हम्म", "हम्म्म", "सही", "सही है", "बढ़िया", "धन्यवाद", "थैंक यू",
           "थैंक्स", "शुक्रिया", "कोई बात नहीं", "चलो", "यस", "सर", "मैडम"],
    "ta": ["ஆம்", "ஆமாம்", "ஆமாங்க", "ஆமா", "சரி", "சரிங்க", "ஓகே", "ஓகேங்க", "ம்ம்", "ம்", "ஹ்ம்",
           "பரவாயில்லை", "பரவால்ல", "நன்றி", "தேங்க்ஸ்", "தேங்க் யூ", "சூப்பர்", "ஆ", "சார்", "மேடம்"],
    "kn": ["ಹೌದು", "ಹೌದೌದು", "ಹೌದುರೀ", "ಸರಿ", "ಸರೀ", "ಆಯಿತು", "ಆಯ್ತು", "ಓಕೆ", "ಹ್ಮ್", "ಪರವಾಗಿಲ್ಲ",
           "ಧನ್ಯವಾದ", "ಧನ್ಯವಾದಗಳು", "ಥ್ಯಾಂಕ್ಸ್", "ಚೆನ್ನಾಗಿದೆ", "ರೀ", "ಸಾರ್", "ಮೇಡಂ"],
    "ml": ["അതെ", "ശരി", "ശരിയാണ്", "ഓക്കെ", "ഓകെ", "ഉം", "ഹ്മ്", "കുഴപ്പമില്ല", "നന്ദി", "താങ്ക്സ്",
           "കൊള്ളാം", "ആ", "സാർ", "മാഡം"],
    "mr": ["हो", "होय", "हो ना", "बरं", "बरे", "ठीक", "ठीक आहे", "ओके", "हम्म", "छान", "समजले",
           "काही हरकत नाही", "धन्यवाद", "थँक्यू", "सर", "मॅडम"],
    "bn": ["হ্যাঁ", "হাঁ", "ঠিক", "ঠিক আছে", "আচ্ছা", "ওকে", "হুম", "বেশ", "বুঝেছি", "কোনো সমস্যা নেই",
           "ধন্যবাদ", "থ্যাংক ইউ", "স্যার", "ম্যাডাম"],
    "gu": ["હા", "હાજી", "બરાબર", "બરાબર છે", "સારું", "ઠીક", "ઠીક છે", "ઓકે", "હમ્મ", "વાંધો નહીં",
           "આભાર", "થેંક યુ", "સમજાયું", "સર", "મેડમ"],
    "pa": ["ਹਾਂ", "ਹਾਂਜੀ", "ਜੀ", "ਠੀਕ", "ਠੀਕ ਹੈ", "ਚੰਗਾ", "ਓਕੇ", "ਹੰਮ", "ਕੋਈ ਗੱਲ ਨਹੀਂ", "ਧੰਨਵਾਦ",
           "ਸ਼ੁਕਰੀਆ", "ਥੈਂਕ ਯੂ", "ਸਰ", "ਮੈਡਮ"],
}
_ACK_PHRASES = sorted(
    {tuple(tokens(p)) for pool in ACKNOWLEDGEMENTS.values() for p in pool if tokens(p)},
    key=len, reverse=True,
)
_ACK_TOKENS = {t for phrase in _ACK_PHRASES for t in phrase if len(phrase) == 1}


def is_acknowledgement(text: str | None) -> bool:
    """True when every word is agreement, thanks or filler ("ok ok", "అవును అవునండి")."""
    words = tokens(text)
    if not words:
        return False
    position = 0
    while position < len(words):
        for phrase in _ACK_PHRASES:
            if tuple(words[position:position + len(phrase)]) == phrase:
                position += len(phrase)
                break
        else:
            return False
    return True


def _same_word(a: str, b: str) -> bool:
    # "సరే" / "సరేనండి", "ji" / "jee": honorific suffixes do not make a new word.
    return a == b or (min(len(a), len(b)) >= 3 and (a.startswith(b) or b.startswith(a)))


def strip_filler_echo(reply: str, caller: str) -> str:
    """Drop a leading clause that only repeats the caller's own filler or acknowledgement."""
    caller_words = tokens(caller)
    text = (reply or "").strip()
    for _ in range(2):
        match = _HEAD_CLAUSE.match(text)
        if match is None:
            break
        head = match.group(0)
        head_words = tokens(head)
        if not head_words or not is_acknowledgement(head):
            break
        if not any(_same_word(w, c) for w in head_words for c in caller_words):
            break
        rest = text[len(head):].strip()
        if not _norm(rest):
            break
        text = rest
    return text


# --- canned slow-down / unclear-audio lines ------------------------------------------------

@lru_cache(maxsize=1)
def _canned_sentences() -> tuple[str, ...]:
    from server.prompts.agent_voice_rules import SLOW_DOWN_FALLBACK, UNCLEAR_FALLBACK

    result = []
    for table in (SLOW_DOWN_FALLBACK, UNCLEAR_FALLBACK):
        for line in table.values():
            result.extend(s for s in sentences(line) if len(_norm(s)) >= 6)
    return tuple(result)


def _similar(a: str, b: str) -> float:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb, autojunk=False).ratio()


def _canned(sentence: str) -> bool:
    return any(_similar(sentence, line) >= 0.85 for line in _canned_sentences())


def looks_garbled(text: str | None) -> bool:
    """An empty, symbol-only or broken STT final; a short acknowledgement is never garbled."""
    raw = (text or "").strip()
    if "�" in raw:
        return True
    words = tokens(raw)
    if not words:
        return True
    if is_acknowledgement(raw):
        return False
    if not any(ch.isalpha() for ch in raw):
        return True
    # STT noise arrives as runs of one-letter fragments.
    singles = sum(1 for w in words if len(w) == 1)
    return len(words) >= 3 and singles / len(words) >= 0.6


def audio_issue_evidence(caller: str, ctx: Any = None, *, server_requested: bool = False) -> bool:
    """Evidence that justifies asking the caller to slow down or repeat."""
    if is_acknowledgement(caller):
        return False
    if server_requested or looks_garbled(caller):
        return True
    confidence = getattr(ctx, "last_stt_confidence", None)
    if isinstance(confidence, (int, float)) and 0 <= confidence < 0.5:
        return True
    rate = getattr(ctx, "caller_words_per_second", None)
    return isinstance(rate, (int, float)) and rate > 4.0


def gate_canned_audio_lines(reply: str, *, caller: str, language: str, evidence: bool) -> str:
    """Remove slow-down / unclear-audio lines that nothing in the call justifies."""
    if evidence:
        return reply
    parts = sentences(reply)
    kept = [s for s in parts if not _canned(s)]
    if len(kept) == len(parts):
        return reply
    if kept and not all(is_acknowledgement(s) for s in kept):
        return _join(kept)
    if is_acknowledgement(caller):
        return _join(kept) or ack_line(language)
    from server.prompts.agent_voice_rules import normalize_compile_language
    from server.prompts.spoken_locale_style import SPOKEN_LOCALES

    try:
        return SPOKEN_LOCALES[normalize_compile_language(language)].clarification
    except (KeyError, ValueError):
        return SPOKEN_LOCALES["en-IN"].clarification


# --- business facts the agent was not given ------------------------------------------------

_SELF = {
    # First person plural: the speaker is talking about their own business.
    "we", "we're", "we’re", "we've", "our", "ours", "us",
    "మేము", "మేం", "మా", "మాది", "మాకు", "మన", "మనం", "మాదగ్గర",
    "हम", "हमारी", "हमारा", "हमारे", "हमें", "हमारी",
    "நாங்க", "நாங்கள்", "எங்க", "எங்கள்", "எங்களுக்கு", "எங்களோட", "எங்களிடம்",
    "ನಾವು", "ನಮ್ಮ", "ನಮಗೆ", "ನಮ್ಮದು",
    "ഞങ്ങൾ", "ഞങ്ങളുടെ", "ഞങ്ങൾക്ക്", "ഞങ്ങളുടേത്",
    "आम्ही", "आमची", "आमचा", "आमचे", "आमच्या", "आम्हाला", "आमचं",
    "আমরা", "আমাদের", "আমাদেরকে",
    "અમે", "અમારી", "અમારો", "અમારું", "અમારા", "અમને",
    "ਅਸੀਂ", "ਸਾਡੀ", "ਸਾਡਾ", "ਸਾਡੇ", "ਸਾਨੂੰ",
}
_NEGATION = _terms(
    ["not", "no", "don't", "don’t", "doesn't", "isn't", "aren't", "can't", "cannot", "won't", "unavailable",
     "unknown", "never"],
    ["లేదు", "లేవు", "తెలియదు", "కాదు", "లేరు"], ["नहीं", "नही", "पता नहीं", "उपलब्ध नहीं"],
    ["இல்லை", "இல்ல", "தெரியல", "தெரியாது"], ["ಇಲ್ಲ", "ಗೊತ್ತಿಲ್ಲ"], ["ഇല്ല", "അറിയില്ല", "അല്ല"],
    ["नाही"], ["নেই", "জানা নেই", "নয়"], ["નથી", "ખબર નથી"], ["ਨਹੀਂ", "ਨਹੀ"],
)
_BUSINESS_NOUN = _terms(
    ["business", "company", "firm", "shop", "store", "enterprise", "brand", "organisation", "organization",
     "agency", "outlet", "startup", "start-up"],
    ["బిజినెస్", "కంపెనీ", "సంస్థ", "షాప్", "దుకాణం", "వ్యాపారం"],
    ["बिज़नेस", "बिजनेस", "कंपनी", "दुकान", "व्यवसाय", "व्यापार", "संस्था", "फर्म"],
    ["பிசினஸ்", "கம்பெனி", "நிறுவனம்", "கடை", "வியாபாரம்"], ["ಬಿಸಿನೆಸ್", "ಕಂಪನಿ", "ಸಂಸ್ಥೆ", "ಅಂಗಡಿ", "ವ್ಯಾಪಾರ"],
    ["ബിസിനസ്", "കമ്പനി", "സ്ഥാപനം", "കട", "വ്യാപാരം"], ["बिझनेस", "कंपनी", "दुकान", "व्यवसाय", "संस्था"],
    ["ব্যবসা", "বিজনেস", "কোম্পানি", "দোকান", "প্রতিষ্ঠান", "সংস্থা"], ["બિઝનેસ", "કંપની", "દુકાન", "વ્યવસાય", "સંસ્થા", "પેઢી"],
    ["ਬਿਜ਼ਨਸ", "ਕੰਪਨੀ", "ਦੁਕਾਨ", "ਕਾਰੋਬਾਰ", "ਵਪਾਰ", "ਸੰਸਥਾ"],
)
_SIZE = _terms(
    ["small", "big", "large", "huge", "tiny", "roadside", "road side", "family", "family-run", "multinational",
     "mnc", "leading", "largest", "biggest", "reputed", "famous", "well-known", "well known"],
    ["చిన్న", "పెద్ద", "రోడ్ సైడ్", "రోడ్‌సైడ్", "రోడ్డు పక్క", "కుటుంబ"],
    ["छोटी", "छोटा", "छोटे", "बड़ी", "बड़ा", "बड़े", "बडी", "बडा", "रोड साइड", "पारिवारिक", "मशहूर"],
    ["சின்ன", "சிறிய", "பெரிய", "ரோடு சைடு"], ["ಚಿಕ್ಕ", "ಸಣ್ಣ", "ದೊಡ್ಡ"], ["ചെറിയ", "വലിയ"],
    ["लहान", "मोठी", "मोठा", "मोठे"], ["ছোট", "বড়", "বড়ো"], ["નાની", "નાનો", "નાનું", "મોટી", "મોટો", "મોટું"],
    ["ਛੋਟੀ", "ਛੋਟਾ", "ਵੱਡੀ", "ਵੱਡਾ"],
)
_KIND = _terms(
    ["manufacturer", "manufacturers", "wholesaler", "wholesalers", "retailer", "retailers", "distributor",
     "distributors", "dealer", "dealers", "reseller", "franchise", "startup", "start-up"],
    ["మాన్యుఫాక్చరర్", "హోల్‌సేల్", "హోల్ సేల్", "డిస్ట్రిబ్యూటర్", "డీలర్"],
    ["मैन्युफैक्चरर", "निर्माता", "थोक", "होलसेल", "डिस्ट्रीब्यूटर", "डीलर"],
    ["உற்பத்தியாளர்", "மொத்த", "டீலர்"], ["ತಯಾರಕ", "ಸಗಟು", "ಡೀಲರ್"], ["നിർമ്മാതാ", "മൊത്ത", "ഡീലർ"],
    ["उत्पादक", "घाऊक", "डीलर"], ["প্রস্তুতকারক", "পাইকারি", "ডিলার"], ["ઉત્પાદક", "જથ્થાબંધ", "ડીલર"],
    ["ਨਿਰਮਾਤਾ", "ਥੋਕ", "ਡੀਲਰ"],
)
# An office or shop noun is only a location claim with a locative ("is in", "లో ఉంది").
_LOCATED = _terms(["located", "based in", "based out of", "headquartered", "situated"],
                  ["లో ఉన్నాం", "లో ఉంది"], ["में स्थित", "स्थित है"], ["இல் அமைந்துள்ளது"], ["ನಲ್ಲಿದೆ"], ["സ്ഥിതി ചെയ്യുന്നു"],
                  ["मध्ये आहे"], ["অবস্থিত"], ["માં આવેલ"], ["ਵਿੱਚ ਸਥਿਤ"])
_LOCATIVE = _terms(
    ["is in", "is at", "is near", "are in", "are at", "are near"], ["లో ఉంది", "లో ఉన్నాం", "దగ్గర ఉంది"],
    ["में है", "में हैं", "पर है"], ["இல் இருக்கு", "ல இருக்கு", "இல் உள்ளது"], ["ನಲ್ಲಿ ಇದೆ", "ದಲ್ಲಿದೆ", "ಅಲ್ಲಿ ಇದೆ"],
    ["ലാണ്", "ഇൽ ആണ്"], ["मध्ये आहे", "ला आहे"], ["তে আছে", "য় আছে"], ["માં છે", "પર છે"], ["ਵਿੱਚ ਹੈ", "ਵਿਚ ਹੈ"],
)
_LOCATION = _terms(
    ["head office", "office", "showroom", "warehouse", "factory", "headquarters", "shop", "store"],
    ["ఆఫీస్", "ఆఫీసు", "కార్యాలయం", "షోరూమ్", "ఫ్యాక్టరీ"], ["ऑफिस", "ऑफ़िस", "दफ्तर", "कार्यालय", "शोरूम", "फैक्ट्री"],
    ["ஆபீஸ்", "அலுவலகம்", "ஷோரூம்"], ["ಆಫೀಸ್", "ಕಚೇರಿ", "ಶೋರೂಮ್"], ["ഓഫീസ്", "ഷോറൂം"],
    ["ऑफिस", "कार्यालय", "शोरूम"], ["অফিস", "শোরুম", "কার্যালয়"], ["ઓફિસ", "કાર્યાલય", "શોરૂમ"],
    ["ਦਫ਼ਤਰ", "ਦਫਤਰ", "ਆਫ਼ਿਸ", "ਸ਼ੋਰੂਮ"],
)
_YEARS = _terms(
    ["years", "year", "established", "founded", "since", "experience"],
    ["సంవత్సరాలు", "సంవత్సరాల", "సంవత్సరం", "ఏళ్లు", "ఏళ్ళు", "ఏళ్ల", "స్థాపించ"],
    ["साल", "सालों", "वर्ष", "वर्षों", "स्थापित"], ["வருட", "ஆண்டு"], ["ವರ್ಷ"], ["വർഷ"], ["वर्ष", "वर्षां"],
    ["বছর"], ["વર્ષ"], ["ਸਾਲ"],
)
_STAFF = _terms(
    ["employees", "employee", "staff", "workers", "people working", "team members"],
    ["ఉద్యోగులు", "ఎంప్లాయిస్", "ఎంప్లాయీస్", "స్టాఫ్", "సిబ్బంది", "వర్కర్స్"],
    ["कर्मचारी", "स्टाफ", "स्टाफ़", "एम्प्लॉई", "एम्प्लॉयी"], ["ஊழியர்", "பணியாளர்", "ஸ்டாஃப்", "ஸ்டாப்"],
    ["ಉದ್ಯೋಗಿ", "ಸಿಬ್ಬಂದಿ", "ನೌಕರ", "ಸ್ಟಾಫ್"], ["ജീവനക്കാർ", "ജോലിക്കാർ", "സ്റ്റാഫ്"], ["कर्मचारी", "स्टाफ"],
    ["কর্মী", "কর্মচারী", "স্টাফ"], ["કર્મચારી", "સ્ટાફ"], ["ਕਰਮਚਾਰੀ", "ਸਟਾਫ਼", "ਸਟਾਫ"],
)
_BRANCHES = _terms(
    ["branch", "branches", "outlets", "franchises"],
    ["బ్రాంచ్", "బ్రాంచీలు", "శాఖలు"], ["ब्रांच", "शाखा", "शाखाएं", "आउटलेट"], ["கிளை", "பிராஞ்ச்"],
    ["ಶಾಖೆ", "ಬ್ರಾಂಚ್"], ["ശാഖ", "ബ്രാഞ്ച്"], ["शाखा", "ब्रँच"], ["শাখা", "ব্রাঞ্চ"], ["શાખા", "બ્રાન્ચ"],
    ["ਸ਼ਾਖਾ", "ਬ੍ਰਾਂਚ"],
)
# "Our branch will call you" is not a claim; a count or a plural network is.
_BRANCH_NETWORK = _terms(["branches", "outlets", "franchises"], ["బ్రాంచీలు", "శాఖలు"], ["शाखाएं", "शाखाओं"],
                         ["கிளைகள்"], ["ಶಾಖೆಗಳು"], ["ശാഖകൾ"], ["शाखा आहेत"], ["শাখাগুলো"], ["શાખાઓ"], ["ਸ਼ਾਖਾਵਾਂ"])
_DISCOUNT = _terms(
    # "free" alone also means "available" ("when you're free"); only cost phrases count.
    ["discount", "discounts", "cashback", "cash back", "coupon", "promo", "promotion", "% off", "percent off",
     "free of cost", "free of charge", "free delivery", "free shipping", "for free", "complimentary",
     "waived", "waive", "special offer", "festival offer", "combo offer", "offer price"],
    ["డిస్కౌంట్", "తగ్గింపు", "రాయితీ", "ఆఫర్", "ఉచితం", "ఉచితంగా", "క్యాష్‌బ్యాక్"],
    ["डिस्काउंट", "छूट", "ऑफ़र", "ऑफर", "मुफ्त", "मुफ़्त", "कैशबैक"], ["தள்ளுபடி", "டிஸ்கவுண்ட்", "ஆஃபர்", "ஆபர்", "இலவச"],
    ["ರಿಯಾಯಿತಿ", "ಡಿಸ್ಕೌಂಟ್", "ಆಫರ್", "ಉಚಿತ"], ["ഡിസ്കൗണ്ട്", "ഇളവ്", "ഓഫർ", "സൗജന്യ"],
    ["सूट", "डिस्काउंट", "ऑफर", "मोफत"], ["ছাড়", "ডিসকাউন্ট", "অফার", "বিনামূল্যে"], ["ડિસ્કાઉન્ટ", "છૂટ", "ઓફર", "મફત"],
    ["ਛੋਟ", "ਡਿਸਕਾਊਂਟ", "ਆਫ਼ਰ", "ਆਫਰ", "ਮੁਫ਼ਤ", "ਮੁਫਤ"],
)
_GUARANTEE = _terms(
    ["guarantee", "guaranteed", "guarantees", "warranty", "money back", "money-back"],
    ["గ్యారంటీ", "గ్యారెంటీ", "హామీ", "వారంటీ"], ["गारंटी", "गारण्टी", "वारंटी"],
    ["உத்தரவாதம்", "கேரண்டி", "கியாரண்டி", "வாரண்டி"], ["ಖಾತರಿ", "ಗ್ಯಾರಂಟಿ", "ವಾರಂಟಿ"], ["ഗ്യാരന്റി", "വാറന്റി"],
    ["हमी", "गॅरंटी", "वॉरंटी"], ["গ্যারান্টি", "ওয়ারেন্টি"], ["ગેરંટી", "ગેરેન્ટી", "વોરંટી"], ["ਗਰੰਟੀ", "ਗਾਰੰਟੀ", "ਵਾਰੰਟੀ"],
)


def _claim_categories(sentence: str) -> set[str]:
    from server.call.memory_guard import has_number

    if "?" in sentence or _NEGATION.search(sentence):
        # A question or an "I don't know / not available" line is not a claim.
        return set()
    self_ref = any(t in _SELF for t in tokens(sentence))
    found = set()
    if self_ref and ((_SIZE.search(sentence) and _BUSINESS_NOUN.search(sentence)) or _KIND.search(sentence)):
        found.add("size_or_kind")
    if self_ref and (_LOCATED.search(sentence) or (_LOCATION.search(sentence) and _LOCATIVE.search(sentence))):
        found.add("location")
    if self_ref and _YEARS.search(sentence) and has_number(sentence):
        found.add("years_running")
    # "Our staff will call you" is not a claim about headcount; a count is.
    if self_ref and _STAFF.search(sentence) and has_number(sentence):
        found.add("staff")
    if self_ref and (_BRANCH_NETWORK.search(sentence) or (_BRANCHES.search(sentence) and has_number(sentence))):
        found.add("branches")
    if _DISCOUNT.search(sentence):
        found.add("discount_or_offer")
    if _GUARANTEE.search(sentence):
        found.add("guarantee")
    return found


def _supported(category: str, facts: str) -> bool:
    patterns = {
        "size_or_kind": (_SIZE, _KIND), "location": (_LOCATED, _LOCATION), "years_running": (_YEARS,),
        "staff": (_STAFF,), "branches": (_BRANCHES,), "discount_or_offer": (_DISCOUNT,),
        "guarantee": (_GUARANTEE,),
    }[category]
    return any(p.search(facts) for p in patterns)


_UNKNOWN_ANCHOR = re.compile(r"[‘'\"`]([^‘’'\"`\n]{2,160})[’'\"`]\s+for a missing fact", re.I)


def unknown_fact_line(brain: str | None, language: str) -> str:
    """The brain's own missing-fact line, else the platform default for the call language."""
    match = _UNKNOWN_ANCHOR.search(brain or "")
    if match:
        return match.group(1).strip()
    from server.prompts.agent_voice_rules import normalize_compile_language
    from server.prompts.spoken_locale_style import SPOKEN_LOCALES

    try:
        return SPOKEN_LOCALES[normalize_compile_language(language)].unknown
    except (KeyError, ValueError):
        return SPOKEN_LOCALES["en-IN"].unknown


def guard_business_claims(reply: str, *, brain: str | None, language: str) -> tuple[str, list[str]]:
    """Replace sentences that state business facts the compiled brain does not contain."""
    if not brain or not (reply or "").strip():
        return reply, []
    from server.call.business_answer_plan import business_fact_text

    facts = business_fact_text(brain)
    parts = sentences(reply)
    flagged: list[str] = []
    kept: list[str] = []
    unknown = unknown_fact_line(brain, language)
    inserted = _norm(unknown) in _norm(reply)
    for sentence in parts:
        unsupported = sorted(c for c in _claim_categories(sentence) if not _supported(c, facts))
        if not unsupported:
            kept.append(sentence)
            continue
        flagged.extend(unsupported)
        if not inserted:
            kept.append(unknown)
            inserted = True
    if not flagged:
        return reply, []
    return _join(kept) or unknown, flagged


# --- repetition and repeated asks ----------------------------------------------------------

REPEAT_ACK = {"te": "సరే.", "hi": "ठीक है।", "ta": "சரி.", "kn": "ಸರಿ.", "ml": "ശരി.", "gu": "સારું.",
              "mr": "ठीक आहे.", "bn": "ঠিক আছে।", "pa": "ਠੀਕ ਹੈ।", "en": "Sure."}
# The caller said yes to an ask but did not give the detail: invite it, don't re-read the question.
GO_AHEAD = {"te": "సరే, చెప్పండి.", "hi": "जी, बताइए।", "ta": "சரி, சொல்லுங்க.", "kn": "ಸರಿ, ಹೇಳಿ.",
            "ml": "ശരി, പറഞ്ഞോളൂ.", "mr": "ठीक आहे, सांगा.", "bn": "ঠিক আছে, বলুন।", "gu": "સારું, કહો.",
            "pa": "ਠੀਕ ਹੈ, ਦੱਸੋ।", "en": "Sure, go ahead."}
# After two unanswered asks the caller gets a way out instead of a third ask.
SHARE_LATER = {
    "te": "పర్వాలేదు, అది తర్వాత కూడా చెప్పొచ్చు.",
    "hi": "कोई बात नहीं, आप यह बाद में भी बता सकते हैं।",
    "ta": "பரவாயில்லை, அதை அப்புறம் கூட சொல்லலாம்.",
    "kn": "ಪರವಾಗಿಲ್ಲ, ಅದನ್ನು ಆಮೇಲೆ ಕೂಡ ಹೇಳಬಹುದು.",
    "ml": "കുഴപ്പമില്ല, അത് പിന്നീട് പറഞ്ഞാലും മതി.",
    "mr": "काही हरकत नाही, ते नंतरही सांगू शकता.",
    "bn": "কোনো সমস্যা নেই, ওটা পরেও বলতে পারেন।",
    "gu": "કોઈ વાંધો નહીં, એ પછી પણ કહી શકો છો.",
    "pa": "ਕੋਈ ਗੱਲ ਨਹੀਂ, ਤੁਸੀਂ ਇਹ ਬਾਅਦ ਵਿੱਚ ਵੀ ਦੱਸ ਸਕਦੇ ਹੋ।",
    "en": "No problem, you can share that later too.",
}


def ack_line(language: str) -> str:
    return REPEAT_ACK.get(_lang(language), REPEAT_ACK["en"])


_SLOT_TERMS = {
    "quantity": _terms(
        ["how many", "quantity", "number of"], ["ఎన్ని", "ఎంత మంది"], ["कितने", "कितनी"], ["எத்தனை"], ["ಎಷ್ಟು"],
        ["എത്ര"], ["किती"], ["কয়টা", "কটা", "কতগুলো", "কয়টি"], ["કેટલા", "કેટલી"], ["ਕਿੰਨੇ", "ਕਿੰਨੀਆਂ", "ਕਿੰਨੀ"],
    ),
    "address": _terms(
        ["address"], ["అడ్రస్", "అడ్రెస్", "చిరునామా"], ["पता", "एड्रेस", "ऐड्रेस"], ["முகவரி", "அட்ரஸ்"],
        ["ವಿಳಾಸ", "ಅಡ್ರೆಸ್"], ["വിലാസം", "അഡ്രസ്"], ["पत्ता", "ॲड्रेस"], ["ঠিকানা", "অ্যাড্রেস"], ["સરનામું", "એડ્રેસ"],
        ["ਪਤਾ", "ਐਡਰੈੱਸ"],
    ),
    "name": _terms(
        ["name"], ["పేరు"], ["नाम"], ["பெயர்", "பேர்"], ["ಹೆಸರು"], ["പേര്"], ["नाव"], ["নাম"], ["નામ"], ["ਨਾਮ", "ਨਾਂ"],
    ),
    "email": _terms(
        ["email", "e-mail", "mail id"], ["ఈమెయిల్", "మెయిల్"], ["ईमेल", "मेल"], ["மின்னஞ்சல்", "ஈமெயில்"], ["ಇಮೇಲ್"],
        ["ഇമെയിൽ"], ["ईमेल"], ["ইমেল", "ইমেইল"], ["ઈમેલ", "ઇમેઇલ"], ["ਈਮੇਲ"],
    ),
    "phone": _terms(
        ["phone number", "mobile number", "contact number", "whatsapp number"], ["ఫోన్ నంబర్", "మొబైల్ నంబర్", "ఫోన్ నెంబర్"],
        ["फ़ोन नंबर", "फोन नंबर", "मोबाइल नंबर"], ["போன் நம்பர்", "மொபைல் நம்பர்"], ["ಫೋನ್ ನಂಬರ್", "ಮೊಬೈಲ್ ನಂಬರ್"],
        ["ഫോൺ നമ്പർ", "മൊബൈൽ നമ്പർ"], ["फोन नंबर", "मोबाईल नंबर"], ["ফোন নম্বর", "মোবাইল নম্বর"], ["ફોન નંબર", "મોબાઇલ નંબર"],
        ["ਫ਼ੋਨ ਨੰਬਰ", "ਫੋਨ ਨੰਬਰ", "ਮੋਬਾਈਲ ਨੰਬਰ"],
    ),
}
_REQUEST = _terms(
    ["tell", "share", "give", "provide", "could you", "can you", "may i", "please", "what is", "what's", "let me know"],
    ["చెప్తారా", "చెప్పండి", "చెప్పగలరా", "ఇస్తారా", "ఇవ్వండి", "చెప్పు"],
    ["बताइए", "बताएं", "बताएँ", "बताएंगे", "बताएँगे", "बता दीजिए", "दीजिए", "बताओ", "क्या है"],
    ["சொல்லுங்க", "சொல்லுங்கள்", "சொல்றீங்களா", "சொல்லுவீங்களா", "கொடுங்க", "தருவீங்களா"],
    ["ಹೇಳಿ", "ಹೇಳ್ತೀರಾ", "ಹೇಳುತ್ತೀರಾ", "ಕೊಡಿ", "ಕೊಡ್ತೀರಾ"], ["പറയാമോ", "പറയൂ", "പറയുമോ", "തരാമോ", "തരൂ"],
    ["सांगा", "सांगाल", "द्या"], ["বলুন", "বলবেন", "দিন", "দেবেন"], ["કહો", "કહેશો", "આપો", "આપશો", "જણાવો"],
    ["ਦੱਸੋ", "ਦੱਸੋਗੇ", "ਦੱਸ ਦਿਓ", "ਦਿਓ"],
)
_REPEAT_REQUEST = _terms(
    ["repeat", "again", "once more", "say that again", "come again"],
    ["మళ్లీ", "మళ్ళీ", "ఇంకోసారి", "రిపీట్"], ["फिर से", "दोबारा", "दुबारा", "रिपीट"], ["மறுபடியும்", "திரும்ப"],
    ["ಮತ್ತೆ", "ಇನ್ನೊಮ್ಮೆ"], ["ഒന്നുകൂടി", "വീണ്ടും"], ["पुन्हा", "परत"], ["আবার"], ["ફરી", "ફરીથી"], ["ਦੁਬਾਰਾ", "ਫਿਰ ਤੋਂ"],
)


# A tag question confirms a value the agent already has ("మీ పేరు Saikiran గారు కదా").
_TAGS = {"right", "correct", "isn't", "కదా", "ना", "தானே", "இல்லையா", "ಅಲ್ವಾ", "ಅಲ್ಲವೇ", "അല്ലേ", "তো", "ને", "ਨਾ"}


def _confirms(clause: str, following: str = "") -> bool:
    words, after = tokens(clause), tokens(following)
    return bool(words and words[-1] in _TAGS) or bool(after and all(w in _TAGS | {"it", "na"} for w in after))


def asked_slots(reply: str) -> dict[str, list[int]]:
    """Slots a reply asks the caller for, by sentence index.

    A clause naming a slot is an ask when it, or the clause right after it, is a
    request ("कितने कार्ड चाहिए, बताइए?"), unless it is a tag-question confirmation.
    """
    found: dict[str, list[int]] = {}
    for index, sentence in enumerate(sentences(reply)):
        clauses = _CLAUSE.findall(sentence)
        requests = ["?" in c or bool(_REQUEST.search(c)) for c in clauses]
        for position, clause in enumerate(clauses):
            following = clauses[position + 1] if position + 1 < len(clauses) else ""
            if _confirms(clause, following):
                continue
            if not (requests[position] or (position + 1 < len(clauses) and requests[position + 1])):
                continue
            for slot, pattern in _SLOT_TERMS.items():
                if pattern.search(clause) and index not in found.setdefault(slot, []):
                    found[slot].append(index)
    return {slot: rows for slot, rows in found.items() if rows}


def _guard_lines(language: str) -> set[str]:
    lang = _lang(language)
    return {_norm(t.get(lang, t["en"])) for t in (GO_AHEAD, SHARE_LATER, REPEAT_ACK)}


def guard_repeated_asks(
    reply: str, *, caller: str, language: str, state: dict, known: dict[str, str] | None = None,
) -> tuple[str, list[str]]:
    """Second ask after a bare "yes" becomes an invitation; a third becomes "share it later".

    ``state`` is per call: ``asked`` counts consecutive asks per slot answered only
    by acknowledgements, ``deferred`` holds slots the caller may give later.
    ``known`` maps a slot to a value the caller already gave; asking for it again is
    dropped unless the sentence confirms that value ("500 cards, right?").
    """
    asked: dict[str, int] = state.setdefault("asked", {})
    deferred: list[str] = state.setdefault("deferred", [])
    caller_ack = is_acknowledgement(caller)
    if not caller_ack:
        asked.clear()
    lang = _lang(language)
    parts = sentences(reply)
    slots = asked_slots(reply)
    replace: dict[int, str | None] = {}
    reasons: list[str] = []
    for slot, rows in slots.items():
        value = _norm((known or {}).get(slot))
        if value:
            unconfirmed = [row for row in rows if value not in _norm(parts[row])]
            if unconfirmed:
                reasons.append(f"known_slot:{slot}")
                replace.update({row: None for row in unconfirmed})
            asked.pop(slot, None)
            continue
        prior = asked.get(slot, 0)
        if slot in deferred and caller_ack:
            line, reason = None, f"deferred_slot:{slot}"
        elif prior >= 2:
            line, reason = SHARE_LATER.get(lang, SHARE_LATER["en"]), f"offer_later:{slot}"
            deferred.append(slot)
            asked.pop(slot, None)
        elif prior == 1:
            line, reason = GO_AHEAD.get(lang, GO_AHEAD["en"]), f"repeat_ask:{slot}"
            asked[slot] = 2
        else:
            asked[slot] = 1
            continue
        reasons.append(reason)
        if line is None or line == SHARE_LATER.get(lang, SHARE_LATER["en"]):
            # "You haven't told me how many" is the same ask in other words.
            rows = sorted({*rows, *(i for i, part in enumerate(parts) if _SLOT_TERMS[slot].search(part))})
        for position, row in enumerate(rows):
            if row not in replace or replace[row] is None:
                replace[row] = line if position == 0 else replace.get(row)
    for slot in [s for s in asked if s not in slots]:
        asked.pop(slot, None)
    if not replace:
        return reply, []
    kept: list[str] = []
    for index, sentence in enumerate(parts):
        if index in replace:
            if replace[index] and replace[index] not in kept:
                kept.append(replace[index])
            continue
        kept.append(sentence)
    if any(line in kept for line in (GO_AHEAD.get(lang), SHARE_LATER.get(lang))):
        # "సరే. సరే, చెప్పండి." — the invitation already acknowledges.
        kept = [s for s in kept if not is_acknowledgement(s)] or kept
    return _join(kept) or ack_line(language), reasons


def drop_near_repeats(reply: str, *, caller: str, previous: list[str], language: str, keep: tuple[str, ...] = ()) -> str:
    """Drop sentences nearly identical to the agent's last two replies.

    ``keep`` lines (the missing-fact line) stay when the caller raised something
    new: the same "I don't know" can be the honest answer to a different question.
    """
    from server.call.end_call_validate import looks_like_question

    if not previous or _REPEAT_REQUEST.search(caller or "") or looks_like_question(caller or "") or "?" in (caller or ""):
        # The caller asked again or asked for a repeat: the same answer is the right answer.
        return reply
    said = [s for p in previous for s in sentences(p.replace("[interrupted]", ""))]
    own = _guard_lines(language)
    if not is_acknowledgement(caller):
        own |= {_norm(line) for line in keep if _norm(line)}
    parts = sentences(reply)
    kept = [
        s for s in parts
        if len(_norm(s)) < 8 or _norm(s) in own or not any(_similar(s, old) >= 0.85 for old in said)
    ]
    if len(kept) == len(parts):
        return reply
    return _join(kept) or ack_line(language)


# --- the caller's words since the agent's last turn ---------------------------------------

def join_caller_fragments(parts: list[str]) -> str:
    """Merge overlapping STT finals into one utterance.

    Finals arrive cumulative ("A", "A B") or overlapping ("A B C", "B C, D"); a
    contained fragment is dropped and an overlap is joined once.
    """
    merged = ""
    for part in parts:
        cleaned = " ".join((part or "").split())
        if not _norm(cleaned):
            continue
        if not merged:
            merged = cleaned
            continue
        a, b = _norm(merged), _norm(cleaned)
        if b in a:
            continue
        if a in b:
            merged = cleaned
            continue
        old, new = merged.split(), cleaned.split()
        overlap = 0
        for size in range(min(len(old), len(new)), 0, -1):
            if [_norm(w) for w in old[-size:]] == [_norm(w) for w in new[:size]]:
                overlap = size
                break
        merged = " ".join(old + new[overlap:])
    return merged


def caller_turn_since_agent(history: list[dict], transcript: str, *, max_fragments: int = 6) -> str:
    """Everything the caller said after the agent's last reply, current final included."""
    fragments: list[str] = []
    for message in reversed(history or []):
        if message.get("role") != "user":
            break
        fragments.append(str(message.get("content") or ""))
    fragments = list(reversed(fragments))[-max_fragments:]
    return join_caller_fragments([*fragments, transcript])[-1600:] or (transcript or "")


def recent_agent_replies(history: list[dict], count: int = 2) -> list[str]:
    replies = [str(m.get("content") or "").replace("[interrupted]", "").strip()
               for m in history or [] if m.get("role") == "assistant"]
    return [r for r in replies if r][-count:]


def guard_reply(
    reply: str,
    *,
    caller: str,
    language: str,
    brain: str | None = None,
    history: list[dict] | None = None,
    state: dict | None = None,
    audio_evidence: bool = False,
    known: dict[str, str] | None = None,
) -> tuple[str, list[str]]:
    """Run every guard in order; return the reply to speak and why it changed."""
    text = (reply or "").strip()
    if not text:
        return reply, []
    reasons: list[str] = []
    text, claims = guard_business_claims(text, brain=brain, language=language)
    reasons.extend(f"business_claim:{c}" for c in claims)
    gated = gate_canned_audio_lines(text, caller=caller, language=language, evidence=audio_evidence)
    if gated != text:
        reasons.append("canned_audio_line")
        text = gated
    stripped = strip_filler_echo(text, caller)
    if stripped != text:
        reasons.append("filler_echo")
        text = stripped
    text, ask_reasons = guard_repeated_asks(text, caller=caller, language=language,
                                            state=state if state is not None else {}, known=known)
    reasons.extend(ask_reasons)
    deduped = drop_near_repeats(text, caller=caller, previous=recent_agent_replies(history or []), language=language,
                                keep=(unknown_fact_line(brain, language),))
    if deduped != text:
        reasons.append("near_repeat")
        text = deduped
    return text, reasons


def known_slots(facts: dict | None, caller: str, *, quantity_asked: bool = False) -> dict[str, str]:
    """Slot values the agent must not ask for again on this turn.

    A value the caller gives in this very turn always counts. A remembered value
    counts only when the caller just acknowledged: a caller who is changing the
    order may need the question asked again.
    """
    from server.call.caller_detail_capture import (
        extract_caller_email,
        extract_caller_name,
        extract_explicit_name,
        extract_requested_quantity,
    )
    from server.call.memory_guard import slot_value_error

    known: dict[str, str] = {}
    if is_acknowledgement(caller):
        for key, value in (facts or {}).items():
            key, value = str(key), str(value or "")
            if not value or slot_value_error(key, value):
                continue
            if re.search(r"(?:^|_)(?:quantity|qty|count)(?:$|_)", key):
                known.setdefault("quantity", value)
            elif re.fullmatch(r"(?:caller_|customer_)?name", key):
                known.setdefault("name", value)
            elif "address" in key:
                known.setdefault("address", value)
            elif re.fullmatch(r"(?:caller_)?email", key):
                known.setdefault("email", value)
    quantity = extract_requested_quantity(caller, quantity_asked=quantity_asked)
    name = extract_explicit_name(caller) or extract_caller_name(caller)
    email = extract_caller_email(caller)
    for slot, value in (("quantity", quantity), ("name", name), ("email", email)):
        if value:
            known[slot] = value
    return known
