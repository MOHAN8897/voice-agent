"""PSTN turn-taking lexicons; regional pools require native-speaker field review."""
from __future__ import annotations

import re

STRONG_HALT_MAP: dict[str, list[str]] = {
    "en": ["stop", "wait", "hold on", "one second", "pause", "shut up", "quiet", "cancel", "listen", "enough"],
    "te": ["ఆగండి", "ఆగు", "ఆపండి", "వినండి", "చాలు", "aagandi", "aagu", "aapandi", "vinandi", "chaalu"],
    "hi": ["रुको", "रुकिए", "बंद करो", "चुप", "मत बोलो", "सुनो", "सुनिए", "बस", "ruko", "rukiye", "band karo", "chup", "suno", "bas"],
    "ta": ["நில்லுங்கள்", "நில்லு", "பொறுங்கள்", "பொறு", "கேளுங்கள்", "போதும்", "nillungal", "porungal", "podhum"],
    "kn": ["ನಿಲ್ಲಿಸಿ", "ನಿಲ್ಲು", "ತಾಳಿ", "ಇರಿ", "ಕೇಳಿ", "ಸಾಕು", "nillisi", "thali", "saaku"],
    "ml": ["നിൽക്കൂ", "നിൽക്ക്", "കാക്കൂ", "കാക്ക്", "കേൾക്കൂ", "മതി", "nilkkoo", "kaakkoo", "mathi"],
    "mr": ["थांबा", "थांब", "ऐका", "ऐक", "चूप", "पुरे", "thamba", "thamb", "aika", "pure"],
    "bn": ["থামুন", "থামো", "দাঁড়ান", "দাঁড়াও", "শুনুন", "থাক", "চুপ", "thamun", "daran", "thak"],
    "gu": ["ઊભા રહો", "થોભો", "સાંભળો", "શાંત રહો", "ubha raho", "thobho", "sambhalo"],
    "pa": ["ਰੁਕੋ", "ਖਲੋਵੋ", "ਸੁਣੋ", "ਚੁੱਪ", "ruko", "khalovo", "suno", "chup"],
}

WEAK_NEGATION_MAP: dict[str, list[str]] = {
    "en": ["no", "nope", "wrong", "actually", "sorry"],
    "te": ["వద్దు", "వద్దండి", "కాదు", "లేదు", "లేదండి", "అది కాదు", "vaddu", "vaddandi", "kaadu", "ledu", "ledandi", "adi kaadu"],
    "hi": ["नहीं", "रहने दो", "गलत", "nahin", "nahi", "rehne do", "galat"],
    "ta": ["வேண்டாம்", "வேண்டாங்க", "இல்லை", "இல்ல", "இல்லீங்க", "அது இல்லை", "தவறு", "vendaam", "illai", "thavaru"],
    "kn": ["ಬೇಡ", "ಬೇಡಿ", "ಇಲ್ಲ", "ಇಲ್ಲರೀ", "ಅದಲ್ಲ", "ತಪ್ಪು", "beda", "bedi", "illa", "adalla", "thappu"],
    "ml": ["വേണ്ട", "വേണ്ടതില്ല", "അല്ല", "ഇല്ല", "തെറ്റാണ്", "venda", "alla", "illa", "thettanu"],
    "mr": ["नको", "नकोस", "नाही", "ते नाही", "चूक", "nako", "nakos", "nahi", "chook"],
    # Bare Roman "na" is ambiguous in code-switched calls. Keep native negations.
    "bn": ["না", "ভুল", "bhul"],
    "gu": ["ના", "નહીં", "નથી", "ખોટું", "રહેવા દો", "nahin", "nathi", "khotu"],
    "pa": ["ਨਾ", "ਨਹੀਂ", "ਰਹਿਣ ਦਿਓ", "ਗ਼ਲਤ", "nahin", "rehn do", "galat"],
}

BACKCHANNEL_NOD_MAP: dict[str, list[str]] = {
    "en": ["yes", "yeah", "yep", "yup", "ok", "okay", "sure", "hmm", "mm", "mhm", "uh huh", "right", "correct", "got it", "i see", "alright", "all right", "no problem", "no worries", "actually that's fine"],
    "te": ["అవును", "అవునండి", "అవునండీ", "సరే", "సరేనండి", "అలాగే", "అలాగేనండి", "బాగుంది", "avunu", "avunandi", "sare", "sarenandi", "alage", "bagundi"],
    "hi": ["हाँ", "हां", "हाँजी", "हाँ जी", "जी", "जी हाँ", "जी हां", "ठीक", "ठीक है", "अच्छा", "अच्छा जी", "haan", "haanji", "ha", "han", "theek", "theek hai", "achha", "theek na", "hai na", "theek hai na", "ठीक है ना"],
    "ta": ["ஆம்", "ஆமாம்", "ஆமாங்க", "ஆமா", "சரி", "சரிங்க", "aam", "aamaam", "aamanga", "sari", "saringa"],
    "kn": ["ಹೌದು", "ಹೌದೌದು", "ಹೌದುರೀ", "ಸರಿ", "ಸರೀ", "ಆಯಿತು", "ಆಯ್ತು", "ಚೆನ್ನಾಗಿದೆ", "haudu", "sari", "aayithu", "chennagide"],
    "ml": ["അതെ", "അതെ അതെ", "ശരി", "ശരിയാണ്", "ശരിയായി", "കൊള്ളാം", "athe", "shari", "kollam"],
    "mr": ["हो", "होय", "हो ना", "बरे", "बरं", "ठीक", "ठीक आहे", "छान", "समजले", "ho", "bare", "theek"],
    "bn": ["হ্যাঁ", "হাঁ", "হ্যাঁ হ্যাঁ", "ঠিক", "ঠিক আছে", "বেশ", "বুঝেছি", "haan", "theek", "besh", "bujhechi"],
    "gu": ["હા", "હાજી", "હા હા", "બરાબર", "બરાબર છે", "સારું", "ઠીક", "સમજાયું", "haa", "haaji", "barabar", "saaru"],
    "pa": ["ਹਾਂ", "ਹਾਂਜੀ", "ਹਾਂ ਹਾਂ", "ਠੀਕ", "ਠੀਕ ਹੈ", "ਚੰਗਾ", "ਸਮਝ ਗਿਆ", "haan", "theek", "changa", "samajh gaya"],
}

QUESTION_MARKER_MAP: dict[str, list[str]] = {
    "en": ["shall i", "do you want", "would you like", "is that ok", "can we", "can you", "could you", "please confirm"],
    "te": ["చెప్పండి", "చెప్తారా", "కావాలా", "సరేనా", "అవునా", "వెళ్దామా"],
    "hi": ["बताइए", "चाहिए", "ठीक है ना", "करूं", "पुष्टि करें", "आगे बढ़ें"],
    "ta": ["சொல்லுங்க", "வேண்டுமா", "சரியா", "தொடரலாமா", "உறுதிப்படுத்தவா"],
    "kn": ["ಹೇಳಿ", "ಬೇಕಾ", "ಸರಿನಾ", "ಮುಂದುವರಿಯಲೇ", "ದೃಢೀಕರಿಸಿ"],
    "ml": ["പറയൂ", "വേണമോ", "ശരിയാണോ", "തുടരണമോ", "ഉറപ്പാക്കണോ"],
    "mr": ["सांगा", "हवे का", "बरोबर का", "पुढे जाऊ का", "खात्री करा"],
    "bn": ["বলুন", "চাই কি", "ঠিক আছে তো", "এগিয়ে যাব কি", "নিশ্চিত করবেন"],
    "gu": ["કહો", "જોઈએ છે", "બરાબર ને", "આગળ વધું", "પુષ્ટિ કરો"],
    "pa": ["ਦੱਸੋ", "ਚਾਹੀਦਾ", "ਠੀਕ ਹੈ ਨਾ", "ਅੱਗੇ ਵਧਾਂ", "ਪੁਸ਼ਟੀ ਕਰੋ"],
}


def _lexicon_core(pools: dict[str, list[str]]) -> str:
    words = {word.strip() for pool in pools.values() for word in pool if word.strip()}
    return "|".join(re.escape(word) for word in sorted(words, key=lambda word: (-len(word), word)))


def compile_lexicon_regex(
    pools: dict[str, list[str]], allow_tail: bool = False,
) -> re.Pattern[str]:
    core = _lexicon_core(pools)
    tail = r"(?:\s+\S+){0,2}" if allow_tail else ""
    return re.compile(rf"^(?:{core}){tail}[.!?,।\s]*$", re.IGNORECASE)


_STRONG_HALT_RE = compile_lexicon_regex(STRONG_HALT_MAP, allow_tail=True)
_WEAK_NEGATION_RE = compile_lexicon_regex(WEAK_NEGATION_MAP)
_BACKCHANNEL_NODS_RE = compile_lexicon_regex(BACKCHANNEL_NOD_MAP)
_NOD_TOKEN_RE = re.compile(
    rf"(?:{_lexicon_core(BACKCHANNEL_NOD_MAP)})(?=$|[.!?,।\s])[.!?,।\s]*", re.IGNORECASE,
)
_SHORT_QUESTION_RE = compile_lexicon_regex({
    "te": ["ఎంత", "ఎందుకు", "ఎప్పుడు"], "hi": ["कितना", "कब"],
    "ta": ["அப்படியா"], "kn": ["ಹೌದಾ"],
})
_TURN_CLAIM_RE = compile_lexicon_regex({
    "en": ["tell me", "go ahead", "speak"], "te": ["చెప్పండి", "చెప్పు", "cheppandi", "cheppu"],
    "hi": ["बोलिए", "बताइए", "boliye", "bataiye"], "ta": ["சொல்லுங்க", "பேசுங்க"],
    "kn": ["ಹೇಳಿ", "ಮಾತನಾಡಿ"], "ml": ["പറയൂ", "സംസാരിക്കൂ"],
    "mr": ["सांगा", "बोला"], "bn": ["বলুন", "কথা বলুন"],
    "gu": ["કહો", "બોલો"], "pa": ["ਦੱਸੋ", "ਬੋਲੋ"],
})


def is_backchannel(text: str) -> bool:
    """Consume repeated nods without nested-regex backtracking on STT input."""
    cleaned = text.strip()
    position = 0
    while position < len(cleaned):
        match = _NOD_TOKEN_RE.match(cleaned, position)
        if match is None:
            return False
        position = match.end()
    return bool(cleaned)


def is_single_word_claim(text: str) -> bool:
    cleaned = text.strip()
    return bool(
        not is_backchannel(cleaned)
        and (len(cleaned.split()) == 1 and len(cleaned) >= 6 and any(char.isalpha() for char in cleaned)
             or _SHORT_QUESTION_RE.fullmatch(cleaned) or _TURN_CLAIM_RE.fullmatch(cleaned))
    )


def agent_asked_question(text: str, *, expects_answer: bool | None = None) -> bool:
    if expects_answer is not None:
        return expects_answer
    sentences = re.findall(r"[^.?!|।\n]+[.?!|।\n]*", text.strip().rstrip('"\'”’ '))
    if not sentences:
        return False
    last = sentences[-1].strip().lower()
    return last.endswith("?") or any(
        re.search(rf"(?<!\w){re.escape(marker)}(?!\w)", last)
        for markers in QUESTION_MARKER_MAP.values() for marker in markers
    )
