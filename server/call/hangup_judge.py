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
    r"reach out (?:to you|shortly)"
    r")\b",
    re.I,
)
_USER_SHORT_ACK = re.compile(
    r"^\s*(?:ok|okay|yes|yeah|yep|sure|fine|alright|great|perfect|"
    r"thanks|thank you|thankyou|sare|సరే|ठीक|हाँ|अच्छा)[.!]?\s*$",
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


def agent_spoke_closing(spoken_text: str) -> bool:
    """True when the agent already delivered a closing / handoff line."""
    return bool(_AGENT_CLOSING.search(spoken_text or ""))


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


HANGUP_JUDGMENT_RULES = """HANGUP JUDGMENT (you decide — then call end_call)
Judge every turn. Speak one short farewell AND call the end_call tool in the SAME turn when closing.

HANG UP now (farewell + end_call.should_end true):
1) firm_refusal — caller clearly not interested / no thanks / don't want / don't call.
2) goodbye — caller says bye / hang up / that's all / stop calling.
3) goal_complete — script objective is done: needed details collected (name/phone/interest),
   next step set (team will contact / callback / visit booked), and caller affirmed or needs nothing else.
   Example close: "Noted — our team will contact you. Goodbye." + end_call reason=goal_complete.

KEEP TALKING (never end_call, never say goodbye):
- Caller is interested or asks more (price, options, tell me more).
- Soft maybe / not now / busy / later / I'll decide / not looking right now.
- Objection (price/location) that you can still handle.
- You still need one useful fact to finish the objective.

Rules:
- Never say goodbye / good day / alvida unless end_call.should_end is true.
- Interested callers: continue until the objective is complete, then close with farewell + end_call.
- Not interested: one polite farewell + end_call immediately — do not pitch again.
- Missed tool is a failure: if you speak a closing farewell, you MUST call end_call."""
