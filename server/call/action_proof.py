"""Typed proofs for actions a turn may claim.

A reply may say an enquiry was saved, an appointment was requested or
confirmed, or an order was confirmed only when a tool result from this turn
proved that exact action. The proof type is carried into the validated speech
phase and checked again before any text is spoken (2026-10-25 audit F06).
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterable

PROOF_ENQUIRY_SAVED = "enquiry_saved"
PROOF_APPOINTMENT_REQUESTED = "appointment_requested"
PROOF_APPOINTMENT_CONFIRMED = "appointment_confirmed"
PROOF_ORDER_CONFIRMED = "order_confirmed"

ACTION_CLAIMS: tuple[str, ...] = (
    PROOF_ENQUIRY_SAVED,
    PROOF_APPOINTMENT_REQUESTED,
    PROOF_APPOINTMENT_CONFIRMED,
    PROOF_ORDER_CONFIRMED,
)
_RECORDED_REQUEST = frozenset({PROOF_ENQUIRY_SAVED, PROOF_APPOINTMENT_REQUESTED})

# Statuses that prove the external action happened. ``cancelled`` is
# deliberately absent: a cancelled booking is not a confirmed one.
_SUCCESS_STATUSES = frozenset(
    {
        "ok",
        "success",
        "succeeded",
        "confirmed",
        "created",
        "booked",
        "sent",
        "draft_created",
        "rescheduled",
        "subscribed",
        "accepted",
    }
)
_PENDING_STATUSES = frozenset({"requested", "pending", "tentative", "queued"})

_ENQUIRY_SUFFIXES = (
    "_CREATE_ENQUIRY",
    "_CREATE_LEAD",
    "_CREATE_CONTACT",
    "_CREATE_DEAL",
    "_CREATE_PERSON",
    "_CREATE_RECORD",
    "_CREATE_CONVERSATION",
    "_CREATE_NOTE",
)
_APPOINTMENT_SUFFIXES = (
    "_CREATE_EVENT",
    "_CREATE_BOOKING",
    "_CREATE_INVITEE",
    "_CREATE_MEETING",
    "_CREATE_APPOINTMENT",
    "_RESCHEDULE_EVENT",
    "_RESCHEDULE_BOOKING",
    "_RESCHEDULE_APPOINTMENT",
)
_REQUEST_SUFFIXES = (
    "_CREATE_TASK",
    "_CREATE_TICKET",
    "_CREATE_ISSUE",
    "_CREATE_CARD",
    "_CREATE_ITEM",
)

_UNCONFIRMED_LINES: dict[str, str] = {
    "en": "I couldn't confirm that your request went through. Please don't treat it as done.",
    "te": "మీ అభ్యర్థన నిర్ధారణ అయిందో లేదో నాకు తెలియదు. దయచేసి దాన్ని పూర్తయినట్టు భావించకండి.",
    "hi": "मैं पुष्टि नहीं कर पाया कि आपका अनुरोध पूरा हुआ। कृपया इसे हो गया न मानें।",
    "mr": "तुमची विनंती पूर्ण झाली का हे मला निश्चित करता आले नाही. कृपया ती झाली असे मानू नका.",
    "ta": "உங்கள் கோரிக்கை முடிந்ததா என்று என்னால் உறுதிப்படுத்த முடியவில்லை. தயவுசெய்து அதை முடிந்ததாகக் கருத வேண்டாம்.",
    "kn": "ನಿಮ್ಮ ವಿನಂತಿ ಪೂರ್ಣಗೊಂಡಿದೆಯೇ ಎಂದು ನನಗೆ ದೃಢೀಕರಿಸಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಅದನ್ನು ಮುಗಿದಿದೆ ಎಂದು ಪರಿಗಣಿಸಬೇಡಿ.",
    "ml": "നിങ്ങളുടെ അഭ്യർത്ഥന പൂർത്തിയായോ എന്ന് എനിക്ക് സ്ഥിരീകരിക്കാനായില്ല. ദയവായി അത് പൂർത്തിയായതായി കരുതരുത്.",
    "bn": "আপনার অনুরোধ সম্পন্ন হয়েছে কিনা আমি নিশ্চিত করতে পারিনি। অনুগ্রহ করে এটি সম্পন্ন হয়েছে মনে করবেন না।",
    "gu": "તમારી વિનંતી પૂર્ણ થઈ કે નહીં તે હું ખાતરી કરી શક્યો નથી. કૃપા કરી તેને થઈ ગયું ન ગણો.",
    "pa": "ਮੈਂ ਪੁਸ਼ਟੀ ਨਹੀਂ ਕਰ ਸਕਿਆ ਕਿ ਤੁਹਾਡੀ ਬੇਨਤੀ ਪੂਰੀ ਹੋਈ ਹੈ। ਕਿਰਪਾ ਕਰਕੇ ਇਸਨੂੰ ਹੋਇਆ ਨਾ ਮੰਨੋ।",
}


def action_unconfirmed_line_for(language: str | None) -> str:
    from server.prompts.agent_voice_rules import normalize_compile_language

    lang = normalize_compile_language(language)
    return _UNCONFIRMED_LINES.get(lang.split("-")[0], _UNCONFIRMED_LINES["en"])


def _status(result: Any) -> str:
    if not isinstance(result, dict):
        return ""
    return str(result.get("status") or "").strip().lower()


def _result_text(result: Any) -> str:
    try:
        return json.dumps(result, ensure_ascii=False, default=str).lower()
    except (TypeError, ValueError):
        return ""


def proof_for_tool_result(tool_name: str, result: Any) -> str | None:
    """The typed action a successful tool result proves, or None.

    Unknown, error and unclassified results prove nothing, so a reply that
    claims one of these actions is replaced before it is spoken.
    """
    name = str(tool_name or "").upper()
    status = _status(result)
    if status not in _SUCCESS_STATUSES:
        return None
    if name == "CONFIRM_ORDER":
        return PROOF_ORDER_CONFIRMED
    if name.endswith(_ENQUIRY_SUFFIXES):
        return PROOF_ENQUIRY_SAVED
    if name.endswith(_APPOINTMENT_SUFFIXES):
        details = _result_text(result)
        if (
            (isinstance(result, dict) and result.get("confirmed") is False)
            or status in _PENDING_STATUSES
            or any(word in details for word in ('"requested"', '"pending"', '"tentative"'))
        ):
            return PROOF_APPOINTMENT_REQUESTED
        return PROOF_APPOINTMENT_CONFIRMED
    if name.endswith(_REQUEST_SUFFIXES):
        return PROOF_APPOINTMENT_REQUESTED
    return None


def proof_set(proofs: Iterable[str]) -> set[str]:
    return {str(proof) for proof in proofs if str(proof) in ACTION_CLAIMS}


def claim_has_proof(claim: str | None, proofs: Iterable[str]) -> bool:
    if not claim or claim not in ACTION_CLAIMS:
        return True
    available = proof_set(proofs)
    if claim in _RECORDED_REQUEST:
        return bool(available & _RECORDED_REQUEST)
    return claim in available


_ORDER_CLAIM = re.compile(
    r"\b(?:order|purchase)\b[^.!?]{0,60}\b(?:confirmed|placed|done|complete[d]?)\b|"
    r"\b(?:confirmed|placed)\b[^.!?]{0,40}\b(?:order|purchase)\b|"
    r"(?:ఆర్డర్|ఆర్డరు)[^.!?]{0,40}(?:నిర్ధార|పూర్తి)|"
    r"(?:ऑर्डर)[^.!?]{0,40}(?:पुष्टि|पूरा)|"
    r"(?:ஆர்டர்)[^.!?]{0,40}(?:உறுதி|முடிந்த)|"
    r"(?:ಆರ್ಡರ್)[^.!?]{0,40}(?:ದೃಢೀಕರಿಸ|ಪೂರ್ಣಗೊಂಡ)|"
    r"(?:ഓർഡർ)[^.!?]{0,40}(?:സ്ഥിരീകരിച്ച|പൂർത്തിയായ)",
    re.I,
)
_APPOINTMENT_CLAIM = re.compile(
    r"\b(?:appointment|booking|slot|visit|meeting|reservation)\b[^.!?]{0,60}"
    r"\b(?:confirmed|booked|scheduled|reserved|fixed)\b|"
    r"\b(?:confirmed|booked|scheduled|reserved)\b[^.!?]{0,40}"
    r"\b(?:appointment|booking|slot|visit|meeting|reservation)\b|"
    r"(?:అపాయింట్‌మెంట్|బుకింగ్|విజిట్)[^.!?]{0,40}(?:నిర్ధార|బుక్|షెడ్యూల్)|"
    r"(?:अपॉइंटमेंट|बुकिंग|विज़िट)[^.!?]{0,40}(?:पुष्टि|बुक|निर्धारित)|"
    r"(?:அப்பாயின்ட்மென்ட்|புக்கிங்|விஜிட்)[^.!?]{0,40}(?:உறுதி|புக்|திட்டமிட)|"
    r"(?:ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್|ಬುಕಿಂಗ್|ವಿಜಿಟ್)[^.!?]{0,40}(?:ದೃಢೀಕರಿಸ|ಬುಕ್|ನಿಗದಿ)|"
    r"(?:അപ്പോയിന്റ്മെന്റ്|ബുക്കിംഗ്)[^.!?]{0,40}(?:സ്ഥിരീകരിച്ച|ബുക്ക്|ക്രമീകരിച്ച)",
    re.I,
)
_RECORDED_CLAIM = re.compile(
    r"\b(?:enquiry|inquiry|request|details)\b[^.!?]{0,60}"
    r"\b(?:saved|recorded|submitted|noted|registered|sent|logged)\b|"
    r"\b(?:saved|recorded|submitted|noted|registered|logged)\b[^.!?]{0,40}"
    r"\b(?:enquiry|inquiry|request|details)\b|"
    r"(?:అభ్యర్థన|వివరాలు|ఎంక్వైరీ)[^.!?]{0,40}(?:సేవ్|నమోదు|పంప|తెలియజేస)|"
    r"(?:अनुरोध|विवरण|पूछताछ)[^.!?]{0,40}(?:सहेज|दर्ज|भेज|नोट)|"
    r"(?:கோரிக்கை|விவரங்கள்|விசாரணை)[^.!?]{0,40}(?:சேமி|பதிவு|அனுப்ப)|"
    r"(?:ವಿನಂತಿ|ವಿವರಗಳು|ವಿಚಾರಣೆ)[^.!?]{0,40}(?:ಉಳಿಸ|ದಾಖಲಿಸ|ಕಳುಹಿಸ)|"
    r"(?:അഭ്യർത്ഥന|വിവരങ്ങൾ|അന്വേഷണം)[^.!?]{0,40}(?:സംരക്ഷിച്ച|രേഖപ്പെടുത്തി|അയച്ച)",
    re.I,
)


# Negation must stay inside the clause that carries the claim: "no placement
# guarantee. The order is confirmed" still asserts a confirmation.
_NEGATORS = re.compile(
    r"\b(?:not|never|no|without|cannot|nahi)\b|\b\w+n['’]t\b|"
    r"(?:नहीं|नही|मत|లేదు|కాదు|இல்லை|இல்ல|கிடையா|ಅಲ್ಲ|ಇಲ್ಲ|ഇല്ല|না|નથી|ਨਹੀਂ)",
    re.I,
)
_CLAUSE_BREAK = re.compile(r"[,.!?।;\n]|\b(?:but|however|and)\b|కానీ|लेकिन|ஆனா|ಆದರೆ", re.IGNORECASE)
# Indic negation often follows the predicate. Only an adjacent negative tail
# belongs to that predicate: "confirmed with no refund" is still a claim.
_NEGATED_TAIL = re.compile(
    r"^\s*(?:(?:or|ya|paid|order|booking|slot|visit)\b\s*|या\s*|அல்லது\s*|ಅಥವಾ\s*){0,6}"
    r"(?:\b(?:not|never|no|cannot|nahi)\b|\b\w+n['’]t\b|"
    r"नहीं|नही|లేదు|కాదు|இல்ல|கிடையா|ಅಲ್ಲ|ಇಲ್ಲ|ഇല്ല)",
    re.IGNORECASE,
)


def _claim_is_negated(text: str, match: re.Match[str]) -> bool:
    if _NEGATORS.search(match.group(0)):
        return True
    prefix = text[max(0, match.start() - 40) : match.start()]
    breaks = list(_CLAUSE_BREAK.finditer(prefix))
    if breaks:
        prefix = prefix[breaks[-1].end() :]
    if _NEGATORS.search(prefix):
        return True
    return bool(_NEGATED_TAIL.search(text[match.end() : match.end() + 60]))


def _asserted(rx: re.Pattern[str], text: str) -> bool:
    return any(not _claim_is_negated(text, match) for match in rx.finditer(text))


def claims_recorded_request(text: str) -> bool:
    return _asserted(_RECORDED_CLAIM, text or "")


def unproven_claim(text: str, proofs: Iterable[str]) -> str | None:
    """The typed claim the text makes without a matching proof, if any."""
    available = proof_set(proofs)
    spoken = text or ""
    if PROOF_ORDER_CONFIRMED not in available and _asserted(_ORDER_CLAIM, spoken):
        return PROOF_ORDER_CONFIRMED
    if PROOF_APPOINTMENT_CONFIRMED not in available and _asserted(
        _APPOINTMENT_CLAIM, spoken
    ):
        return PROOF_APPOINTMENT_CONFIRMED
    if not (available & _RECORDED_REQUEST) and _asserted(_RECORDED_CLAIM, spoken):
        return PROOF_ENQUIRY_SAVED
    return None


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?।])\s+")


def replace_unproven_claims(
    text: str, proofs: Iterable[str], language: str | None, *, warning_line: str | None = None,
) -> str:
    """Remove only the claim the server cannot prove, keeping usable answers.

    An unsupported order or appointment also invalidates dependent delivery
    promises, so replace that reply. Remove unsupported recorded-request
    sentences individually, retaining separate factual answers.
    """
    spoken = (text or "").strip()
    claim = unproven_claim(spoken, proofs)
    if not claim:
        return spoken
    line = warning_line or action_unconfirmed_line_for(language)
    if claim in {PROOF_ORDER_CONFIRMED, PROOF_APPOINTMENT_CONFIRMED}:
        return line
    kept: list[str] = []
    replaced = False
    for part in _SENTENCE_SPLIT.split(spoken):
        if unproven_claim(part, proofs) == claim:
            if not replaced:
                kept.append(line)
            replaced = True
        else:
            kept.append(part)
    return " ".join(kept) if kept else line


_UNAVAILABLE_LINES = {
    "en": "I can keep a note during this call, but I cannot send this request to the team or promise a follow-up.",
    "te": "ఈ కాల్‌లో విషయం గుర్తుంచుకోగలను. కానీ టీమ్‌కు ఇది పంపే సదుపాయం లేదా follow-up హామీ ఇచ్చే సదుపాయం నాకు లేదు.",
    "hi": "मैं इस कॉल में बात नोट कर सकता हूँ, लेकिन बाहरी सिस्टम में इसे भेज या follow-up तय नहीं कर सकता।",
    "ta": "இந்த அழைப்பில் மட்டும் நினைவில் வைத்துக்கொள்ளலாம். ஆனால் team-க்கு இதை அனுப்பவோ follow-up உறுதி சொல்லவோ முடியாது.",
    "kn": "ಈ ಕರೆಯಲ್ಲಿ ಮಾತ್ರ ನೆನಪಿಟ್ಟುಕೊಳ್ಳಬಹುದು. ಆದರೆ ತಂಡಕ್ಕೆ ಇದನ್ನು ಕಳುಹಿಸಲು ಅಥವಾ follow-up ಭರವಸೆ ನೀಡಲು ಸಾಧ್ಯವಿಲ್ಲ.",
}
_REQUEST_TARGET = re.compile(
    r"enquir|inquir|request|details|team|system|crm|email|callback|follow.?up|"
    r"అభ్యర్థ|వివర|టీమ్|जांच|अनुरोध|विवरण|टीम|क्वायरी|"
    r"கோரிக்கை|விவரங்க|குழு|வಿನಂತಿ|ವಿವರ|ತಂಡ", re.IGNORECASE,
)
_REQUEST_ACTION = re.compile(
    r"sav(?:e|ed|ing)|submit|send|sent|forward|pass|record|not(?:e|ed|ing)|review|"
    r"contact|callback|follow.?up|\bcheck\b|\bupdate\b|ಸಂಪರ್ಕಿ|ಸಂಪ್ರದಿ|సంప్రదిం|संपर्क|தொடர்பு|"
    r"సేవ్|నమోదు|పంప|సమర్పి|భద్రపర|भेज|दर्ज|सहेज|नोट|"
    r"சேமி|பதிவு|அனுப்ப|ಉಳಿಸ|ದಾಖಲಿ|ಕಳುಹಿ|ಕಳಿಸ|ಪರಿಶೀಲಿಸ", re.IGNORECASE,
)
_UNAVAILABLE_NEGATION = re.compile(
    r"\b(?:no|not|cannot|can't|couldn't|unable|won't|without)\b|"
    r"చేయలే|లేను|లేము|లేదు|కాదు|नहीं|नही|मत|"
    r"முடியாத|முடியாது|இல்லை|ಆಗಲ್ಲ|ಸಾಧ್ಯವಿಲ್ಲ|ಮಾಡಲಾಗದು|ಸೌಲಭ್ಯವಿಲ್ಲ", re.IGNORECASE,
)
_LOCAL_NOTE_SCOPE = re.compile(
    r"(?:this|our)\s+(?:call|conversation)|ఈ\s*కాల్|इस\s*कॉल|இந்த\s*அழைப்|ಈ\s*(?:ಕರೆ|ಕರೆಯಲ್ಲಿ)",
    re.IGNORECASE,
)
_EXTERNAL_TARGET = re.compile(r"team|system|crm|external|email|callback|follow.?up|టీమ్|टीम|குழு|ತಂಡ", re.IGNORECASE)
_FACTUAL_PRICE = re.compile(
    r"\b(?:fee|cost|price|charge|rupees|rs)\b|₹|రూపాయ|रुपय|ரூபாய்|ರೂಪಾಯಿ", re.IGNORECASE,
)
_NEXT_STEP = re.compile(r"\b(?:will|shall|can|could|would|try|later|again)\b", re.IGNORECASE)
_SUBMISSION_TARGET = re.compile(
    r"enquir|inquir|request|lead|ticket|అభ్యర్థ|ఎంక్వైరీ|अनुरोध|पूछताछ|கோரிக்கை|விசாரணை|ವಿನಂತಿ|ವಿಚಾರಣೆ",
    re.IGNORECASE,
)
_SUBMISSION_VERB = re.compile(
    r"\b(?:submit|save|send|forward|register)\b|సమర్పి|పంపండి|సేవ్|दर्ज|भेज|சமர்ப்பி|அனுப்பு|சேமி|ಸಲ್ಲಿಸಿ|ಕಳುಹಿಸಿ|ಸೇವ್",
    re.IGNORECASE,
)
_SUBMISSION_NEGATION = re.compile(r"కండి|ಬೇಡಿ|செய்யாத|பண்ணாத", re.IGNORECASE)


def caller_requests_external_submission(text: str) -> bool:
    """High-confidence request only; it adds a limitation, never permission."""
    return any(
        _SUBMISSION_TARGET.search(clause) and _SUBMISSION_VERB.search(clause)
        and not _NEGATORS.search(clause) and not _SUBMISSION_NEGATION.search(clause)
        for clause in re.split(r"[.!?।;\n]", text or "")
    )


def unavailable_action_line_for(language: str | None) -> str:
    lang = str(language or "en-IN").split("-")[0]
    return _UNAVAILABLE_LINES.get(lang, _UNAVAILABLE_LINES["en"])


def replace_unavailable_action_promises(
    text: str, language: str | None, *, unconfirmed: bool = False,
    requested_unavailable: bool = False,
) -> str:
    """No connected gateway means no submission promise, including future tense.

    This runs only with explicit server evidence that external actions are
    unavailable. Keep factual sentences and explicitly local conversation notes;
    a booking disclaimer cannot justify an earlier promise to submit an enquiry.

    After a failed/unknown tool result, the server owns the outcome wording.
    Retain separate price facts, but never forward free-form model promises or
    retry advice after an uncertain write.
    """
    if unconfirmed or requested_unavailable:
        facts = [
            sentence for sentence in _SENTENCE_SPLIT.split((text or "").strip())
            if _FACTUAL_PRICE.search(sentence)
            and not _REQUEST_TARGET.search(sentence)
            and not _REQUEST_ACTION.search(sentence)
            and not _NEXT_STEP.search(sentence)
        ]
        boundary = action_unconfirmed_line_for(language) if unconfirmed else unavailable_action_line_for(language)
        return " ".join([*facts, boundary])
    boundary = unavailable_action_line_for(language)
    output: list[str] = []
    replaced = False
    for sentence in _SENTENCE_SPLIT.split((text or "").strip()):
        unsupported = False
        target_seen = False
        for clause in re.split(r"[,;]|\b(?:but|however)\b|కానీ|लेकिन|ஆனா|ಆದರೆ", sentence):
            target_seen = target_seen or bool(_REQUEST_TARGET.search(clause))
            if not target_seen or not _REQUEST_ACTION.search(clause):
                continue
            if _UNAVAILABLE_NEGATION.search(clause):
                continue
            if _LOCAL_NOTE_SCOPE.search(clause) and not _EXTERNAL_TARGET.search(clause):
                continue
            unsupported = True
        if unsupported:
            if not replaced:
                output.append(boundary)
                replaced = True
        else:
            output.append(sentence)
    return " ".join(output)
