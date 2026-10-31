"""Hangup judgment helpers — when the model should close the call.

The Realtime model normally decides via the end_call tool. These helpers:
1) give the model a clear decision tree in prompts, and
2) repair missed tool calls, including explicit terminal agent farewells on
   primary Gemini PSTN calls.
"""
from __future__ import annotations

import re
from typing import Any

_AGENT_CLOSING = re.compile(
    r"\b("
    r"goodbye|good day|alvida|"
    r"time ichinanduku|ichinanduku thanks|dhanyavaadalu|"
    r"team will (?:contact|reach|call|get back)|"
    r"our team will|"
    r"we(?:'ll| will) (?:have )?(?:the )?team (?:contact|call|reach)|"
    r"someone from (?:our |the )?team (?:will )?(?:contact|call|reach)|"
    r"call you back|"
    r"reach out (?:to you|shortly)|"
    r"take it from here|"
    r"all set|"
    r"(?:details|appointment|information) (?:is |are |have been )?(?:noted|saved|booked|confirmed)|"
    r"booked (?:your |the )?appointment|"
    r"thank(?:s| you) for your time|thanks for your time|"
    r"have a (?:great|good|nice) day|you'?re welcome"
    r")\b",
    re.I,
)
_AGENT_DISQUALIFY = re.compile(
    r"\b("
    r"since you don'?t have|"
    r"you don'?t (?:have|own) (?:a |any )?(?:car|vehicle|bike|motorbike)|"
    r"not (?:able|eligible) to (?:help|assist)|"
    r"unable to (?:help|assist) you(?: today)?|"
    r"won'?t be able to (?:help|service)|"
    r"doesn'?t (?:apply|qualify)"
    r")\b",
    re.I,
)
_USER_SHORT_ACK = re.compile(
    r"^\s*(?:ok|okay|yes|yeah|yep|sure|fine|alright|great|perfect|"
    r"thanks|thank you|thankyou|thanks a lot|thank you so much|thank you very much|"
    r"ja[,.]?\s*danke|danke(?:\s*sch[oö]n)?|"
    r"sare|సరే|ठीक(?:\s*है)?|हाँ|अच्छा|சரி|ஆமாம்|ஆம்|நன்றி)[.!]?\s*$",
    re.I,
)
_INTERESTED_CONTINUE = re.compile(
    r"\b("
    r"i(?:'m| am) interested|tell me more|go on|"
    r"yes (?:please )?(?:tell|explain|share|continue)|"
    r"sounds interesting|i want (?:to )?(?:know|see|visit|buy|book)|"
    r"please (?:explain|continue|tell)|what (?:else|next)|"
    r"how (?:much|does|do|can)|can you (?:tell|explain|help)|"
    # Asking for more is a continuation even when it starts with a close-like
    # courtesy ("thanks, but one more question"). Backup only — the close
    # decision step reads the turn's meaning.
    r"(?:one|a) (?:more|other|last) (?:question|thing|doubt|query)|"
    r"thanks?,? but .{0,40}(?:question|ask|know|understand)|"
    r"दिलचस्पी\s*है|और\s*जानना|और\s*बताइए|आगे\s*बताइए|एक\s*और\s*(?:सवाल|बात)|"
    r"ఆసక్తి\s*ఉంది|ఇంకా\s*చెప్పండి|మరింత\s*వివరించండి|ఇంకో\s*(?:ప్రశ్న|విషయం)|"
    r"ஆர்வமாக\s*இருக்கிறது|ஆர்வம்\s*இருக்கு|மேலும்\s*சொல்லுங்கள்|இன்னும்\s*விவரமாக|"
    r"இன்னொரு\s*(?:கேள்வி|விஷயம்)"
    r")\b",
    re.I,
)
# Staying in contact / receiving updates is continuation intent, not a goodbye.
_KEEP_UPDATES = re.compile(
    r"\bkeep\s+me\s+(?:updated|informed|posted|in\s+the\s+loop)\b|"
    r"\b(?:please\s+)?keep\s+calling\s+me\s+(?:with|for)\b|"
    r"\b(?:send|share|give)\s+me\s+(?:the\s+)?(?:updates?|details|information|info)\b|"
    r"\bcall\s+me\s+(?:with|for)\s+(?:updates?|details|information|info)\b|"
    r"\bi\s+(?:want|need|would\s+like)\s+(?:to\s+be\s+)?(?:kept\s+)?(?:updated|informed)\b|"
    r"\blet\s+me\s+know\b",
    re.I,
)
# A complaint about repeated calls is the opposite of "keep calling me".
_KEEP_CALLING_COMPLAINT = re.compile(
    r"\b(?:why|how\s+many\s+times)\s+(?:do|are|have)\s+you(?:r)?(?:\s+people)?\s+"
    r"(?:keep|always|still)\s+(?:calling|contacting|phoning)\b|"
    r"\byou(?:r)?\s+people\s+keep\s+(?:calling|contacting)\b|"
    r"\bstop\s+these\s+calls\b",
    re.I,
)
# Denying a refusal ("I never said I wasn't interested") is not a refusal.
_NEGATED_REFUSAL = re.compile(
    r"\b(?:never|didn'?t|did\s+not|haven'?t|have\s+not)\s+(?:say|said|mean|mention)\b"
    r".{0,40}\b(?:not\s+interested|don'?t\s+want|do\s+not\s+want|no\s+need|not\s+for\s+me|no|nothing)\b|"
    r"\bnot\s+saying\s+(?:no|not\s+interested)\b|"
    r"\bdon'?t\s+(?:assume|think|decide)\b.{0,30}\b(?:not\s+interested|no)\b|"
    r"\bi(?:'m| am)\s+still\s+interested\b|"
    r"\bwhy\s+(?:do|would)\s+you\s+(?:think|assume)\b.{0,30}\bnot\s+interested\b",
    re.I | re.S,
)
_LEAD_CONTEXT = re.compile(
    r"contact details for the team|callback|team (?:will |to )?follow",
    re.I,
)


_AGENT_STILL_COLLECTING = re.compile(
    r"\b("
    r"need your (?:name|phone|number)|"
    r"may i have your (?:name|phone|number)|"
    r"what(?:'s| is) your (?:name|phone|number)|"
    r"once i have that|"
    r"best (?:phone |callback )?number|"
    r"good phone number|"
    r"before i let you go|"
    r"(?:உங்கள்|உங்க).{0,20}(?:பெயர்|நம்பர்|எண்|போன்)|"
    r"(?:பெயர்|நம்பர்|எண்).{0,20}(?:சொல்லுங்கள்|சொல்லுங்க|தர முடியுமா)|"
    r"(?:आपका|अपना).{0,12}(?:नाम|फोन|नंबर)|"
    r"(?:మీ|మీరు).{0,16}(?:పేరు|నంబర్|ఫోన్)"
    r")\b",
    re.I,
)


_INDIC_CLOSING = re.compile(
    r"ధన్యవాదాలు|సమయం\s*ఇచ్చినందుకు|ఇచ్చినందుకు\s*ధన్యవాదాలు|धन्यवाद|समय\s*देने\s*के\s*लिए|"
    r"நேரம்\s*ஒதுக்கியதற்கு\s*நன்றி|விடைபெறுகிறேன்|போய்\s*வருகிறேன்",
    re.I,
)


_TERMINAL_FAREWELL = re.compile(
    r"(?<!\w)(?:"
    r"good[ -]?bye|bye(?:[ -]bye| for now)?|good (?:day|night)|take care|have a good one|"
    r"have a (?:very )?(?:nice|good|great|wonderful|lovely) (?:day|evening|night|weekend)|"
    r"(?:talk|speak) to you (?:later|soon)|see you (?:later|soon)|"
    r"alvida|అల్విదా|ఉంటానండి|మళ్లీ మాట్లాడుకుందాం|మళ్ళీ మాట్లాడుకుందాం|"
    r"(?:మీకు )?శుభ\s*దినం|మీ రోజు శుభంగా ఉండాలి|"
    r"కాల్\s*(?:cut|కట్)\s*(?:చేస్తున్నాను|చేస్తున్నా)|కట్\s*(?:చేస్తున్నాను|చేస్తున్నా)|"
    r"अलविदा|आपका दिन शुभ हो|फिर मिलेंगे|"
    r"விடைபெறுகிறேன்|போய்\s*வருகிறேன்|உங்கள் நாள் இனிதாக அமையட்டும்|"
    r"நல்ல நாளாக அமையட்டும்|"
    r"ವಿದಾಯ|ನಿಮ್ಮ ದಿನ ಶುಭವಾಗಲಿ|ಶುಭ ದಿನವಾಗಲಿ|ಮತ್ತೆ ಮಾತನಾಡೋಣ"
    r")(?:[,!.।\s]*(?:sir|ma'am|madam|సార్|మేడమ్|అండి|जी|सर|मैडम|சார்|மேடம்|ಸರ್|ಮೇಡಂ|"
    r"thank you|thanks|take care|bye|goodbye|ధన్యవాదాలు)){0,3}"
    r"[.!।…\s]*$",
    re.IGNORECASE,
)
_FAREWELL_MENTION = re.compile(
    r"\b(?:say|saying|said|says|word|phrase|means|called|translate(?:d)?(?: as| to)?|"
    r"(?:do not|don't|never|won't|will not|not)(?: say)?)\s*$", re.IGNORECASE,
)


def agent_spoke_terminal_farewell(spoken_text: str) -> bool:
    """An explicit final goodbye, excluding thanks, questions and quoted examples."""
    spoken = (spoken_text or "").strip()
    if "?" in spoken or agent_still_collecting_lead(spoken):
        return False
    match = _TERMINAL_FAREWELL.search(spoken)
    if match:
        return not bool(_FAREWELL_MENTION.search(spoken[:match.start()]))
    # Some language packs end with a greeting word (e.g. namaskar). Require
    # their entire authored farewell, so an ordinary opening cannot end a call.
    from server.prompts.agent_voice_rules import CALL_END_FAREWELLS

    normalized = re.sub(r"\s+", " ", spoken).casefold().rstrip(" .!।…")
    for farewell in CALL_END_FAREWELLS.values():
        ending = re.sub(r"\s+", " ", farewell).casefold().rstrip(" .!।…")
        if normalized.endswith(ending) and not _FAREWELL_MENTION.search(normalized[:-len(ending)]):
            return True
    return False


def agent_spoke_closing(spoken_text: str) -> bool:
    """True when the agent already delivered a closing / handoff line."""
    spoken = spoken_text or ""
    if agent_still_collecting_lead(spoken):
        return False
    return bool(_AGENT_CLOSING.search(spoken) or _INDIC_CLOSING.search(spoken))


def agent_spoke_disqualification_close(spoken_text: str) -> bool:
    """True when the agent closed because the caller is not a service lead (e.g. no vehicle)."""
    return bool(_AGENT_DISQUALIFY.search(spoken_text or ""))


def agent_still_collecting_lead(spoken_text: str) -> bool:
    """True when the agent is still asking for name/phone in this utterance."""
    return bool(_AGENT_STILL_COLLECTING.search(spoken_text or ""))


def user_short_close_ack(user_text: str) -> bool:
    """True for a short affirmative close ("ok", "thanks") — not a new question."""
    return bool(_USER_SHORT_ACK.match((user_text or "").strip()))


_POLITE_THANKS_ONLY = re.compile(
    r"^\s*(?:"
    r"(?:yeah|yes|yep|ok|okay|sure|fine|alright|mhm|mm[- ]?hm|uh[- ]?huh)"
    r"(?:[,.]?\s+then)?[,.]?\s+)?"
    r"(?:thanks?|thank you)(?:\s+so much)?[.!]?\s*$",
    re.I,
)


def caller_polite_thanks_only(user_text: str) -> bool:
    """Thanks / yeah thank you after the agent closed — not a new request."""
    text = (user_text or "").strip()
    if not text or "?" in text:
        return False
    if caller_wants_to_continue(text):
        return False
    return bool(_USER_SHORT_ACK.match(text) or _POLITE_THANKS_ONLY.match(text))


def caller_wants_to_continue(user_text: str) -> bool:
    """True when the caller is engaged — do not hang up yet."""
    text = (user_text or "").strip()
    if not text:
        return False
    if _KEEP_UPDATES.search(text) or _NEGATED_REFUSAL.search(text):
        return True
    return bool(_INTERESTED_CONTINUE.search(text))


def caller_negated_refusal(user_text: str) -> bool:
    """The caller is denying a refusal ("I never said no"), not making one."""
    return bool(_NEGATED_REFUSAL.search((user_text or "").strip()))


def caller_complains_about_repeated_calls(user_text: str) -> bool:
    """A complaint about being called repeatedly — close-worthy, unlike a request for updates."""
    return bool(_KEEP_CALLING_COMPLAINT.search((user_text or "").strip()))


_CALLBACK_WITHDRAWAL = re.compile(
    r"\b("
    r"don'?t (?:have to |need to )?call|"
    r"do not call|don'?t call(?: me)?|"
    r"no callback|cancel (?:the )?callback|"
    r"stop calling|"
    r"இனி.{0,16}(?:அழைக்க|தொடர்பு).{0,16}வேண்டாம்|அழைக்காதீர்கள்|தொடர்பு\s*கொள்ளாதீர்கள்"
    r")\b",
    re.I,
)
_DECLINE_MORE_HELP = re.compile(
    r"^(?:no(?:pe)?|nah)(?:[,.]?\s*(?:ma'?am|sir|thanks?|thank you))?[.!?]*\s*$"
    r"|^(?:nothing else|no thanks|that'?s (?:all|it)|not really)[.!?]*\s*$"
    r"|^(?:வேண்டாம்|வேண்டாம்[,.]?\s*நன்றி|அவ்வளவுதான்)[.!?]*\s*$",
    re.I,
)
_GENERIC_INBOUND_GREETING = re.compile(
    r"^(?:hello[!,.]?\s*)?how can i help you(?: today)?[.!?]*\s*$",
    re.I,
)


def caller_withdrew_callback(user_text: str) -> bool:
    """Explicit callback cancellation — not a bare 'no' to 'anything else?'."""
    return bool(_CALLBACK_WITHDRAWAL.search((user_text or "").strip()))


def caller_declines_more_help(user_text: str) -> bool:
    """Short negative after the agent asked if there is anything else."""
    text = (user_text or "").strip()
    if not text or caller_withdrew_callback(text) or caller_wants_to_continue(text):
        return False
    return bool(_DECLINE_MORE_HELP.match(text))


def is_generic_inbound_greeting(spoken_text: str) -> bool:
    return bool(_GENERIC_INBOUND_GREETING.match((spoken_text or "").strip()))


def memory_has_lead_handoff(snapshot: dict[str, Any] | None) -> bool:
    """Lead details captured for team follow-up (not bare telephony CLI phone)."""
    if not snapshot:
        return False
    facts = snapshot.get("facts") or {}
    if isinstance(facts, dict):
        for key in ("callback_phone", "caller_email", "caller_name"):
            if str(facts.get(key) or "").strip():
                return True
    ctx = str(snapshot.get("important_context") or "")
    return bool(_LEAD_CONTEXT.search(ctx))


def default_farewell_for(language: str | None) -> str:
    from server.prompts.agent_voice_rules import CALL_END_FAREWELLS, normalize_compile_language

    lang = normalize_compile_language(language)
    return CALL_END_FAREWELLS.get(lang) or CALL_END_FAREWELLS["en-IN"]


def callback_farewell_for(language: str | None) -> str:
    from server.prompts.agent_voice_rules import normalize_compile_language

    lang = normalize_compile_language(language)
    pack = {
        "en-IN": "Your callback request is noted. Thank you for your time. Goodbye.",
        "en-US": "Your callback request is noted. Thank you for your time. Goodbye.",
        "te-IN": "మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నోట్ చేసుకున్నాను. ధన్యవాదాలు.",
        "hi-IN": "दोबारा कॉल करने का आपका अनुरोध नोट कर लिया है। धन्यवाद।",
        "ta-IN": "உங்கள் callback கோரிக்கையை பதிவு செய்துவிட்டேன். நன்றி.",
    }
    return pack.get(lang) or default_farewell_for(lang)


def silence_close_instruction(language: str | None) -> str:
    farewell = default_farewell_for(language)
    return (
        "The caller has been silent. Propose a close; the platform will speak the approved "
        f"farewell (example: {farewell}). Do not say goodbye yourself. No question, no pitch."
    )


def map_call_action_end_reason(reason: str | None) -> str:
    raw = str(reason or "").strip().lower()
    return {
        "goodbye": "goodbye",
        "goal_complete": "goal_complete",
        "firm_refusal": "firm_refusal",
        "not_interested": "not_interested",
        "opt_out": "goodbye",
        "callback_cancelled": "goodbye",
        "abuse": "abuse",
        "out_of_scope": "out_of_scope",
    }.get(raw, "goodbye")


HANGUP_JUDGMENT_RULES = """HANGUP JUDGMENT (one story — judge meaning; the platform owns disconnect timing and farewell)
Decide from what the caller means, in any language or mix, never from a fixed phrase list.
- KEEP TALKING (decision continue): interested, asking, objecting, hello or wait. Answer first and stay on the line.
- Busy or call-me-later: acknowledge, ask once for a convenient time, note the callback, then close; never promise an automatic call. A bare okay or thanks is never permission to hang up.
- CLARIFY (decision clarify): garbled or ambiguous input — ask one short question, then follow the answer.
- HANG UP (decision close) only for: firm_refusal — an explicit stop-contact request; not_interested — a clear refusal that is not an opt-out; goodbye — an explicit end request (bye, hang up, that's all, I have to go); goal_complete — the script objective and agreed next step are confirmed; abuse — hostile or threatening; answer briefly and leave.
- Default is continue. A price, service or product question is never a reason to close.
When you close:
- JSON sessions: end_call = evidence = the caller's own words from THIS turn that justify it, reason, decision "close", remaining_request = anything they still want (a real request cancels the close), contact_preference. Never put a farewell in your reply text.
- Live audio: request_end_call (or end_call) with the matching reason and contact_preference. Do not speak a goodbye.
contact_preference is do_not_call only when they asked to stop being contacted; otherwise end_call.
The platform validates the decision and speaks its own approved farewell. Never say goodbye before an approved close, and after a close do not start another turn."""

