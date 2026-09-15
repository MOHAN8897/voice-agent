"""Hangup judgment helpers — when the model should close the call.

The Realtime model owns the decision via the end_call tool. These helpers:
1) give the model a clear decision tree in prompts, and
2) repair missed tool calls when speech + user evidence already close the call.
"""
from __future__ import annotations

import re
from typing import Any

_AGENT_CLOSING = re.compile(
    r"\b("
    r"goodbye|good day|alvida|"
    r"team will (?:contact|reach|call|get back)|"
    r"our team will|"
    r"we(?:'ll| will) (?:have )?(?:the )?team (?:contact|call|reach)|"
    r"someone from (?:our |the )?team (?:will )?(?:contact|call|reach)|"
    r"call you back|"
    r"reach out (?:to you|shortly)|"
    r"take it from here|"
    r"all set|"
    r"(?:details|appointment|information) (?:is |are |have been )?(?:noted|saved|booked|confirmed)|"
    r"booked (?:your |the )?appointment"
    r")\b",
    re.I,
)
_USER_SHORT_ACK = re.compile(
    r"^\s*(?:ok|okay|yes|yeah|yep|sure|fine|alright|great|perfect|"
    r"thanks|thank you|thankyou|thanks a lot|thank you so much|thank you very much|"
    r"ja[,.]?\s*danke|danke(?:\s*sch[oö]n)?|"
    r"sare|సరే|ठीक|हाँ|अच्छा)[.!]?\s*$",
    re.I,
)
_INTERESTED_CONTINUE = re.compile(
    r"\b("
    r"i(?:'m| am) interested|interested in|tell me more|go on|"
    r"yes (?:please )?(?:tell|explain|share|continue)|"
    r"sounds interesting|i want (?:to )?(?:know|see|visit|buy|book)|"
    r"please (?:explain|continue|tell)|what (?:else|next)|"
    r"how (?:much|does|do|can)|can you (?:tell|explain|help)"
    r")\b",
    re.I,
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
    r"before i let you go"
    r")\b",
    re.I,
)


def agent_spoke_closing(spoken_text: str) -> bool:
    """True when the agent already delivered a closing / handoff line."""
    spoken = spoken_text or ""
    if agent_still_collecting_lead(spoken):
        return False
    return bool(_AGENT_CLOSING.search(spoken))


def agent_still_collecting_lead(spoken_text: str) -> bool:
    """True when the agent is still asking for name/phone in this utterance."""
    return bool(_AGENT_STILL_COLLECTING.search(spoken_text or ""))


def user_short_close_ack(user_text: str) -> bool:
    """True for a short affirmative close ("ok", "thanks") — not a new question."""
    return bool(_USER_SHORT_ACK.match((user_text or "").strip()))


def caller_wants_to_continue(user_text: str) -> bool:
    """True when the caller is engaged — do not hang up yet."""
    text = (user_text or "").strip()
    if not text:
        return False
    return bool(_INTERESTED_CONTINUE.search(text))


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

    return CALL_END_FAREWELLS[normalize_compile_language(language)]


def callback_farewell_for(language: str | None) -> str:
    from server.prompts.agent_voice_rules import normalize_compile_language

    return {
        "en-IN": "Your callback request is noted. Thank you for your time. Goodbye.",
        "te-IN": "మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నోట్ చేసుకున్నాను. ధన్యవాదాలు.",
        "hi-IN": "दोबारा कॉल करने का आपका अनुरोध नोट कर लिया है। धन्यवाद।",
    }[normalize_compile_language(language)]


HANGUP_JUDGMENT_RULES = """HANGUP JUDGMENT (you decide — then call end_call)
Judge every turn. Speak one short farewell AND call the end_call tool in the SAME turn when closing.

HANG UP now (farewell + end_call.should_end true):
1) firm_refusal — caller clearly not interested / no thanks / don't want / don't call.
2) goodbye — caller says bye / hang up / cut the call / that's all / stop calling.
   Polite forms such as 'Can you cut the call, please?' are end requests, not information questions.
3) goal_complete — script objective is done: needed details collected (name/phone/interest),
   next step set (team will contact / callback / visit booked), and caller affirmed or needs nothing else.
   Example close: "Noted — our team will contact you. Goodbye." + end_call reason=goal_complete.
4) goal_complete — caller asks to be contacted later: 'call me tomorrow', 'contact me tomorrow',
   'get back to me', or 'record my name and phone number'.
   Follow the server callback phase. If it is still collecting a field, ask ONLY that field.
   Do not pitch. Do not say goodbye until that field is captured. Then confirm the callback day/time
   they gave, speak a short farewell, and call end_call.
5) goal_complete — appointment or details already confirmed and you told them the team will
   take it from here / contact them. If they said thanks / okay / that's all, close now:
   one short goodbye AND end_call in the SAME turn. Do not keep wrapping after the objective is done.

KEEP TALKING (never end_call, never say goodbye):
- Caller is interested or asks more (price, options, tell me more).
- Soft maybe / not now / busy / I'll decide / not looking right now, without a request to end or call back.
- Objection (price/location) that you can still handle.
- You still need one useful fact they asked you to record (name or phone).

NATURAL CLOSE (how a person hangs up — not a sudden cut):
- Speak a complete closing in one breath: brief confirm of the next step if any, thank them, then goodbye.
- Finish the last word. Never trail off mid-sentence or stop talking as if the line already dropped.
- After goodbye, stop. The platform plays your full audio, pauses briefly, then disconnects. Do not add a second pitch.

Rules:
- Never say goodbye / good day / alvida unless end_call.should_end is true.
- Interested callers: continue until the objective is complete, then close with farewell + end_call.
- Not interested: one polite farewell + end_call immediately — do not pitch again.
- Missed tool is a failure: if you speak a closing farewell, you MUST call end_call."""
