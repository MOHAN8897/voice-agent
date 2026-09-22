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


HANGUP_JUDGMENT_RULES = """HANGUP JUDGMENT (one story — the platform owns disconnect timing)
Call end_call in the SAME turn as a short farewell only when the caller has confirmed they are done.

HANG UP (farewell + end_call.should_end true):
1) firm_refusal — not interested / no thanks / don't want / don't call.
2) goodbye — bye, hang up, cut the call, that's all / that's it, stop calling,
   I'm sleeping, I have to go. 'Can you cut the call, please?' and ASR 'can you call this call'
   are end requests, not information questions. Do not ask 'are you still there?' after that.
3) goal_complete — they asked for a callback/visit/handoff, any missing name/phone they wanted
   recorded is captured, they confirmed that next step (not a bare okay/thanks), then you confirm
   it in one line and say goodbye.

KEEP TALKING (never goodbye, never end_call):
- Interested callers, questions, tell me more, price, objections you can still handle.
- Bare okay / thanks / alright — that is not permission to hang up.
- Busy / not now / maybe / I'll decide: offer ONE callback time, no pitch, stay on the line
  until they pick a time, decline the callback, or ask to end.
- I'm here / wait / hold on / hello after goodbye or 'are you still there?': continue the topic.
- A fact they already said on this call (name, phone, area, budget): never ask it again.

HOW A CLOSE WORKS:
- Thank them, say goodbye once, then stop. The platform listens; it disconnects only if they stay silent.
- If they speak after goodbye, discard hangup and answer them.
- Use end_call only — do not also require call_action to hang up.
- Never say goodbye unless end_call.should_end is true."""
