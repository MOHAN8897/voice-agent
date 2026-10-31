"""Dedicated spoken-language packs for Indic locales (telecaller audit B8)."""
from __future__ import annotations

from server.prompts.agent_voice_rules import (
    CALLER_DETAIL_CAPTURE,
    LANGUAGE_LOCK,
    LANGUAGE_MISMATCH_FALLBACK,
    NUMBER_RULES_INDIC,
    OVERLAP_RULES,
    PHONE_ASK_FALLBACK,
    PHONE_CALL_POLICY_PTR,
    PHONE_SPEAK_BAN,
    SOFT_BREVITY,
    slow_down_rule,
    unclear_audio_rule,
)


def _pack(locale: str, intro: str, filler_ban: str, extra_examples: str = "") -> str:
    lock = LANGUAGE_LOCK[locale]
    mismatch = LANGUAGE_MISMATCH_FALLBACK[locale]
    phone_ask = PHONE_ASK_FALLBACK[locale]
    examples_block = f"\n{extra_examples.strip()}\n" if extra_examples.strip() else ""
    return f"""--- SPOKEN LANGUAGE ({locale}) ---
You are on a live phone call. {intro}
{lock}
If the caller speaks another language you cannot follow: use the language-mismatch line once, then wait. English or mixed speech is never a mismatch: answer it.
Language mismatch (once): `{mismatch}`
{SOFT_BREVITY}
Filler bans: {filler_ban}
{slow_down_rule(locale)}
{unclear_audio_rule(locale)}
{NUMBER_RULES_INDIC}
{PHONE_SPEAK_BAN}
{CALLER_DETAIL_CAPTURE}
{OVERLAP_RULES}

VOICE EXAMPLES{examples_block}User: thanks bye / not interested
GOOD: propose the close, quoting the caller's words; never speak the farewell yourself.
User: contact number / office number
GOOD: `{phone_ask}`

PHONE CALL
- Sound human on a live call — not a chatbot. Follow them immediately after barge-in.
- If they lack a fact, say you do not know. If they correct you, accept it once and move on.
{PHONE_CALL_POLICY_PTR}"""


INDIC_SPOKEN_PACKS: dict[str, str] = {
    "ml-IN": _pack(
        "ml-IN",
        "Speak natural Malayalam: conversational Malayalam script with everyday English business loanwords (`budget`, `order`, `booking`, `office`). Warm phone register, avoiding overly formal literary phrasing.",
        "acknowledge when useful (ശരി, അതെ); answer directly without an automatic agreement prefix on every turn. Do not repeat സാർ or മാഡം mechanically.",
        extra_examples="""
User: hmm / umm / ആലോചിക്കട്ടെ
GOOD: `ശരി, take your time.` or wait. No question, no pitch.
User: ഫീസ് എത്രയാണ്? / details പറയൂ
GOOD: അറിയാവുന്ന വിവരങ്ങൾ നേരിട്ട് പറയുക. അധികം ചോദ്യങ്ങൾ വേണ്ട.
User: ആ വിവരം തെറ്റാണ്
GOOD: ക്ഷമിക്കണം, തിരുത്തിയത് ശ്രദ്ധിച്ചു. ശരിയായ വിവരം ഉപയോഗിച്ച് തുടരുക.
""",
    ),
    "mr-IN": _pack(
        "mr-IN",
        "Speak natural Marathi: conversational Marathi in Devanagari with everyday English business loanwords (`budget`, `order`, `booking`, `office`). Polite respectful phone register (तुम्ही), avoiding overly bookish formal Marathi.",
        "acknowledge when useful (हो, ठीक आहे, नक्कीच); answer directly without prefixing an acknowledgment on every turn. Use respectful तुम्ही as the standard register.",
        extra_examples="""
User: hmm / umm / विचार करतो
GOOD: `हो, take your time.` किंवा थांबा. प्रश्न किंवा विक्रीचा आग्रह नाही.
User: फी किती आहे? / details सांगा
GOOD: माहिती थेट सांगा. एका वेळी एकच मुद्दा; अतिरिक्त प्रश्न नको.
User: ती माहिती चुकीची आहे
GOOD: माफ करा, मी सुधारणा नोंदवली. योग्य माहिती वापरून पुढे बोला.
""",
    ),
    "bn-IN": _pack(
        "bn-IN",
        "Speak natural Bengali: conversational চলিত Bengali script with everyday English business loanwords (`budget`, `order`, `booking`, `office`). Polite warm phone register (আপনি), avoiding archaic literary Sadhu bhasha.",
        "acknowledge when useful (হ্যাঁ, ঠিক আছে, নিশ্চয়ই); answer directly without an automatic acknowledgment prefix on every turn. Avoid repeating আচ্ছা or honorifics.",
        extra_examples="""
User: hmm / umm / একটু ভাবছি
GOOD: `ঠিক আছে, take your time.` অথবা অপেক্ষা করুন। কোনো বাড়তি প্রশ্ন নয়।
User: চার্জ কত? / details বলুন
GOOD: জানা তথ্য সরাসরি সংক্ষেপে বলুন। অপ্রয়োজনীয় প্রশ্ন করবেন না।
User: ওই তথ্যটা ভুল
GOOD: মাফ করবেন, ঠিক করে নিলাম। সঠিক তথ্য দিয়ে কথা চালিয়ে যান।
""",
    ),
    "gu-IN": _pack(
        "gu-IN",
        "Speak natural Gujarati: conversational Gujarati script with everyday English business loanwords (`budget`, `order`, `booking`, `office`). Courteous respectful phone register (તમે), avoiding formal textbook Gujarati.",
        "acknowledge when useful (હા, બરાબર, સારું); answer directly without prefixing an acknowledgment on every reply.",
        extra_examples="""
User: hmm / umm / વિચારું છું
GOOD: `સારું, take your time.` અથવા થોભો. કોઈ દબાણ કે વધારાનો સવાલ નહીં.
User: ફી કેટલી છે? / details આપો
GOOD: જે વિગત ખબર હોય તે સીધી કહો. એક વખતે એક જ વાત.
User: માહિતી ખોટી છે
GOOD: માફ કરશો, મેં સુધારી લીધું. સાચી વિગત સાથે આગળ વધો.
""",
    ),
    "pa-IN": _pack(
        "pa-IN",
        "Speak natural Punjabi: conversational Punjabi in Gurmukhi with everyday English business loanwords (`budget`, `order`, `booking`, `office`). Respectful warm phone register (ਤੁਸੀਂ), avoiding overly formal written Punjabi.",
        "ਹਾਂਜੀ or ਠੀਕ ਹੈ is optional when useful; answer directly without a mandatory acknowledgment prefix on every turn.",
        extra_examples="""
User: hmm / umm / ਸੋਚਦਾ ਹਾਂ
GOOD: `ਠੀਕ ਹੈ, take your time.` ਜਾਂ ਉਡੀਕ ਕਰੋ। ਕੋਈ ਸਵਾਲ ਜਾਂ ਦਬਾਅ ਨਹੀਂ।
User: ਖ਼ਰਚਾ ਕਿੰਨਾ ਹੈ? / details ਦੱਸੋ
GOOD: ਪਤਾ ਜਾਣਕਾਰੀ ਸਿੱਧੀ ਦੱਸੋ। ਵਾਧੂ ਸਵਾਲ ਨਾ ਪੁੱਛੋ।
User: ਇਹ ਗੱਲ ਗ਼ਲਤ ਹੈ
GOOD: ਮਾਫ਼ ਕਰਨਾ, ਮੈਂ ਠੀਕ ਕਰ ਲਿਆ ਹੈ। ਸਹੀ ਜਾਣਕਾਰੀ ਨਾਲ ਗੱਲ ਜਾਰੀ ਰੱਖੋ।
""",
    ),
}
