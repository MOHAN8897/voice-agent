"""Session call-end policy — UI overlay + brain section + hangup reason allow-list."""
from __future__ import annotations

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
    "the farewell playback finishes, without a post-farewell silence wait."
)


def default_call_end_policy(language: str | None = None) -> dict[str, Any]:
    lang = normalize_compile_language(language)
    return {
        # Out-of-scope cannot be proven from one turn. It remains available as
        # an explicit policy overlay, but is unsafe as a default hangup reason.
        "allowedReasons": list(DEFAULT_HANGUP_REASONS),
        "farewell": pack_get(CALL_END_FAREWELLS, lang),
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
    if farewell and farewell not in CALL_END_FAREWELLS.values():
        base["farewell"] = farewell
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
    if contact_preference == "callback":
        from server.call.hangup_judge import callback_farewell_for

        return callback_farewell_for(language)
    normalized = normalize_call_end_policy(policy, language=language)
    farewell = str(normalized.get("farewell") or "").strip()
    if farewell:
        return farewell
    from server.call.hangup_judge import default_farewell_for

    return default_farewell_for(language)


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
        f"On an approved close the platform speaks this farewell: `{farewell}`. "
        "There is one farewell owner: never speak a goodbye or this line yourself. "
        "On a close turn the platform speaks, so leave spoken_response empty."
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
