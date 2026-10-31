"""Session call-end policy — UI overlay + brain section + hangup reason allow-list."""
from __future__ import annotations

import json
import re
from typing import Any

from server.prompts.agent_voice_rules import (
    CALL_END_FAREWELLS,
    normalize_compile_language,
    pack_get,
)

HANGUP_REASONS = (
    "goodbye",
    "firm_refusal",
    "not_interested",
    "goal_complete",
    "abuse",
    "out_of_scope",
)
DEFAULT_HANGUP_REASONS = ("goodbye", "firm_refusal", "not_interested", "goal_complete", "abuse")

CLOSING_TOOL_DESCRIPTION = (
    "Propose that the platform end the call. Never speak a farewell yourself: the platform "
    "speaks the approved farewell after it accepts this decision. "
    "Use firm_refusal for an explicit stop-contact request, not_interested for a clear refusal "
    "that is not an opt-out, goodbye for an explicit end request, and goal_complete when the "
    "configured required outcome and applicable agreed next step are complete. A callback, visit "
    "or handoff is required only when that workflow applies and is permitted; never invent one to "
    "close an information or support call. "
    "Never call for bare okay/thanks, unclear speech, an unanswered question or busy without an end request. "
    "Before disconnect is committed, a meaningful new request may reopen the conversation. "
    "After an accepted close, stop generating turns; the platform disconnects immediately when "
    "the farewell playback and brief caller-resumption window finish."
)


def default_call_end_policy(language: str | None = None) -> dict[str, Any]:
    lang = normalize_compile_language(language)
    return {
        # Out-of-scope cannot be proven from one turn. It remains available as
        # an explicit policy overlay, but is unsafe as a default hangup reason.
        "allowedReasons": list(DEFAULT_HANGUP_REASONS),
        "farewell": pack_get(CALL_END_FAREWELLS, lang),
        "farewellSource": "default",
    }


def normalize_call_end_policy(raw: Any, *, language: str | None = None) -> dict[str, Any]:
    lang = normalize_compile_language(language)
    base = default_call_end_policy(lang)
    if not isinstance(raw, dict):
        return base
    reasons_raw = raw.get("allowedReasons") or raw.get("allowed_reasons")
    if isinstance(reasons_raw, list) and reasons_raw:
        reasons = [str(r).strip().lower() for r in reasons_raw if str(r).strip().lower() in HANGUP_REASONS]
        if reasons:
            base["allowedReasons"] = reasons
    farewell = str(raw.get("farewell") or "").strip()[:240]
    if farewell and (raw.get("farewellSource") == "tenant" or farewell not in CALL_END_FAREWELLS.values()):
        base["farewell"] = farewell
        base["farewellSource"] = "tenant"
    return base


def allowed_reasons_for(policy: dict[str, Any] | None) -> frozenset[str]:
    if not policy:
        return frozenset(DEFAULT_HANGUP_REASONS)
    raw = policy.get("allowedReasons") or policy.get("allowed_reasons") or []
    reasons = [str(r).strip().lower() for r in raw if str(r).strip().lower() in HANGUP_REASONS]
    return frozenset(reasons or DEFAULT_HANGUP_REASONS)


def server_farewell_for(
    language: str | None,
    *,
    policy: dict[str, Any] | None = None,
    contact_preference: str | None = None,
) -> str:
    """The only farewell spoken on a close. Tenant policy wins, then the language pack."""
    normalized = normalize_call_end_policy(policy, language=language)
    farewell = str(normalized.get("farewell") or "").strip()
    if not farewell:
        from server.call.hangup_judge import default_farewell_for

        farewell = default_farewell_for(language)
    if contact_preference == "callback":
        acknowledgement = callback_acknowledgement_for(language)
        return f"{acknowledgement} {farewell}"
    if contact_preference == "do_not_call":
        # An opt-out is confirmed out loud, so the caller knows it was heard.
        return f"{do_not_call_acknowledgement_for(language)} {farewell}"
    return farewell


def callback_acknowledgement_for(language: str | None) -> str:
    """Spoken after the callback request is saved. Everyday phone speech, not a form letter."""
    lang = normalize_compile_language(language)
    return {
        "te-IN": "సరే, మీ callback note చేసుకున్నాను.",
        "hi-IN": "ठीक है, आपका callback note कर लिया है।",
        "ta-IN": "சரி, உங்க callback-ஐ note பண்ணிட்டேன்.",
        "kn-IN": "ಸರಿ, ನಿಮ್ಮ callback note ಮಾಡ್ಕೊಂಡಿದೀನಿ.",
        "ml-IN": "ശരി, നിങ്ങളുടെ callback note ചെയ്തിട്ടുണ്ട്.",
        "gu-IN": "સારું, તમારો callback note કરી લીધો છે.",
        "mr-IN": "ठीक आहे, तुमचा callback note करून घेतला आहे.",
        "bn-IN": "ঠিক আছে, আপনার callback note করে নিয়েছি।",
        "pa-IN": "ਠੀਕ ਹੈ, ਤੁਹਾਡਾ callback note ਕਰ ਲਿਆ ਹੈ।",
    }.get(lang, "Okay, I've noted your callback.")


def callback_time_question_for(language: str | None) -> str:
    """Asked once when a caller wants a callback but gave no day or time."""
    lang = normalize_compile_language(language)
    return {
        "te-IN": "మీకు ఏ time కి call చేయమంటారు?",
        "hi-IN": "आपको किस समय call करना ठीक रहेगा?",
        "ta-IN": "உங்களுக்கு எந்த நேரத்தில் call பண்ணலாம்?",
        "kn-IN": "ನಿಮಗೆ ಯಾವ ಸಮಯಕ್ಕೆ ಕಾಲ್ ಮಾಡಲಿ?",
        "ml-IN": "ഏത് സമയത്ത് വിളിക്കണം?",
        "gu-IN": "તમને કયા સમયે કૉલ કરીએ?",
        "mr-IN": "तुम्हाला कोणत्या वेळी कॉल करू?",
        "bn-IN": "আপনাকে কখন কল করব?",
        "pa-IN": "ਤੁਹਾਨੂੰ ਕਿਸ ਵੇਲੇ ਕਾਲ ਕਰੀਏ?",
    }.get(lang, "When would be a good time to call you back?")


def do_not_call_acknowledgement_for(language: str | None) -> str:
    """Spoken confirmation that the caller's opt-out was recorded."""
    return {
        "te-IN": "సరే, ఈ నంబర్‌కి మళ్లీ కాల్ చేయము.",
        "hi-IN": "ठीक है, इस नंबर पर अब दोबारा कॉल नहीं करेंगे।",
        "ta-IN": "சரி, இந்த எண்ணுக்கு இனி அழைக்க மாட்டோம்.",
        "kn-IN": "ಸರಿ, ಈ ನಂಬರ್‌ಗೆ ಮತ್ತೆ ಕಾಲ್ ಮಾಡಲ್ಲ.",
        "ml-IN": "ശരി, ഈ നമ്പറിലേക്ക് ഇനി വിളിക്കില്ല.",
        "gu-IN": "ઠીક છે, આ નંબર પર હવે ફરી કૉલ નહીં કરીએ.",
        "mr-IN": "ठीक आहे, या नंबरवर पुन्हा कॉल करणार नाही.",
        "bn-IN": "ঠিক আছে, এই নম্বরে আর কল করব না।",
        "pa-IN": "ਠੀਕ ਹੈ, ਇਸ ਨੰਬਰ 'ਤੇ ਦੁਬਾਰਾ ਕਾਲ ਨਹੀਂ ਕਰਾਂਗੇ।",
    }.get(normalize_compile_language(language), "Understood, we won't call this number again.")


def callback_save_failed_for(language: str | None) -> str:
    return {
        "te-IN": "క్షమించండి, మీ callback save కాలేదు. దయచేసి మమ్మల్ని నేరుగా contact చేయండి.",
        "hi-IN": "माफ़ कीजिए, आपका callback save नहीं हो पाया। प्लीज़ हमसे सीधे contact कीजिए।",
        "ta-IN": "மன்னிக்கணும், உங்க callback save ஆகல. தயவுசெய்து எங்களை நேரடியா contact பண்ணுங்க.",
        "kn-IN": "ಕ್ಷಮಿಸಿ, ನಿಮ್ಮ callback save ಆಗ್ಲಿಲ್ಲ. ದಯವಿಟ್ಟು ನಮ್ಮನ್ನ ನೇರವಾಗಿ contact ಮಾಡಿ.",
        "ml-IN": "ക്ഷമിക്കണം, നിങ്ങളുടെ callback save ആയില്ല. ദയവായി ഞങ്ങളെ നേരിട്ട് contact ചെയ്യൂ.",
        "gu-IN": "માફ કરજો, તમારો callback save ન થયો. પ્લીઝ અમારો સીધો contact કરજો.",
        "mr-IN": "माफ करा, तुमचा callback save झाला नाही. प्लीज आम्हाला थेट contact करा.",
        "bn-IN": "দুঃখিত, আপনার callback save হয়নি। প্লিজ আমাদের সাথে সরাসরি contact করুন।",
        "pa-IN": "ਮਾਫ਼ ਕਰਨਾ, ਤੁਹਾਡਾ callback save ਨਹੀਂ ਹੋਇਆ। ਕਿਰਪਾ ਕਰਕੇ ਸਾਡੇ ਨਾਲ ਸਿੱਧਾ contact ਕਰੋ।",
    }.get(normalize_compile_language(language), "Sorry, I couldn't save your callback. Please contact us directly.")


def callback_time_reply_for(language: str | None) -> str:
    """A busy or call-me-later turn with no time: a short acknowledgement, then one question."""
    lang = normalize_compile_language(language)
    acknowledgement = {
        "te-IN": "సరే, పర్లేదు.",
        "hi-IN": "ठीक है, कोई बात नहीं।",
        "ta-IN": "சரி, பரவாயில்ல.",
        "kn-IN": "ಸರಿ, ಪರವಾಗಿಲ್ಲ.",
        "ml-IN": "ശരി, കുഴപ്പമില്ല.",
        "gu-IN": "ઠીક છે, વાંધો નહીં.",
        "mr-IN": "ठीक आहे, हरकत नाही.",
        "bn-IN": "ঠিক আছে, কোনো সমস্যা নেই।",
        "pa-IN": "ਠੀਕ ਹੈ, ਕੋਈ ਗੱਲ ਨਹੀਂ।",
    }.get(lang, "Sure, no problem.")
    return f"{acknowledgement} {callback_time_question_for(lang)}"


def handoff_acknowledgement_for(language: str | None) -> str:
    """Spoken once a request for a person from the business is saved. Never "I can't connect you"."""
    return {
        "te-IN": "సరే, ఈ విషయం మా manager లేదా team కి చెప్తాను.",
        "hi-IN": "ठीक है, आपकी बात हम अपने manager या team तक पहुँचा देंगे।",
        "ta-IN": "சரி, இந்த விஷயத்தை எங்க manager அல்லது team-கிட்ட சொல்றேன்.",
        "kn-IN": "ಸರಿ, ಈ ವಿಷಯವನ್ನ ನಮ್ಮ manager ಅಥವಾ team ಗೆ ತಿಳಿಸ್ತೀನಿ.",
        "ml-IN": "ശരി, ഈ കാര്യം ഞങ്ങളുടെ manager-നെയോ team-നെയോ അറിയിക്കാം.",
        "gu-IN": "સારું, આ વાત અમારા manager કે team સુધી પહોંચાડી દઈશ.",
        "mr-IN": "ठीक आहे, ही गोष्ट आम्ही आमच्या manager किंवा team पर्यंत पोहोचवू.",
        "bn-IN": "ঠিক আছে, এটা আমাদের manager বা team কে জানিয়ে দেব।",
        "pa-IN": "ਠੀਕ ਹੈ, ਇਹ ਗੱਲ ਅਸੀਂ ਆਪਣੇ manager ਜਾਂ team ਤੱਕ ਪਹੁੰਚਾ ਦਿਆਂਗੇ।",
    }.get(normalize_compile_language(language), "Okay, I'll pass this to my manager or team.")


CALL_END_CONFIG_TITLE = "saas_call_end_policy"


def policy_from_sections(sections: list[dict[str, Any]], language: str) -> dict[str, Any] | None:
    section = next((s for s in sections if s.get("title") == CALL_END_CONFIG_TITLE), None)
    if section is None:
        return None
    try:
        raw = json.loads(section.get("raw_text") or "{}")
    except (ValueError, TypeError) as exc:
        raise ValueError("The farewell configuration is invalid.") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("farewell", ""), str):
        raise ValueError("The farewell must be text.")  # noqa: TRY004 -- validation boundary uses ValueError.
    if len(raw.get("farewell", "").strip()) > 240:
        raise ValueError("The farewell must be 240 characters or fewer.")
    raw["farewellSource"] = "tenant" if raw.get("farewell", "").strip() else "default"
    return normalize_call_end_policy(raw, language=language)


def policy_from_brain(brain: str | None, language: str | None) -> dict[str, Any] | None:
    text = str(brain or "")
    block = re.search(r"(?ms)^--- CALL END POLICY ---\n(.*?)(?=^--- [A-Z][^\n]* ---|\Z)", text)
    if block:
        text = block.group(1)
    match = re.search(r"(?m)^Farewell text \(JSON\):\s*(.+)$", text)
    farewell = None
    if match:
        try:
            farewell = json.loads(match.group(1))
        except ValueError:
            return None
    if farewell is None:
        legacy = re.findall(r"(?:Farewell example|platform speaks this farewell):\s*`([^`]+)`", text)
        farewell = legacy[-1] if legacy else None
    if not isinstance(farewell, str):
        return None
    reasons = re.search(r"Allowed (?:hangup|close) reasons for this agent:\s*([^\n.]+)", text)
    return normalize_call_end_policy({
        "farewell": farewell,
        "farewellSource": "tenant" if re.search(r"(?m)^Farewell source: tenant$", text) else "default",
        "allowedReasons": reasons.group(1).split(",") if reasons else list(DEFAULT_HANGUP_REASONS),
    }, language=language)


def apply_call_end_policy(brain: str, language: str, policy: dict[str, Any] | None) -> str:
    if policy is None:
        return brain
    section = format_call_end_section(language, policy)
    pattern = r"(?ms)^--- CALL END POLICY ---\n.*?(?=^--- [A-Z][^\n]* ---|\Z)"
    if re.search(pattern, brain):
        return re.sub(pattern, lambda _: section + "\n\n", brain, count=1)
    return brain.rstrip() + "\n\n" + section


def format_call_end_section(language: str | None, policy: dict[str, Any] | None = None) -> str:
    from server.call.hangup_judge import HANGUP_JUDGMENT_RULES

    lang = normalize_compile_language(language)
    normalized = normalize_call_end_policy(policy, language=lang)
    reasons = ", ".join(normalized["allowedReasons"])
    farewell = normalized["farewell"]
    return (
        "--- CALL END POLICY ---\n"
        f"{HANGUP_JUDGMENT_RULES}\n"
        f"Allowed close reasons for this agent: {reasons}. "
        "On an approved close the platform speaks the configured farewell below. "
        "There is one farewell owner: never speak a goodbye or this line yourself. "
        "For JSON sessions proposing a close, leave spoken_response empty. "
        "For speech-text sessions, a brief acknowledgement is allowed; never write a farewell. "
        "The platform can save a caller-requested callback for the business even without external integrations. "
        "Gather any required details and requested timing before proposing that close. "
        "The platform confirms saving only after persistence succeeds; never promise an automatically scheduled call.\n"
        f"Farewell text (JSON): {json.dumps(farewell, ensure_ascii=False)}\n"
        f"Farewell source: {normalized['farewellSource']}"
    )


_CANONICAL_CLOSING: dict[str, str] = {
    "en": (
        "Make the close decision only when the caller is finished, clearly refuses all help, "
        "or asks to end. Never speak a goodbye or farewell; the platform speaks it. "
        "Keep the conversation open while the caller still has a question, interest for later, "
        "or asks you not to disconnect."
    ),
    "te": (
        "కాలర్ పని పూర్తయినప్పుడు, సహాయం పూర్తిగా తిరస్కరించినప్పుడు లేదా కాల్ ముగించమని "
        "స్పష్టంగా అడిగినప్పుడు మాత్రమే close decision ఇవ్వండి. మీరు goodbye లేదా farewell "
        "చెప్పకండి; platform చెబుతుంది. కాలర్‌కు ఇంకా ప్రశ్న ఉంటే, భవిష్యత్తులో ఆసక్తి ఉంటే, "
        "లేదా కాల్ కట్ చేయవద్దని అడిగితే సంభాషణ కొనసాగించండి."
    ),
    "hi": (
        "क्लोज़ का फैसला तभी करें जब कॉलर का काम पूरा हो, उसने सारी मदद साफ़ तौर पर मना कर दी हो, "
        "या कॉल खत्म करने को कहा हो। आप खुद goodbye या farewell न कहें; platform कहता है। "
        "जब तक कॉलर का सवाल बाकी है, भविष्य की दिलचस्पी है, या कॉल काटने से मना किया है, "
        "बातचीत जारी रखें।"
    ),
    "ta": (
        "அழைப்பாளரின் வேலை முடிந்தால், எல்லா உதவியையும் தெளிவாக மறுத்தால், அல்லது "
        "அழைப்பை முடிக்கச் சொன்னால் மட்டுமே close decision எடுங்கள். நீங்கள் goodbye அல்லது "
        "farewell சொல்ல வேண்டாம்; platform சொல்லும். அழைப்பாளருக்கு இன்னும் கேள்வி இருந்தால், "
        "எதிர்கால ஆர்வம் இருந்தால், அல்லது call cut செய்ய வேண்டாம் என்றால் உரையாடலைத் தொடருங்கள்."
    ),
    "kn": (
        "ಕರೆ ಮಾಡಿದವರ ಕೆಲಸ ಮುಗಿದಾಗ, ಎಲ್ಲ ಸಹಾಯವನ್ನೂ ಸ್ಪಷ್ಟವಾಗಿ ನಿರಾಕರಿಸಿದಾಗ, ಅಥವಾ ಕರೆ "
        "ಮುಗಿಸಲು ಕೇಳಿದಾಗ ಮಾತ್ರ close decision ತೆಗೆದುಕೊಳ್ಳಿ. ನೀವು goodbye ಅಥವಾ farewell "
        "ಹೇಳಬೇಡಿ; platform ಹೇಳುತ್ತದೆ. ಕರೆ ಮಾಡಿದವರಿಗೆ ಇನ್ನೂ ಪ್ರಶ್ನೆ ಇದ್ದರೆ, ಭವಿಷ್ಯದ ಆಸಕ್ತಿ "
        "ಇದ್ದರೆ, ಅಥವಾ call cut ಮಾಡಬೇಡಿ ಎಂದರೆ ಸಂಭಾಷಣೆ ಮುಂದುವರಿಸಿ."
    ),
}


def closing_policy_section(language: str | None) -> str:
    """The one closing instruction compiled into every agent script."""
    lang = normalize_compile_language(language)
    return _CANONICAL_CLOSING.get(lang.split("-")[0], _CANONICAL_CLOSING["en"])
