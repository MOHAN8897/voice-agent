"""One reading of caller intent for the turn gate and the farewell rail.

The 2026-10-25 audit found the two rails disagreeing about the same words:
"Call cut చేయకండి" was read as an opt-out by the gate and as a goodbye by the
disconnect check, while "call ముగించండి" was read as neither. Mixed-language
speech is the normal case on these calls, so the disconnect act, its negation
and the callback mention are detected across scripts in one place.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_SPACE = re.compile(r"\s+")


def normalize_caller_text(text: str) -> str:
    return _SPACE.sub(" ", unicodedata.normalize("NFC", text or "").casefold()).strip()


_DISCONNECT_ACT = re.compile(
    r"\b(?:cut|end|disconnect|hang\s*up|hangup|close|drop|terminate)\b|"
    r"కట్|ముగించ|ఆపేయ|ఆపండి|తెంచ|"
    r"काट|समाप्त|बंद|खत्म|"
    r"முடி|முடிக்க|முடிச்ச|நிறுத்த|துண்டி|கட்|"
    r"ಮುಗಿಸ|ನಿಲ್ಲಿಸ|ಕಡಿತ|ಕಟ್|ಮುಕ್ತಾಯ",
    re.I,
)
_NATIVE_NEGATIVE = re.compile(
    r"వద్దు|వద్దండి|చేయకండి|చేయొద్దు|చేయవద్దు|చెయ్యకండి|కూడదు|"
    r"मत|नहीं|न\s*करें|"
    r"வேண்டாம்|கூடாது|செய்யாதீங்க|செய்யாதீர்கள்|"
    r"ಬೇಡ|ಬೇಡಿ|ಮಾಡಬೇಡಿ|ಬೇಡವೇ",
    re.I,
)
_CALL_WORD = (
    r"(?:call|కాల్|ఫోన్|कॉल|फोन|கால்|அழைப்ப\w*|ಕರೆ|ಫೋನ್|ಕಾಲ್)"
)

# "Don't cut the call", "call ముగించవద్దు", "Call मत काटिए" — the caller is
# holding the line open, so none of these may authorize a hangup or an opt-out.
_NEGATED_END = re.compile(
    r"\b(?:don'?t|do\s+not|never|please\s+don'?t|no\s+need\s+to)\s+"
    r"(?:hang\s*up|hangup|end|cut|disconnect|close|drop|terminate)\b|"
    r"\b(?:don'?t|do\s+not|never)\s+(?:cut|end|disconnect|hang\s*up)\s+"
    r"(?:the\s+|this\s+|our\s+)?(?:call|line|conversation)\b|"
    rf"{_CALL_WORD}.{{0,20}}"
    r"(?:cut|కట్|ముగించ\w*|కాట్|काट\w*|बंद\w*|समाप्त\w*|खत्म\w*|"
    r"முடி\w*|முடிச்ச\w*|நிறுத்த\w*|துண்டி\w*|கட்|ಮುಗಿಸ\w*|ನಿಲ್ಲಿಸ\w*|ಕಡಿತ|ಕಟ್)"
    r".{0,16}"
    r"(?:వద్దు|వద్దండి|చేయకండి|చేయొద్దు|చేయవద్దు|చెయ్యకండి|"
    r"मत|नहीं|न\s*करें|வேண்டாம்|கூடாது|செய்யாதீங்க|செய்யாதீர்கள்|ಬೇಡ|ಬೇಡಿ|ಮಾಡಬೇಡಿ)|"
    rf"{_CALL_WORD}.{{0,12}}"
    r"(?:వద్దు|వద్దండి|చేయకండి|मत|नहीं|வேண்டாம்|செய்யாதீங்க|ಬೇಡ|ಬೇಡಿ|ಮಾಡಬೇಡಿ)"
    r".{0,16}"
    r"(?:cut|కట్|ముగించ\w*|కాట్|काट\w*|बंद\w*|समाप्त\w*|खत्म\w*|"
    r"முடி\w*|நிறுத்த\w*|கட்|ಮುಗಿಸ\w*|ನಿಲ್ಲಿಸ\w*|ಕಡಿತ|ಕಟ್)|"
    r"(?:కట్|ముగించ\w*|కాట్|काट\w*|बंद\w*|समाप्त\w*|खत्म\w*|முடி\w*|நிறுத்த\w*|கட்|"
    r"ಮುಗಿಸ\w*|ನಿಲ್ಲಿಸ\w*|ಕಡಿತ)"
    r"(?:వద్దు|వద్దండి|కండి|కూడదు|मत|नहीं|வேண்டாம்|கூடாது|ಬೇಡ|ಬೇಡಿ)",
    re.I | re.S,
)

# "wait", "one more question" — a new turn that must cancel a pending goodbye.
_WAIT_OR_CONTINUE = re.compile(
    r"\b(?:wait|hold\s+on|one\s+(?:more|moment|second)|just\s+a\s+(?:moment|second)|"
    r"not\s+yet|hang\s+on)\b|"
    r"ఆగండి|ఆగు|కాస్త\s*ఆగ|ఇంకో\s*ప్రశ్న|ఇంకా\s*ప్రశ్న|"
    r"रुकिए|रुको|ठहरिए|एक\s*और\s*सवाल|एक\s*और\s*प्रश्न|"
    r"காத்திருங்க|காத்திரு|நில்லுங்க|இன்னொரு\s*கேள்வி|"
    r"ನಿಲ್ಲಿ|ಕಾಯಿರಿ|ಇನ್ನೊಂದು\s*ಪ್ರಶ್ನೆ",
    re.I,
)

# "I am not asking you to call me later", "I'll call you" — a mention, not consent.
_CALLBACK_REVOKED = re.compile(
    r"\b(?:not|never|didn'?t|did\s+not|don'?t|do\s+not|wasn'?t|was\s+not)\s+"
    r"(?:ask(?:ing|ed)?|request(?:ing|ed)?)\s+(?:me\s+|you\s+)?(?:to\s+)?"
    r"(?:call|contact|ring|reach\s+out)\b|"
    r"\b(?:not|never|don'?t|do\s+not|didn'?t|did\s+not)\s+(?:want|need)\s+"
    r"(?:you\s+)?(?:to\s+)?(?:call|contact|ring)\b|"
    r"\b(?:not|never|don'?t|do\s+not|didn'?t|did\s+not)\s+(?:want|need)\s+(?:a\s+)?"
    r"(?:callback|call\s*back)\b|"
    r"\b(?:not|no)\s+(?:a\s+)?callback\b|"
    r"\b(?:don'?t|do\s+not|didn'?t|never)\s+(?:book|schedule|arrange|set\s*up)\s+(?:a\s+)?callback\b|"
    r"\b(?:i(?:'ll| will| can| may)\s+(?:call|phone|contact)\s+(?:you|back)|i(?:'ll| will)\s+call\s+(?:you\s+)?later)\b|"
    r"(?:callback|call\s*back|కాల్\s*బ్యాక్|కాల్బ్యాక్)\s*(?:వద్దు|వద్దండి|అవసరం\s*లేదు|చేయొద్దు|చేయవద్దు|చేయకండి|అక్కర్లేదు|కాదు)|"
    r"(?:కాల్|call)\s*(?:వద్దు|వద్దండి|అవసరం\s*లేదు|అక్కర్లేదు)|"
    r"(?:వద్దు|వద్దండి|అవసరం\s*లేదు|అక్కర్లేదు).{0,20}(?:callback|call\s*back|కాల్\s*బ్యాక్|కాల్బ్యాక్|కాల్|call)|"
    r"(?i:call|కాల్|कॉल|फोन|கால்|கூப்பிட|ಕರೆ|ಫೋನ್).{0,40}"
    r"(?:అడగడం\s*లేదు|అడగడం\s*కాదు|అడగటం\s*లేదు|అడగటం\s*కాదు|అడిగేది\s*కాదు|"
    r"అడగలేదు|అడుగుట\s*లేదు|"
    r"नहीं\s*कह\s*रह[ाीे]*|नहीं\s*कहा|नहीं\s*मांग|नहीं\s*चाहता|नहीं\s*चाहती|"
    r"சொல்லவில்லை|கேட்கவில்லை|கேட்கல|சொல்லல|"
    r"ಕೇಳುತ್ತಿಲ್ಲ|ಕೇಳಿಲ್ಲ|ಹೇಳುತ್ತಿಲ್ಲ|ಹೇಳಿಲ್ಲ)|"
    r"(?:అడగడం\s*లేదు|नहीं\s*कह\s*रह[ाीे]*|சொல்லவில்லை|ಕೇಳುತ್ತಿಲ್ಲ).{0,40}"
    r"(?i:call|కాల్|कॉल|கால்|ಕರೆ)",
    re.I | re.S,
)

# Interest that exists in the future is welcome, not a rejection and not a
# request to be called back now.
_FUTURE_INTEREST = re.compile(
    r"\b(?:next\s+(?:month|week|year)|later\s+(?:this|next)\s+(?:month|year)|"
    r"after\s+(?:my\s+|the\s+|our\s+)?(?:exams?|graduation|festival|diwali)|"
    r"in\s+(?:a|one|two|three)\s+(?:month|week)s?|"
    r"future(?!\s+(?:calls?|contacts?|campaigns?|communications?|messages?))|"
    r"someday|some\s+day|not\s+right\s+now)\b|"
    r"(?:వచ్చే|తర్వాతి|ముందు)\s*(?:నెల|వారం|సంవత్సరం)|"
    r"భవిష్యత్తు(?!\s*(?:calls|కాల్స్|కాల్))|పరీక్షల\s*తర్వాత|"
    r"(?:अगले|आने\s*वाले)\s*(?:महीने|हफ्ते|साल)|भविष्य|परीक्षा\s*के\s*बाद|अभी\s*नहीं|"
    r"(?:அடுத்த|வரும்)\s*(?:மாதம்|வாரம்|வருடம்)|எதிர்கால|தேர்வுக்கு\s*பிறகு|இப்போ\s*இல்லை|"
    r"(?:ಮುಂದಿನ|ಬರುವ)\s*(?:ತಿಂಗಳು|ವಾರ|ವರ್ಷ)|ಭವಿಷ್ಯ|ಪರೀಕ್ಷೆ\s*ನಂತರ|ಈಗ\s*ಇಲ್ಲ",
    re.I,
)


@dataclass(frozen=True)
class CallerIntent:
    text: str
    question: bool = False
    wait_or_continue: bool = False
    negated_end: bool = False
    explicit_end: bool = False
    stop_contact: bool = False
    not_interested: bool = False
    callback_requested: bool = False
    callback_revoked: bool = False
    future_interest: bool = False
    unavailable_now: bool = False
    done: bool = False

    @property
    def keeps_call_open(self) -> bool:
        if self.stop_contact:
            return False
        return bool(
            self.wait_or_continue
            or self.negated_end
            or self.question
            or self.callback_revoked
            or self.future_interest
            or self.callback_requested
        )


def caller_text(text: str) -> str:
    return normalize_caller_text(text)


def is_negated_end(text: str) -> bool:
    return bool(_NEGATED_END.search(normalize_caller_text(text)))


def is_wait_or_continue(text: str) -> bool:
    return bool(_WAIT_OR_CONTINUE.search(normalize_caller_text(text)))


def caller_revoked_callback(text: str) -> bool:
    norm = normalize_caller_text(text)
    return bool(_CALLBACK_REVOKED.search(norm) or _CALLBACK_DECLINED.search(norm))


def has_future_interest(text: str) -> bool:
    return bool(_FUTURE_INTEREST.search(normalize_caller_text(text)))


# A callback noun names a different act than "the business calling until I say
# stop". Consent and opt-out checks must scope the negative to that noun first,
# or "callback వద్దు" reads as a permanent do-not-call request.
_CALLBACK_NOUN = (
    r"(?:callback|call\s*back|కాల్\s*బ్యాక్|కాల్బ్యాక్|कॉल\s*बैक|कालबैक|"
    r"கால்\s*பேக்|கால்பேக்|ಕಾಲ್\s*ಬ್ಯಾಕ್|ಕಾಲ್ಬ್ಯಾಕ್)"
)
_CALLBACK_DECLINED = re.compile(
    _CALLBACK_NOUN + r".{0,32}?"
    r"(?:వద్దు|వద్దండి|అవసరం\s*లేదు|అక్కర్లేదు|"
    r"नहीं|मत|न\s*करें|नको|"
    r"வேண்டாம்|கூடாது|"
    r"ಬೇಡ|ಬೇಡಿ|"
    r"not\s+(?:needed|required|necessary)|no\s+need|don'?t\s+need)|"
    r"\b(?:no|not|don'?t|do\s+not|without|skip|decline)\s+"
    r"(?:a\s+|the\s+|any\s+)?(?:callback|call\s*back)\b",
    re.I | re.S,
)
# "నేను తర్వాత call చేస్తాను", "I'll call you later" — the caller owns the next
# step. That is not consent for the business to call and not an opt-out.
_WILL_CONTACT = re.compile(
    r"\bi(?:'ll| will| can| may| would)\s+(?:call|phone|contact|reach\s+out\s+to)\s+"
    r"(?:you|the\s+(?:office|team|business|company)|back|later|tomorrow)\b|"
    r"\b(?:i|we)\s+(?:am|are)\s+going\s+to\s+(?:call|phone|contact)\s+you\b|"
    r"(?:నేను|నేనే|మేము|మేమే|nenu|nene|memu).{0,40}(?:call|కాల్|ఫోన్|సంప్రదించ\w*).{0,20}"
    r"(?:చేస్తాను|చేస్తాం|చేస్తాము|చేయగలను|చేసుకుంటాను|చేసుకుంటాం|chestanu|chestam)|"
    r"(?:मैं|हम).{0,40}(?:कॉल|फोन|संपर्क).{0,20}(?:करूंगा|करूँगा|करूँगी|करेंगे)|"
    r"(?:நான்|நாங்கள்).{0,40}(?:கால்|அழைக்க|தொடர்பு).{0,20}"
    r"(?:செய்வேன்|செய்கிறேன்|செய்வோம்)|"
    r"(?:ನಾನು|ನಾವು).{0,40}(?:ಕರೆ|ಫೋನ್|ಸಂಪರ್ಕ).{0,20}(?:ಮಾಡುತ್ತೇನೆ|ಮಾಡುತ್ತೇವೆ)",
    re.I | re.S,
)
# Final words that make a stop-contact request permanent regardless of a
# callback decline in the same turn ("don't call me again; I'll call you").
_FINAL_OPT_OUT = re.compile(
    r"\b(?:again|anymore|ever|never|permanently|at\s+all)\b|"
    r"ఎప్పటికీ|ఎప్పుడూ|మళ్ళీ|మళ్లీ|ఇక\s*మీరు|"
    r"दोबारा|फिर\s*कभी|कभी\s*नहीं|हमेशा\s*के\s*लिए|"
    r"மீண்டும்|இனி|எப்போதும்|"
    r"ಮತ್ತೆ|ಇನ್ನು|ಯಾವತ್ತೂ",
    re.I,
)


def caller_declined_callback(text: str) -> bool:
    """The current words decline a callback, not future business contact."""
    norm = normalize_caller_text(text)
    return bool(_CALLBACK_DECLINED.search(norm) and not _FINAL_OPT_OUT.search(norm))


def caller_will_contact(text: str) -> bool:
    """The caller says they will contact the business themselves."""
    return bool(_WILL_CONTACT.search(normalize_caller_text(text)))


def callback_scope_only(text: str) -> bool:
    """A callback decline with no independent permanent opt-out in the turn."""
    raw = text or ""
    return caller_declined_callback(raw) or (
        caller_will_contact(raw) and not _FINAL_OPT_OUT.search(normalize_caller_text(raw))
    )


def disconnect_act(text: str) -> bool:
    return bool(_DISCONNECT_ACT.search(normalize_caller_text(text)))


def native_negative(text: str) -> bool:
    return bool(_NATIVE_NEGATIVE.search(normalize_caller_text(text)))


def classify_caller_intent(text: str) -> CallerIntent:
    """Read the current caller turn once; each rail applies its own precedence."""
    raw = (text or "").strip()
    if not raw:
        return CallerIntent(text="")
    from server.call.end_call_validate import (
        _CALLER_DONE,
        _DONE_WORDS,
        _END_REQUEST,
        _STAY_ON_LINE,
        _UNAVAILABLE_NOW,
        _REFUSAL,
        _scoped_refusal,
        caller_unavailable_now,
        caller_stop_contact,
        looks_like_question,
    )

    norm = normalize_caller_text(raw)
    negated = is_negated_end(raw)
    revoked = caller_revoked_callback(raw)
    explicit_end = bool(_END_REQUEST.search(norm)) and not negated
    stop_contact = caller_stop_contact(raw)
    done = bool(_CALLER_DONE.search(norm) or _DONE_WORDS.search(norm))
    unavailable = caller_unavailable_now(raw)
    question = looks_like_question(raw)
    not_interested = bool(
        not explicit_end
        and not stop_contact
        and _REFUSAL.search(norm)
        and not question
        and not _scoped_refusal(raw)
        and not _STAY_ON_LINE.search(norm)
        and not negated
    )
    return CallerIntent(
        text=raw,
        question=question,
        wait_or_continue=is_wait_or_continue(raw),
        negated_end=negated,
        explicit_end=explicit_end,
        stop_contact=stop_contact,
        not_interested=not_interested,
        callback_requested=False,
        callback_revoked=revoked,
        future_interest=has_future_interest(raw),
        unavailable_now=unavailable,
        done=done,
    )
