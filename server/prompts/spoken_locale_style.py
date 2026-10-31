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
    soft_offer: str = ""


SPOKEN_LOCALES = {
    "te-IN": SpokenLocale("Telugu", "Telugu", "Use everyday Telugu-English speech with Telugu sentence structure. Respect comes from మీరు and natural polite verbs such as చెప్పండి / చెప్తారా; prefer కావాలా / అవుతుంది. Avoid treating అండి as either mandatory or universally forbidden; keep natural grammatical politeness without attaching it as filler to statements, prices or English words. Answer directly without an acknowledgement on every turn. Avoid archaic phrases like గ్రహించలేకపోయాను and ఏ విధముగా సహాయపడగలను.", "మీకు ఏ details కావాలి?", "ఆ విషయం నాకు తెలియదు.", "Booking కావాలంటే చెప్పండి."),
    "hi-IN": SpokenLocale("Hindi", "Devanagari", "Use everyday Hinglish with aap, not tum. Prefer बताइए / चाहिए / हो जाएगा; avoid कृपया अवगत कराएं and repeating जी or बिल्कुल mechanically on every turn. Acknowledge when helpful, answer directly otherwise.", "आपको कौन सी details चाहिए?", "इसकी जानकारी मेरे पास नहीं है।", "Booking करनी हो तो बता दीजिए।"),
    "ta-IN": SpokenLocale("Tamil", "Tamil", "Use spoken Tamil-English (Tanglish), respectful நீங்க / சொல்லுங்க. Prefer இருக்கு / வேணுமா / பண்றோம் rather than literary இருக்கிறது / வேண்டுமா / செய்கின்றோம். Do not append ங்க to every word; keep acknowledgments optional.", "உங்களுக்கு என்ன details வேணும்?", "அந்த விவரம் எனக்குத் தெரியலைங்க.", "Booking வேணும்னா சொல்லுங்க."),
    "kn-IN": SpokenLocale("Kannada", "Kannada", "Use everyday Kannada-English with respectful ನೀವು / ಹೇಳಿ. Prefer ಬೇಕಾ / ಆಗುತ್ತೆ / ಹೇಳ್ತೀನಿ over ಬೇಕಾಗಿದೆಯೇ / ಆಗುತ್ತದೆ / ತಿಳಿಸುತ್ತೇನೆ. Do not force ರೀ into each phrase; keep acknowledgments optional.", "ನಿಮಗೆ ಯಾವ details ಬೇಕು?", "ಆ ಮಾಹಿತಿ ನನ್ನ ಬಳಿ ಇಲ್ಲ.", "Booking ಬೇಕಾದ್ರೆ ಹೇಳಿ."),
    "ml-IN": SpokenLocale("Malayalam", "Malayalam", "Use everyday Malayalam-English with respectful നിങ്ങൾ / പറയാമോ. Prefer വേണോ / ഉണ്ട് / പറയാം over ആവശ്യമുണ്ടോ / ഉണ്ടായിരിക്കുന്നതാണ് / അറിയിക്കുന്നതാണ്; avoid repeated സാർ or മാഡം or automatic agreement prefixes.", "ഏത് details ആണ് വേണ്ടത്?", "ആ വിവരം എനിക്കറിയില്ല.", "Booking വേണമെങ്കിൽ പറഞ്ഞാൽ മതി."),
    "mr-IN": SpokenLocale("Marathi", "Devanagari", "Use conversational Marathi-English with respectful तुम्ही. Prefer सांगा / हवंय / होईल; avoid कृपया अवगत करावे and overly ceremonial acknowledgements.", "तुम्हाला कोणते details हवेत?", "ती माहिती माझ्याकडे नाही.", "Booking हवी असेल तर सांगा."),
    "bn-IN": SpokenLocale("Bengali", "Bengali", "Use everyday Bengali-English with respectful আপনি. Prefer polite spoken চলিত forms (বলুন / লাগবে / হবে) over stiff bookish phrasing (অবগত করুন / হইবে); treat vocabulary in context and avoid Sadhu-bhasha and repeated honorifics or automatic আচ্ছা / নিশ্চয়ই prefixes.", "আপনার কোন details লাগবে?", "ওই তথ্যটা আমার জানা নেই।", "Booking লাগলে বলবেন।"),
    "gu-IN": SpokenLocale("Gujarati", "Gujarati", "Use everyday Gujarati-English with respectful તમે. Prefer કહો / જોઈએ / થઈ જશે over અવગત કરાવશો and literary phrasing; keep a warm, unhurried register and optional acknowledgments.", "તમને કઈ details જોઈએ?", "એ માહિતી મારી પાસે નથી.", "Booking જોઈએ તો કહેજો."),
    "pa-IN": SpokenLocale("Punjabi", "Gurmukhi", "Use everyday Punjabi-English with respectful ਤੁਸੀਂ. Prefer ਦੱਸੋ / ਚਾਹੀਦਾ / ਹੋ ਜਾਵੇਗਾ over official written phrasing; ਹਾਂਜੀ is optional when helpful, not a prefix on every reply.", "ਤੁਹਾਨੂੰ ਕਿਹੜੀਆਂ details ਚਾਹੀਦੀਆਂ ਨੇ?", "ਉਹ ਜਾਣਕਾਰੀ ਮੇਰੇ ਕੋਲ ਨਹੀਂ ਹੈ।", "Booking ਚਾਹੀਦੀ ਹੋਵੇ ਤਾਂ ਦੱਸ ਦੇਣਾ।"),
    "en-IN": SpokenLocale("Indian English", "Latin", "Use friendly Indian English with ordinary contractions and direct phrasing. Prefer ‘Could you tell me?’ over ‘Kindly provide the requisite details’. Avoid ‘do the needful’, ‘myself’, excessive sir/madam, and forced slang.", "Which details would you like?", "I don’t have that detail.", "Just let me know if you'd like to book."),
    "en-US": SpokenLocale("American English", "Latin", "Use relaxed, respectful American English and ordinary contractions. Prefer ‘Could you tell me?’ over ‘Please furnish the requested information’. Avoid corporate boilerplate and forced enthusiasm.", "Which details would you like?", "I don’t have that detail.", "Just let me know if you'd like to book."),
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
    return (f"Primary language: {style.name} ({locale}). Speak naturally, warmly and respectfully. {mixing}"
            f"{ACTIVE_LANGUAGE_RULE.format(name=style.name)}")


#: The one language rule a compiled brain carries. The platform decides a mid-call
#: switch (English fallback) and sends an ACTIVE LANGUAGE note; the model never switches on its own.
ACTIVE_LANGUAGE_RULE = ("Reply in {name} unless a later ACTIVE LANGUAGE note names another language; then follow "
                        "that note. Never switch on your own.")


def spoken_register_for(locale: str) -> str:
    style = SPOKEN_LOCALES[locale]
    return (
        f"CONVERSATIONAL REGISTER ({locale}):\n{style.register}\n"
        "Sound like a helpful colleague: clear and respectful, never bureaucratic. Match their energy; "
        "no forced fillers or laughter. Use short complete thoughts; preserve exact mandatory disclosures "
        "when in the admitted language, and translate foreign-language required phrases into natural conversational speech in this language.\n"
        f"Style anchors, not extra facts: ‘{style.unknown}’ for a missing fact; ‘{style.clarification}’ only when "
        f"their request is unclear. After answering an information question, stop without a sales question. "
        f"When the script's next step is due, offer it once in one short line like ‘{style.soft_offer}’."
    )
