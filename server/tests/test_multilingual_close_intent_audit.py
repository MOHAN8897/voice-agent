"""Regression corpus from the 2026-10-25 Standard-tier multilingual audit.

Every caller turn below is copied from intent-diagnostics.json in the audit.
The same words were read differently by the turn gate and the farewell rail,
so these tests pin one shared reading across all five enabled locales:
questions and future interest keep the call open, explicit endings and
opt-outs are honoured, and a negated end or withdrawn callback is never
consent to disconnect.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.call import end_call_validate as ecv
from server.call.callback_close import (
    PHASE_COLLECTING_PHONE,
    PHASE_IDLE,
    advance_callback_close,
)
from server.call.close_decision import useful_answer_after_rejected_close
from server.services import pstn_voice_core as core

# scenario -> exact caller text, per enabled locale (audit intent-diagnostics).
_CASES: dict[str, dict[str, str]] = {
    "en-IN": {
        "wait": "Wait, one more question: what is the price? Do not disconnect.",
        "future": (
            "I do not need this right now, but I am interested next month. Please tell me the "
            "current price; do not book anything or call this a permanent rejection."
        ),
        "future_more": (
            "Yes, I am still interested in future. I am not asking you to call me later right "
            "now. What should I know about the service?"
        ),
        "reject": "No thank you. I do not want your service or product. Please end this call.",
        "optout": "Do not contact me again. Remove me from future calls and end the call.",
        "done": "You have answered my questions. I do not need anything else. Goodbye, end the call.",
        "alternate": (
            "I don't want visiting cards, but I do want wedding invitations. Do you make them?"
        ),
    },
    "te-IN": {
        "wait": "ఆగండి, ఇంకో ప్రశ్న ఉంది: ధర ఎంత? Call cut చేయకండి.",
        "future": (
            "ఇప్పుడైతే అవసరం లేదు, కానీ వచ్చే నెల నాకు ఆసక్తి ఉంది. ప్రస్తుత ధర చెప్పండి. "
            "ఏదీ book చేయకండి, దీన్ని శాశ్వతంగా వద్దన్నట్టు అనుకోకండి."
        ),
        "future_more": (
            "అవును, భవిష్యత్తులో నాకు ఆసక్తి ఉంది. ఇప్పుడే తర్వాత call చేయమని నేను అడగడం "
            "లేదు. ఈ service గురించి ఇంకా ఏం తెలుసుకోవాలి?"
        ),
        "reject": (
            "వద్దండి, ధన్యవాదాలు. మీ service లేదా product నాకు అవసరం లేదు. దయచేసి call ముగించండి."
        ),
        "optout": (
            "నాకు మళ్లీ call చేయకండి. భవిష్యత్తు calls నుంచి నా పేరు తీసేసి ఈ call ముగించండి."
        ),
        "done": (
            "నా ప్రశ్నలకు సమాధానం ఇచ్చారు. ఇంకేమీ అవసరం లేదు. నమస్కారం, call ముగించండి."
        ),
        "alternate": (
            "నాకు visiting cards వద్దు, కానీ wedding invitations కావాలి. మీరు చేస్తారా?"
        ),
    },
    "hi-IN": {
        "wait": "रुकिए, एक और सवाल है: कीमत क्या है? Call मत काटिए।",
        "future": (
            "अभी जरूरत नहीं है, लेकिन अगले महीने मुझे दिलचस्पी है। अभी की कीमत बताइए। "
            "कुछ book मत कीजिए और इसे हमेशा के लिए मना करना मत समझिए।"
        ),
        "future_more": (
            "हाँ, भविष्य में मुझे दिलचस्पी है। मैं अभी बाद में call करने के लिए नहीं कह रहा हूँ। "
            "इस service के बारे में और क्या जानना चाहिए?"
        ),
        "reject": (
            "नहीं, धन्यवाद। मुझे आपकी service या product नहीं चाहिए। कृपया call समाप्त कीजिए।"
        ),
        "optout": (
            "मुझे दोबारा call मत कीजिए। आगे की calls से मेरा नाम हटाइए और यह call खत्म कीजिए।"
        ),
        "done": (
            "मेरे सवालों के जवाब मिल गए हैं। अब कुछ और नहीं चाहिए। नमस्ते, call समाप्त कीजिए।"
        ),
        "alternate": (
            "मुझे visiting cards नहीं चाहिए, लेकिन शादी के निमंत्रण चाहिए। क्या आप बनाते हैं?"
        ),
    },
    "ta-IN": {
        "wait": "காத்திருங்க, இன்னொரு கேள்வி இருக்கு: விலை என்ன? Call cut செய்யாதீங்க.",
        "future": (
            "இப்போ தேவையில்லை, ஆனால் அடுத்த மாதம் எனக்கு ஆர்வம் இருக்கு. தற்போதைய விலையைச் "
            "சொல்லுங்க. எதையும் book செய்யாதீங்க; நான் நிரந்தரமாக மறுத்ததாக எடுத்துக்காதீங்க."
        ),
        "future_more": (
            "ஆமாம், எதிர்காலத்தில் எனக்கு ஆர்வம் இருக்கு. இப்போ நான் பிறகு call செய்யச் "
            "சொல்லவில்லை. இந்த service பற்றி இன்னும் என்ன தெரிஞ்சுக்கணும்?"
        ),
        "reject": (
            "வேண்டாம், நன்றி. உங்கள் service அல்லது product எனக்கு தேவையில்லை. தயவுசெய்து "
            "call முடிச்சிடுங்க."
        ),
        "optout": (
            "எனக்கு மறுபடியும் call செய்யாதீங்க. இனி செய்யும் callsலிருந்து என் பெயரை நீக்கி "
            "இந்த call முடிச்சிடுங்க."
        ),
        "done": (
            "என் கேள்விகளுக்கு பதில் கிடைச்சது. வேற எதுவும் தேவையில்லை. வணக்கம், call முடிச்சிடுங்க."
        ),
        "alternate": (
            "எனக்கு visiting cards வேண்டாம், ஆனால் திருமண அழைப்பிதழ்கள் வேண்டும். நீங்க செய்வீங்களா?"
        ),
    },
    "kn-IN": {
        "wait": "ನಿಲ್ಲಿ, ಇನ್ನೊಂದು ಪ್ರಶ್ನೆ ಇದೆ: ಬೆಲೆ ಎಷ್ಟು? Call cut ಮಾಡಬೇಡಿ.",
        "future": (
            "ಈಗ ಅಗತ್ಯವಿಲ್ಲ, ಆದರೆ ಮುಂದಿನ ತಿಂಗಳು ನನಗೆ ಆಸಕ್ತಿ ಇದೆ. ಈಗಿನ ಬೆಲೆ ಹೇಳಿ. ಏನನ್ನೂ "
            "book ಮಾಡಬೇಡಿ; ಇದನ್ನು ಶಾಶ್ವತ ನಿರಾಕರಣೆ ಎಂದು ಭಾವಿಸಬೇಡಿ."
        ),
        "future_more": (
            "ಹೌದು, ಭವಿಷ್ಯದಲ್ಲಿ ನನಗೆ ಆಸಕ್ತಿ ಇದೆ. ನಾನು ಈಗ ನಂತರ call ಮಾಡಲು ಕೇಳುತ್ತಿಲ್ಲ. ಈ "
            "service ಬಗ್ಗೆ ಇನ್ನೇನು ತಿಳಿಯಬೇಕು?"
        ),
        "reject": (
            "ಬೇಡ, ಧನ್ಯವಾದಗಳು. ನಿಮ್ಮ service ಅಥವಾ product ನನಗೆ ಬೇಡ. ದಯವಿಟ್ಟು call ಮುಗಿಸಿ."
        ),
        "optout": (
            "ನನಗೆ ಮತ್ತೆ call ಮಾಡಬೇಡಿ. ಮುಂದೆ ಮಾಡುವ callsನಿಂದ ನನ್ನ ಹೆಸರು ತೆಗೆದು ಈ call ಮುಗಿಸಿ."
        ),
        "done": "ನನ್ನ ಪ್ರಶ್ನೆಗಳಿಗೆ ಉತ್ತರ ಸಿಕ್ಕಿದೆ. ಬೇರೆ ಏನೂ ಬೇಡ. ನಮಸ್ಕಾರ, call ಮುಗಿಸಿ.",
        "alternate": (
            "ನನಗೆ visiting cards ಬೇಡ, ಆದರೆ ಮದುವೆಯ ಆಮಂತ್ರಣಗಳು ಬೇಕು. ನೀವು ಮಾಡುತ್ತೀರಾ?"
        ),
    },
}

# close_reason, wants_hangup, question, stop_contact
_EXPECTED: dict[str, tuple[object, object, object, object]] = {
    "wait": (None, False, True, False),
    "future": (None, False, None, False),
    "future_more": (None, False, True, False),
    "reject": ("goodbye", True, False, False),
    "optout": ("firm_refusal", True, False, True),
    "done": ((None, "goodbye"), (False, True), False, False),
    "alternate": (None, False, True, False),
}


def _matches(actual, expected) -> bool:
    if isinstance(expected, tuple):
        return actual in expected
    return actual == expected


@pytest.mark.parametrize(
    ("locale", "scenario"),
    [(locale, scenario) for locale in _CASES for scenario in _CASES[locale]],
)
def test_audit_intent_diagnostics(locale: str, scenario: str):
    text = _CASES[locale][scenario]
    reason, hangup, question, stop = _EXPECTED[scenario]
    assert _matches(ecv.caller_close_reason(text), reason), (locale, scenario)
    assert _matches(ecv.caller_requested_hangup(text), hangup), (locale, scenario)
    if question is not None:
        assert ecv.looks_like_question(text) is question, (locale, scenario)
    assert ecv.caller_stop_contact(text) is stop, (locale, scenario)
    # None of these turns is a callback request; the negated ones withdraw it.
    assert ecv.caller_requested_callback(text) is False, (locale, scenario)


@pytest.mark.parametrize("locale", list(_CASES))
@pytest.mark.parametrize("scenario", ["wait", "future", "future_more", "alternate"])
def test_farewell_rail_reopens_on_wait_question_and_future_interest(locale: str, scenario: str):
    loop = core.PstnVoiceLoop(
        session_id=f"audit-{locale}", call_id=f"audit-{locale}", on_agent_wire=AsyncMock()
    )
    assert loop._close_revocable_text(_CASES[locale][scenario]) is True, (locale, scenario)


@pytest.mark.parametrize("locale", list(_CASES))
@pytest.mark.parametrize("scenario", ["reject", "optout", "done"])
def test_farewell_rail_finishes_the_callers_own_ending(locale: str, scenario: str):
    loop = core.PstnVoiceLoop(
        session_id=f"audit-{locale}", call_id=f"audit-{locale}", on_agent_wire=AsyncMock()
    )
    assert loop._close_revocable_text(_CASES[locale][scenario]) is False, (locale, scenario)


def test_withdrawn_callback_resets_a_stale_callback_phase():
    ctx = SimpleNamespace(
        callback_close_phase=PHASE_COLLECTING_PHONE,
        callback_request_text="call me later",
        callback_name="Ravi",
        callback_phone="",
        callback_when="",
    )
    state = advance_callback_close(
        ctx,
        "Yes, I am still interested in future. I am not asking you to call me later right "
        "now. What should I know about the service?",
    )
    assert state.phase == PHASE_IDLE
    assert ctx.callback_close_phase == PHASE_IDLE
    assert ctx.callback_request_text == ""


def test_rejected_close_keeps_the_answer_and_drops_only_the_farewell():
    assert (
        useful_answer_after_rejected_close(
            "Yes, the course is 4999 rupees. Goodbye.", language="en-IN"
        )
        == "Yes, the course is 4999 rupees."
    )
    assert (
        useful_answer_after_rejected_close(
            "Thank you for your time. Have a wonderful day. Goodbye.", language="en-IN"
        )
        is None
    )
    assert useful_answer_after_rejected_close("and we do,", language="en-IN") is None


def test_compiled_closing_has_one_farewell_owner_in_every_locale():
    from server.call.call_end_policy import closing_policy_section, format_call_end_section

    for locale in _CASES:
        text = closing_policy_section(locale)
        assert text, locale
        lowered = text.casefold()
        # The policy may name a goodbye only to forbid speaking it.
        assert "have a wonderful day" not in lowered, locale
        assert "thank you for your time" not in lowered, locale
    assert "Never speak a goodbye" in closing_policy_section("en-IN")
    end = format_call_end_section("en-IN")
    assert "one farewell owner" in end
    assert "leave spoken_response empty" in end


def test_compiled_brain_drops_the_model_closing_but_keeps_the_policy():
    from server.brain.compiled_brain_artifact import assemble_unified_brain

    script = (
        "--- AGENT IDENTITY ---\nYou are Ananya.\n\n"
        "--- COMPANY & OFFER ---\nFee final is 4999 rupees TOTAL. An old note says 3999 "
        "but that is WRONG, discard old fee, current fee 4999 only.\n\n"
        "--- CLOSING ---\nThank you for your time today. Have a wonderful day. Goodbye.\n\n"
        "--- GUARDRAILS ---\nDo not use the old fee of 3999 rupees."
    )
    brain = assemble_unified_brain(language="en-IN", script=script)
    assert "Have a wonderful day" not in brain
    assert "3999" not in brain
    assert "--- CLOSING ---" not in brain
    assert "There is one farewell owner" in brain
    assert "leave spoken_response empty" in brain


def test_corrected_course_fact_compiles_without_the_obsolete_price():
    from server.brain.fact_canon import canonicalize_superseded_facts

    script = (
        "Fee final is 4999 rupees TOTAL. An old note says 3999 but that is WRONG, "
        "discard old fee, current fee 4999 only.\n"
        "If they ask about the fee, state clearly that the total fee is 4999 rupees and "
        "old notes of 3999 are incorrect.\n"
        "--- GUARDRAILS ---\nDo not use the old fee of 3999 rupees."
    )
    compiled = canonicalize_superseded_facts(script)
    assert "3999" not in compiled
    assert compiled.count("4999") == 3
    assert "\n." not in compiled


def test_clipping_keeps_a_complete_sentence():
    from server.services.voice_pipeline_limits import clamp_live_spoken_reply

    assert (
        clamp_live_spoken_reply("The course covers A, B, C, and we do,", max_chars=120)
        == "The course covers A, B, C."
    )
    assert (
        clamp_live_spoken_reply("Our placement team will help you. Have", max_chars=120)
        == "Our placement team will help you."
    )


# Exact threat turn from the recheck matrix's 4_abuse scenario, in each
# enabled locale. The end request carries an adverb between "call" and the
# native verb, so the original mixed pattern missed it and 11 calls stayed
# open after the caller had explicitly asked to end the call.
_MIXED_THREAT_END = {
    "en-IN": "I will kill you. End this call now.",
    "hi-IN": (
        "\u092e\u0948\u0902 \u0924\u0941\u092e\u094d\u0939\u0947\u0902 \u091c\u093e\u0928 \u0938\u0947 "
        "\u092e\u093e\u0930 \u0926\u0942\u0901\u0917\u093e\u0964 \u092f\u0939 call "
        "\u0905\u092d\u0940 \u0938\u092e\u093e\u092a\u094d\u0924 \u0915\u0930\u094b\u0964"
    ),
    "ta-IN": (
        "\u0ba8\u0bbe\u0ba9\u0bcd \u0b89\u0ba9\u0bcd\u0ba9\u0bc8\u0b95\u0bcd "
        "\u0b95\u0bca\u0ba9\u0bcd\u0bb1\u0bc1\u0bb5\u0bbf\u0b9f\u0bc1\u0bb5\u0bc7\u0ba9\u0bcd. "
        "\u0b87\u0ba8\u0bcd\u0ba4 call \u0b87\u0baa\u0bcd\u0baa\u0bb5\u0bc7 \u0bae\u0bc1\u0b9f\u0bbf."
    ),
    "te-IN": (
        "\u0c28\u0c47\u0c28\u0c41 \u0c28\u0c3f\u0c28\u0c4d\u0c28\u0c41 "
        "\u0c1a\u0c02\u0c2a\u0c47\u0c38\u0c4d\u0c24\u0c3e\u0c28\u0c41. \u0c08 call "
        "\u0c07\u0c2a\u0c4d\u0c2a\u0c41\u0c21\u0c47 \u0c2e\u0c41\u0c17\u0c3f\u0c02\u0c1a\u0c41."
    ),
    "kn-IN": (
        "\u0ca8\u0cbe\u0ca8\u0c41 \u0ca8\u0cbf\u0ca8\u0ccd\u0ca8\u0ca8\u0ccd\u0ca8\u0cc1 "
        "\u0c95\u0cca\u0c82\u0ca6\u0cc1\u0cb9\u0cbe\u0c95\u0cc1\u0ca4\u0ccd\u0ca4\u0cc7\u0ca8\u0cc6. "
        "\u0c88 call \u0c88\u0c97\u0cb2\u0cc7 \u0cae\u0cc1\u0c97\u0cbf\u0cb8\u0cc1."
    ),
}


@pytest.mark.parametrize("locale,text", _MIXED_THREAT_END.items())
def test_explicit_end_with_adverb_between_call_and_native_verb(locale: str, text: str):
    assert ecv.caller_explicit_end_request(text)
    assert ecv.caller_requested_hangup(text)
    decision = ecv.validate_end_call(
        None, user_text=text, language=locale, call_status="active"
    )
    assert decision.accepted, decision.reject_code
    assert decision.reason == "goodbye"


def test_adverb_gap_does_not_bypass_the_negated_end_guard():
    assert not ecv.caller_explicit_end_request(
        "Don't end this call yet, I still have a question."
    )
    assert not ecv.caller_explicit_end_request(
        "\u092f\u0939 call \u092e\u0924 \u0938\u092e\u093e\u092a\u094d\u0924 \u0915\u0930\u094b, "
        "\u092e\u0947\u0930\u093e \u0938\u0935\u093e\u0932 \u0939\u0948\u0964"
    )


# Exact 3b_stop_contact caller turn from the recheck corpus. Every locale
# closes, and the close must persist the caller's real do-not-call request
# rather than a plain end_call preference.
_OPTOUT_TURNS = {
    "en-IN": "Do not contact me again. Remove me from future calls and end the call.",
    "hi-IN": (
        "\u092e\u0941\u091d\u0947 \u0926\u094b\u092c\u093e\u0930\u093e call \u092e\u0924 "
        "\u0915\u0940\u091c\u093f\u090f\u0964 \u0906\u0917\u0947 \u0915\u0940 calls \u0938\u0947 "
        "\u092e\u0947\u0930\u093e \u0928\u093e\u092e \u0939\u091f\u093e\u0907\u090f \u0914\u0930 "
        "\u092f\u0939 call \u0916\u0924\u094d\u092e \u0915\u0940\u091c\u093f\u090f\u0964"
    ),
    "ta-IN": (
        "\u0b8e\u0ba9\u0b95\u0bcd\u0b95\u0bc1 \u0bae\u0bb1\u0bc1\u0baa\u0b9f\u0bbf\u0baf\u0bc1\u0bae\u0bcd "
        "call \u0b9a\u0bc6\u0baf\u0bcd\u0baf\u0bbe\u0ba4\u0bc0\u0b99\u0bcd\u0b95. \u0b87\u0ba9\u0bbf "
        "\u0b9a\u0bc6\u0baf\u0bcd\u0baf\u0bc1\u0bae\u0bcd calls\u0bb2\u0bbf\u0bb0\u0bc1\u0ba8\u0bcd\u0ba4\u0bc1 "
        "\u0b8e\u0ba9\u0bcd \u0baa\u0bc6\u0baf\u0bb0\u0bc8 \u0ba8\u0bc0\u0b95\u0bcd\u0b95\u0bbf "
        "\u0b87\u0ba8\u0bcd\u0ba4 call \u0bae\u0bc1\u0b9f\u0bbf\u0b9a\u0bcd\u0b9a\u0bbf\u0b9f\u0bc1\u0b99\u0bcd\u0b95."
    ),
    "te-IN": (
        "\u0c28\u0c3e\u0c15\u0c41 \u0c2e\u0c33\u0c4d\u0c32\u0c40 call "
        "\u0c1a\u0c47\u0c2f\u0c15\u0c02\u0c21\u0c3f. \u0c2d\u0c35\u0c3f\u0c37\u0c4d\u0c2f\u0c24\u0c4d\u0c24\u0c41 "
        "calls \u0c28\u0c41\u0c02\u0c1a\u0c3f \u0c28\u0c3e \u0c2a\u0c47\u0c30\u0c41 "
        "\u0c24\u0c40\u0c38\u0c47\u0c38\u0c3f \u0c08 call \u0c2e\u0c41\u0c17\u0c3f\u0c02\u0c1a\u0c02\u0c21\u0c3f."
    ),
    "kn-IN": (
        "\u0ca8\u0ca8\u0c97\u0cc6 \u0cae\u0ca4\u0ccd\u0ca4\u0cc6 call "
        "\u0cae\u0cbe\u0ca1\u0cac\u0cc7\u0ca1\u0cbf. \u0cae\u0cc1\u0c82\u0ca6\u0cc6 "
        "\u0cae\u0cbe\u0ca1\u0cc1\u0cb5 calls\u0ca8\u0cbf\u0c82\u0ca6 \u0ca8\u0ca8\u0ccd\u0ca8 "
        "\u0cb9\u0cc6\u0cb8\u0cb0\u0cc1 \u0ca4\u0cc6\u0c97\u0cc6\u0ca6\u0cc1 \u0c88 call "
        "\u0cae\u0cc1\u0c97\u0cbf\u0cb8\u0cbf."
    ),
}


@pytest.mark.parametrize("locale,text", _OPTOUT_TURNS.items())
def test_native_optout_closes_and_records_do_not_call(locale: str, text: str):
    decision = ecv.validate_end_call(
        None, user_text=text, language=locale, call_status="active"
    )
    assert decision.accepted, decision.reject_code
    assert decision.reason == "firm_refusal"
    assert decision.contact_preference == "do_not_call"


def test_plain_refusal_still_ends_without_a_dnc_enrollment():
    decision = ecv.validate_end_call(
        None,
        user_text="No thank you. I do not want your service or product. Please end this call.",
        language="en-IN",
        call_status="active",
    )
    assert decision.accepted
    assert decision.contact_preference == "end_call"


_LOCALIZED_SUPERSEDED = {
    "te-IN": (
        "\u0c2a\u0c4d\u0c30\u0c38\u0c4d\u0c24\u0c41\u0c24 \u0c2b\u0c40\u0c1c\u0c41 4999 "
        "\u0c30\u0c42\u0c2a\u0c3e\u0c2f\u0c32\u0c41 \u0c2e\u0c3e\u0c24\u0c4d\u0c30\u0c2e\u0c47. "
        "\u0c2a\u0c3e\u0c24 \u0c28\u0c4b\u0c1f\u0c4d\u0c38\u0c4d\u200c\u0c32\u0c4b \u0c09\u0c28\u0c4d\u0c28 "
        "3999 \u0c24\u0c2a\u0c4d\u0c2a\u0c41, \u0c26\u0c3e\u0c28\u0c4d\u0c28\u0c3f "
        "\u0c2a\u0c30\u0c3f\u0c17\u0c23\u0c3f\u0c02\u0c1a\u0c35\u0c26\u0c4d\u0c26\u0c41."
    ),
    "hi-IN": (
        "\u0935\u0930\u094d\u0924\u092e\u093e\u0928 \u092b\u0940\u0938 4999 "
        "\u0930\u0941\u092a\u092f\u0947 \u0939\u0948\u0964 \u092a\u0941\u0930\u093e\u0928\u0947 "
        "\u0928\u094b\u091f \u092e\u0947\u0902 3999 \u0917\u0932\u0924 \u0939\u0948."
    ),
    "ta-IN": (
        "\u0ba4\u0bb1\u0bcd\u0baa\u0bcb\u0ba4\u0bc8\u0baf \u0b95\u0b9f\u0bcd\u0b9f\u0ba3\u0bae\u0bcd 4999. "
        "\u0baa\u0bb4\u0bc8\u0baf \u0b95\u0bc1\u0bb1\u0bbf\u0baa\u0bcd\u0baa\u0bbf\u0bb2\u0bcd 3999 "
        "\u0ba4\u0bb5\u0bb1\u0bc1."
    ),
    "kn-IN": (
        "\u0caa\u0ccd\u0cb0\u0cb8\u0ccd\u0ca4\u0cc1\u0ca4 \u0cae\u0cbe\u0cb8 4999. "
        "\u0cb9\u0cb3\u0cc6\u0caf \u0c9f\u0cbf\u0caa\u0ccd\u0caa\u0ca3\u0cbf\u0caf\u0cb2\u0ccd\u0cb2\u0cbf 3999 "
        "\u0ca4\u0caa\u0ccd\u0caa\u0cc1."
    ),
}


@pytest.mark.parametrize("locale,script", _LOCALIZED_SUPERSEDED.items())
def test_localized_superseded_price_is_canonicalized(locale: str, script: str):
    from server.brain.fact_canon import canonicalize_superseded_facts

    compiled = canonicalize_superseded_facts(script)
    assert "3999" not in compiled
    assert "4999" in compiled
