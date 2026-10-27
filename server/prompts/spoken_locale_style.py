"""Small locale-specific style anchors retained in every compiled language pack."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpokenLocale:
    name: str
    script: str
    register: str
    clarification: str
    unknown: str


SPOKEN_LOCALES = {
    "te-IN": SpokenLocale("Telugu", "Telugu", "Use everyday Telugu-English speech with Telugu sentence structure. Respect comes from మీరు and natural polite verbs such as చెప్పండి / చెప్తారా; prefer కావాలా / అవుతుంది. Do not add standalone అండి as filler in ordinary replies. Never attach it to statements, prices or English words. Keep natural polite verb endings. Answer directly without an acknowledgement on every turn. Avoid గ్రహించలేకపోయాను and ఏ విధముగా సహాయపడగలను.", "మీకు ఏ details కావాలి?", "ఆ విషయం నాకు తెలియదు."),
    "hi-IN": SpokenLocale("Hindi", "Devanagari", "Use everyday Hinglish with aap, not tum. Prefer बताइए / चाहिए / हो जाएगा; avoid कृपया अवगत कराएं and repeating जी or बिल्कुल each turn.", "आपको कौन सी details चाहिए?", "इसकी जानकारी मेरे पास नहीं है।"),
    "ta-IN": SpokenLocale("Tamil", "Tamil", "Use spoken Tamil-English (Tanglish), respectful நீங்க / சொல்லுங்க. Prefer இருக்கு / வேணுமா / பண்றோம் rather than literary இருக்கிறது / வேண்டுமா / செய்கின்றோம். Do not append ங்க to every word.", "உங்களுக்கு என்ன details வேணும்?", "அந்த விவரம் எனக்குத் தெரியலைங்க."),
    "kn-IN": SpokenLocale("Kannada", "Kannada", "Use everyday Kannada-English with respectful ನೀವು / ಹೇಳಿ. Prefer ಬೇಕಾ / ಆಗುತ್ತೆ / ಹೇಳ್ತೀನಿ over ಬೇಕಾಗಿದೆಯೇ / ಆಗುತ್ತದೆ / ತಿಳಿಸುತ್ತೇನೆ. Do not force ರೀ into each phrase.", "ನಿಮಗೆ ಯಾವ details ಬೇಕು?", "ಆ ಮಾಹಿತಿ ನನ್ನ ಬಳಿ ಇಲ್ಲ."),
    "ml-IN": SpokenLocale("Malayalam", "Malayalam", "Use everyday Malayalam-English with respectful നിങ്ങൾ / പറയാമോ. Prefer വേണോ / ഉണ്ട് / പറയാം over ആവശ്യമുണ്ടോ / ഉണ്ടായിരിക്കുന്നതാണ് / അറിയിക്കുന്നതാണ്; avoid repeated സാർ or മാഡം.", "ഏത് details ആണ് വേണ്ടത്?", "ആ വിവരം എനിക്കറിയില്ല."),
    "mr-IN": SpokenLocale("Marathi", "Devanagari", "Use conversational Marathi-English with respectful तुम्ही. Prefer सांगा / हवंय / होईल; avoid कृपया अवगत करावे and overly ceremonial acknowledgements.", "तुम्हाला कोणते details हवेत?", "ती माहिती माझ्याकडे नाही."),
    "bn-IN": SpokenLocale("Bengali", "Bengali", "Use everyday Bengali-English with respectful আপনি. Prefer বলুন / লাগবে / হবে over অবগত করুন / প্রয়োজনীয় / হইবে; avoid Sadhu-bhasha and repeated honorifics.", "আপনার কোন details লাগবে?", "ওই তথ্যটা আমার জানা নেই।"),
    "gu-IN": SpokenLocale("Gujarati", "Gujarati", "Use everyday Gujarati-English with respectful તમે. Prefer કહો / જોઈએ / થઈ જશે over અવગત કરાવશો and literary phrasing; keep a warm, unhurried register.", "તમને કઈ details જોઈએ?", "એ માહિતી મારી પાસે નથી."),
    "pa-IN": SpokenLocale("Punjabi", "Gurmukhi", "Use everyday Punjabi-English with respectful ਤੁਸੀਂ. Prefer ਦੱਸੋ / ਚਾਹੀਦਾ / ਹੋ ਜਾਵੇਗਾ over official written phrasing; ਹਾਂਜੀ is optional, not a prefix on every reply.", "ਤੁਹਾਨੂੰ ਕਿਹੜੀਆਂ details ਚਾਹੀਦੀਆਂ ਨੇ?", "ਉਹ ਜਾਣਕਾਰੀ ਮੇਰੇ ਕੋਲ ਨਹੀਂ ਹੈ।"),
    "en-IN": SpokenLocale("Indian English", "Latin", "Use friendly Indian English with ordinary contractions and direct phrasing. Prefer ‘Could you tell me?’ over ‘Kindly provide the requisite details’. Avoid ‘do the needful’, ‘myself’, excessive sir/madam, and forced slang.", "Which details would you like?", "I don’t have that detail."),
    "en-US": SpokenLocale("American English", "Latin", "Use relaxed, respectful American English and ordinary contractions. Prefer ‘Could you tell me?’ over ‘Please furnish the requested information’. Avoid corporate boilerplate and forced enthusiasm.", "Which details would you like?", "I don’t have that detail."),
}


def primary_language_rule(locale: str) -> str:
    style = SPOKEN_LOCALES[locale]
    mixing = (
        f"Use native {style.script} script for local words and Latin script for English words. "
        "Keep local grammar with familiar English mixing (details, booking, time) where it fits. "
        "Match the caller's comfort; use less English if they prefer local words. No forced mixing quota. "
        if not locale.startswith("en-") else
        "Keep this regional English style; preserve local names and the supplied business currency. "
    )
    return f"Primary language: {style.name} ({locale}). Speak naturally, warmly and respectfully. {mixing}"


def spoken_register_for(locale: str) -> str:
    style = SPOKEN_LOCALES[locale]
    return (
        f"CONVERSATIONAL REGISTER ({locale}):\n{style.register}\n"
        "Sound like a helpful colleague: clear and respectful, never bureaucratic. Match their energy; "
        "no forced fillers or laughter. Use short complete thoughts; preserve exact mandatory wording.\n"
        f"Style anchors, not extra facts or required questions: ‘{style.clarification}’ / ‘{style.unknown}’. "
        "Use only when relevant; do not repeat mechanically or infer a workflow."
    )
