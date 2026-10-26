"""Reviewed close-decision corpus: 10 languages / 11 supported locales.

Every case is a reviewed expectation, not a phrase list to copy into the live
matchers. A valid refusal closes through the model's evidence span, so a new
phrasing must pass here without adding a regex entry to hangup_judge.py or
end_call_validate.py.

Covers native script, Romanized and code-mixed turns, casual and negated
refusals, stop-contact versus end-this-call, remaining requests, callback
requests and withdrawals, soft deferrals, and bare acknowledgements.
"""
from __future__ import annotations

import pytest

from server.call.close_decision import opt_out_evidence
from server.call.end_call_validate import (
    caller_firm_refusal,
    caller_requested_callback,
    looks_like_question,
    validate_end_call,
)

# The model over-proposes do_not_call for plain refusals here: the gate must
# keep ending this call separate from a permanent opt-out.
_REFUSALS = {
    "te-IN": "నాకు ఇవేమీ అక్కర్లేదండి",
    "en-IN": "I'm not interested.",
    "en-US": "No thanks, I don't want this.",
    "hi-IN": "मुझे इसमें दिलचस्पी नहीं है।",
    "ta-IN": "எனக்கு இது வேண்டாம்.",
    "kn-IN": "ನನಗೆ ಇದು ಬೇಡ.",
    "ml-IN": "എനിക്ക് ഇത് വേണ്ട.",
    "mr-IN": "मला यात रस नाही.",
    "bn-IN": "আমার এতে আগ্রহ নেই.",
    "gu-IN": "મને આમાં રસ નથી.",
    "pa-IN": "ਮੈਨੂੰ ਇਸ ਵਿੱਚ ਦਿਲਚਸਪੀ ਨਹੀਂ.",
}

_OPT_OUTS = {
    "te-IN": "దయచేసి మళ్లీ కాల్ చేయకండి.",
    "en-IN": "Please stop calling me.",
    "en-US": "Don't call me again.",
    "hi-IN": "मुझे दोबारा कॉल न करें।",
    "ta-IN": "என்னை மீண்டும் அழைக்க வேண்டாம்.",
    "kn-IN": "ನನ್ನನ್ನು ಮತ್ತೆ ಕರೆ ಮಾಡಬೇಡಿ.",
    "ml-IN": "എന്നെ വീണ്ടും ബന്ധപ്പെടേണ്ട.",
    "mr-IN": "मला पुन्हा कॉल करू नका.",
    "bn-IN": "আমাকে আবার কল করবেন না.",
    "gu-IN": "મને ફરી કૉલ ન કરો.",
    "pa-IN": "ਮੈਨੂੰ ਦੁਬਾਰਾ ਕਾਲ ਨਾ ਕਰੋ.",
}

_ROMANIZED_REFUSALS = [
    ("te-IN", "ippudu em avasaram ledandi"),
    ("te-IN", "vaddu bro, interest ledu"),
    ("hi-IN", "mujhe nahi chahiye"),
    ("ta-IN", "enakku venam"),
    ("en-IN", "No need, not interested."),
]

_REFUSAL_WITH_QUESTION = {
    "en-IN": "I don't need this, but what is the price?",
    "te-IN": "నాకు ఇది వద్దు, కానీ ధర ఎంత?",
    "ta-IN": "இது வேண்டாம், ஆனால் விலை என்ன?",
    "ml-IN": "എനിക്ക് ഇത് വേണ്ട, പക്ഷേ വില എന്താണ്?",
}

_CALLBACK_REQUESTS = {
    "en-IN": "Call me again tomorrow.",
    "te-IN": "రేపు మళ్లీ కాల్ చేయండి",
    "hi-IN": "कल फिर से कॉल कीजिए",
    "ta-IN": "நாளை மீண்டும் அழைக்கவும்",
}


def _close(
    user: str,
    language: str,
    *,
    reason: str = "firm_refusal",
    remaining: str = "",
    preference: str = "do_not_call",
    evidence: str | None = None,
):
    return validate_end_call(
        {
            "decision": "close",
            "should_end": True,
            "reason": reason,
            "evidence": user if evidence is None else evidence,
            "remaining_request": remaining,
            "contact_preference": preference,
            "farewell": "Thank you. Goodbye.",
        },
        user_text=user,
        language=language,
        completed_turns=2,
    )


@pytest.mark.parametrize("language,user", _REFUSALS.items())
def test_plain_refusal_in_every_locale_ends_this_call_without_dnc(language, user):
    decision = _close(user, language)

    assert decision.accepted is True
    assert decision.reason == "not_interested"
    assert decision.contact_preference == "end_call"


@pytest.mark.parametrize("language,user", _ROMANIZED_REFUSALS)
def test_romanized_and_code_mixed_refusals_close(language, user):
    decision = _close(user, language)

    assert decision.accepted is True
    assert decision.reason == "not_interested"
    assert decision.contact_preference == "end_call"


@pytest.mark.parametrize("language,user", _OPT_OUTS.items())
def test_stop_contact_language_enrolls_dnc_in_every_locale(language, user):
    assert opt_out_evidence(user) is True
    assert caller_requested_callback(user) is False

    decision = _close(user, language)

    assert decision.accepted is True
    assert decision.reason == "firm_refusal"
    assert decision.contact_preference == "do_not_call"


@pytest.mark.parametrize(
    "language,user",
    [
        ("ml-IN", "എനിക്ക് ഇതിൽ താല്പര്യമില്ല."),
        ("bn-IN", "আমার এতে আগ্রহ নেই।"),
        ("gu-IN", "એનામાં મને રસ નથી."),
    ],
)
def test_semantic_refusal_closes_without_live_phrase_support(language, user):
    assert caller_firm_refusal(user) is False
    assert opt_out_evidence(user) is False

    decision = _close(user, language)

    assert decision.accepted is True
    assert decision.reason == "not_interested"
    assert decision.contact_preference == "end_call"


@pytest.mark.parametrize(
    "language,user,reject_code",
    [
        ("en-IN", "I never said I am not interested, please tell me more.", "caller_engaged"),
        ("en-IN", "I didn't say I don't want it, I only asked the price.", "caller_engaged"),
        ("hi-IN", "मैंने नहीं कहा कि मुझे नहीं चाहिए, और बताइए।", "stay_on_line"),
        ("ta-IN", "நான் வேண்டாம் என்று சொல்லவில்லை, இன்னும் சொல்லுங்கள்.", "stay_on_line"),
    ],
)
def test_negated_or_quoted_refusal_keeps_the_line(language, user, reject_code):
    decision = _close(user, language)

    assert decision.accepted is False
    assert decision.reject_code == reject_code


@pytest.mark.parametrize("language,user", _REFUSAL_WITH_QUESTION.items())
def test_live_question_after_refusal_keeps_the_call_open(language, user):
    decision = _close(user, language)

    assert decision.accepted is False
    assert decision.reject_code == "user_asked_question"


def test_remaining_request_cancels_a_refusal_but_not_an_explicit_stop():
    refused = _close("No thanks.", "en-IN", reason="goodbye", remaining="send me the brochure")
    stopped = _close("Don't call me again.", "en-IN", reason="goodbye", remaining="send me the brochure")

    assert refused.accepted is False
    assert refused.reject_code == "remaining_request"
    assert stopped.accepted is True
    assert stopped.contact_preference == "do_not_call"


@pytest.mark.parametrize("language,user", _CALLBACK_REQUESTS.items())
def test_callback_request_closes_as_callback_not_dnc(language, user):
    decision = _close(user, language, reason="goal_complete", preference="callback")

    assert decision.accepted is True
    assert decision.reason == "goal_complete"
    assert decision.contact_preference == "callback"


@pytest.mark.parametrize(
    "user",
    [
        "Don't call me again, I'll call you back.",
        "Cancel the callback, don't call me again.",
    ],
)
def test_callback_withdrawal_is_an_opt_out_not_a_callback(user):
    assert caller_requested_callback(user) is False

    decision = _close(user, "en-IN", reason="goodbye")

    assert decision.accepted is True
    assert decision.contact_preference == "do_not_call"


@pytest.mark.parametrize(
    "language,user",
    [
        ("en-IN", "I'm busy right now, maybe later."),
        ("hi-IN", "मैंने नहीं कहा, और बताइए।"),
    ],
)
def test_soft_deferral_or_continuation_stays_on_the_line(language, user):
    decision = _close(user, language)

    assert decision.accepted is False
    assert decision.reject_code == "stay_on_line"


@pytest.mark.parametrize(
    "language,user",
    [
        ("en-IN", "okay thanks"),
        ("en-IN", "thanks"),
        ("te-IN", "సరే"),
        ("ta-IN", "சரி"),
        ("hi-IN", "ठीक है"),
    ],
)
def test_bare_acknowledgement_never_authorises_a_close(language, user):
    decision = _close(user, language, reason="goodbye")

    assert decision.accepted is False
    # A two-character ack is too short to count as a verifiable quote.
    assert decision.reject_code in {"no_evidence", "evidence_not_quoted"}


def test_tamil_accusative_pronoun_is_not_an_interrogative():
    assert looks_like_question("என்னை மீண்டும் அழைக்க வேண்டாம்") is False
    assert looks_like_question("இதன் விலை என்ன?") is True


def test_malayalam_stop_contact_forms_need_a_final_prohibition():
    assert opt_out_evidence("എന്നെ വീണ്ടും ബന്ധപ്പെടേണ്ട") is True
    assert opt_out_evidence("എന്നെ വിളിക്കരുത്") is True
    assert opt_out_evidence("എന്നെ നാളെ ബന്ധപ്പെടേണ്ടതുണ്ട്") is False


def test_telugu_stop_contact_is_not_a_callback_request():
    assert caller_requested_callback("దయచేసి మళ్లీ కాల్ చేయకండి.") is False
    assert caller_requested_callback("రేపు మళ్లీ కాల్ చేయండి") is True


def test_do_not_contact_is_a_final_opt_out_not_a_soft_preference():
    assert opt_out_evidence("Do not contact me ever again.") is True
    assert opt_out_evidence("Don't call me at night.") is False

    decision = _close("Do not contact me ever again.", "en-IN", reason="goodbye")

    assert decision.accepted is True
    assert decision.contact_preference == "do_not_call"
