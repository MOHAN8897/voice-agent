"""Server-side hangup gate — LLM may propose end_call; this decides."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from server.call.call_end_policy import HANGUP_REASONS as POLICY_REASONS, allowed_reasons_for
from server.call.hangup_judge import (
    agent_spoke_closing,
    caller_wants_to_continue,
    default_farewell_for,
    memory_has_lead_handoff,
    user_short_close_ack,
)
from server.prompts.agent_voice_rules import normalize_compile_language
from server.utils.logger import logger

END_CALL_REASONS = frozenset({"none", *POLICY_REASONS})
HANGUP_REASONS = frozenset(POLICY_REASONS)

_QUESTION_RE = re.compile(
    r"(\?|^(what|why|how|when|where|who|can you|could you|please tell|will you)\b"
    r"|ఏమిటి|ఎలా|ఎందుకు|కదా\s*\?|क्या|कैसे|क्यों)",
    re.I,
)
_GOODBYE = re.compile(
    r"\b(bye|goodbye|good night|hang up|hangup|don't call|do not call|stop calling|"
    r"keep calling|stop the calls|alvida|call cheyoddu|call cheyaku|call cheyakandi)\b|"
    r"వద్దు\s*call|కాల్\s*చేయొద్దు|call\s*చేయక|ఇక\s*call|చేయకండి",
    re.I,
)
# Do not match లేదు inside నచ్చలేదు / కాలేదు, or bare వద్దు in "ఇంకేమీ వద్దు".
_REFUSAL = re.compile(
    r"\b(not interested|no thanks|don't want|do not want|nahi chahiye|"
    r"mat karo|no interest|not for me|no need|remove me|"
    r"don'?t (?:want|need) (?:this|it|any)|stop (?:this|the) call)\b|"
    r"\b(vaddu|ledu)\b.{0,48}interest|interest.{0,24}\b(vaddu|ledu)\b|"
    r"interest\s*లేదు|interested\s*nahi|"
    r"(?:వద్దు.{0,48}(?:interest|call)|(?:interest|call).{0,24}వద్దు)",
    re.I | re.S,
)
_ABUSE = re.compile(
    r"\b(kill you|rape|bomb|terrorist)\b",
    re.I,
)
_GOAL_DONE = re.compile(
    r"\b(booked|scheduled|ticket[_ ]?id|order[_ ]?id|confirmed slot|visit booked|"
    r"lead[_ ]?captured|callback[_ ]?scheduled)\b",
    re.I,
)
_STAY_ON_LINE = re.compile(
    r"\b(frustrated|frustrating|explained this|taking too long|"
    r"maybe|think about it|not now|busy|in a meeting|email me|text me|"
    r"call (me )?later|i'll decide|will think|don't have time for (a )?pitch|"
    r"not looking|not in the market|not looking for)\b",
    re.I,
)
_CALLER_DONE = re.compile(
    r"^\s*(?:thanks|thank you)[,.]?\s+that'?s (?:all|it)(?:\s+for now)?\b.*"
    r"(?:\bbye\b|\bgoodbye\b)?\s*[.!]?\s*$|"
    r"^\s*that'?s (?:all|it)(?:\s+for now)?(?:[,.]?\s*(?:thanks|thank you))?"
    r"(?:[,.]?\s*(?:bye|goodbye))?\s*[.!]?\s*$",
    re.I,
)
_GOAL_COMPLETE_USER = re.compile(
    r"\b(that answers (?:it|my question)|that(?:'s| is) (?:sorted|resolved)|"
    r"i (?:have|got) (?:the|my) answer|i know .{1,40} now|"
    r"that is all i needed|that(?:'s| is) what i needed|"
    r"(?:yes|yeah|ok|okay|sure|fine|please).{0,40}"
    r"(?:call me(?: back)?|team (?:will |can )?call|callback|reach out)|"
    r"(?:call me(?: back)?|callback).{0,20}(?:please|yes|ok|okay)|"
    r"(?:yes|yeah|ok|okay).{0,24}(?:team (?:will |can )?contact|have (?:them|the team) call))\b",
    re.I,
)
_OPT_OUT = re.compile(
    r"don't call|do not call|stop calling|keep calling|stop the calls|never (?:call|contact)|please stop calling",
    re.I,
)

# Polite requests are grammatically questions, but explicitly end this call.
_END_REQUEST = re.compile(
    r"\b(?:hang\s*up|(?:cut|end|disconnect|stop)\s+(?:the |this |our )?call)\b|"
    r"\bcall\s+(?:cut|band|end)\s*(?:karo|kar do|chey|cheyyi|cheyandi)?\b|"
    r"కాల్\s*(?:కట్|ఆపండి|ముగించండి)|कॉल\s*(?:काट|बंद)", re.I,
)
_NEGATED_END = re.compile(r"\b(?:don'?t|do not|never)\s+(?:hang\s*up|end|cut|disconnect)\b", re.I)
_CALLBACK_REQUEST = re.compile(
    r"\b(?:call|phone|ring)\s+me\s+(?:(?:back|again)\b(?:\s+(?:later|tomorrow))?|"
    r"later\b|tomorrow\b|after\b|next\b|at\s+\d)|"
    r"\b(?:call|phone|ring)\s+me\s+(?:on\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b|"
    r"\b(?:repu|tarvata|malli)\s+(?:naaku\s+)?call\b|"
    r"(?:రేపు|తర్వాత|మళ్ళీ|మళ్లీ).{0,16}(?:కాల్|call)|"
    r"(?:कल|बाद में).{0,16}(?:कॉल|फोन)", re.I,
)
_NEGATED_CALLBACK = re.compile(
    r"\b(?:don'?t|do not|never|cannot|can'?t)\s+(?:you\s+)?(?:call|phone|ring)\s+me|"
    r"\b(?:can|could|should|will)\s+i\s+call\b|"
    r"\b(?:if|whether)\s+you\s+(?:can\s+)?call\s+me|"
    r"\b(?:before|first).{0,20}(?:tell|explain|answer)|\b(?:tell|explain|answer).{0,30}\bfirst\b", re.I,
)


def caller_requested_callback(user_text: str) -> bool:
    """A direct request to move this conversation to a later call, not a question about callbacks."""
    text = user_text or ""
    return bool(_CALLBACK_REQUEST.search(text) and not _NEGATED_CALLBACK.search(text))


def caller_explicit_end_request(user_text: str) -> bool:
    text = user_text or ""
    return bool(_END_REQUEST.search(text) and not _NEGATED_END.search(text))


@dataclass(frozen=True)
class EndCallDecision:
    accepted: bool
    should_end: bool
    reason: str
    farewell: str
    reject_code: str | None = None


def parse_end_call_payload(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {"should_end": False, "reason": "none", "farewell": ""}
    should_end = bool(raw.get("should_end"))
    reason = str(raw.get("reason") or "none").strip().lower()
    if reason not in END_CALL_REASONS:
        reason = "none"
    farewell = str(raw.get("farewell") or "")[:240]
    return {"should_end": should_end, "reason": reason, "farewell": farewell}


def looks_like_question(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(_QUESTION_RE.search(t))


def memory_has_goal_complete(snapshot: dict[str, Any] | None) -> bool:
    if not snapshot:
        return False
    blobs: list[str] = []
    facts = snapshot.get("facts") or {}
    prefs = snapshot.get("preferences") or {}
    if isinstance(facts, dict):
        for k, v in facts.items():
            blobs.append(f"{k} {v}")
    if isinstance(prefs, dict):
        for k, v in prefs.items():
            blobs.append(f"{k} {v}")
    blobs.append(str(snapshot.get("summary") or ""))
    blobs.append(str(snapshot.get("important_context") or ""))
    joined = " ".join(blobs)
    return bool(_GOAL_DONE.search(joined))


def _evidence_ok(
    reason: str,
    user_text: str,
    *,
    language: str,
    completed_turns: int = 0,
    memory_snapshot: dict[str, Any] | None = None,
    spoken_text: str = "",
) -> bool:
    text = user_text or ""
    spoken = spoken_text or ""
    if reason == "goodbye":
        return bool(_GOODBYE.search(text) or _CALLER_DONE.search(text) or caller_explicit_end_request(text))
    if reason == "firm_refusal":
        return bool(_REFUSAL.search(text))
    if reason == "abuse":
        return bool(_ABUSE.search(text))
    if reason == "goal_complete":
        if caller_requested_callback(text):
            return True
        if looks_like_question(text):
            return False
        if _GOAL_COMPLETE_USER.search(text) or memory_has_goal_complete(memory_snapshot):
            return True
        # Objective closed: agent spoke handoff/farewell with lead details or a short ack.
        if agent_spoke_closing(spoken) and (
            memory_has_lead_handoff(memory_snapshot)
            or (user_short_close_ack(text) and completed_turns >= 1)
        ):
            return True
        return False
    if reason == "out_of_scope":
        return bool(text.strip()) and not looks_like_question(text) and completed_turns >= 1
    return False


def caller_requested_hangup(user_text: str) -> bool:
    """True when the caller explicitly asked to stop / said goodbye."""
    return _user_wants_hangup(user_text)


def caller_firm_refusal(user_text: str) -> bool:
    """True when the caller clearly refuses — hang up (not soft maybe / not looking)."""
    text = user_text or ""
    if not text.strip() or looks_like_question(text):
        return False
    if _STAY_ON_LINE.search(text):
        return False
    return bool(_REFUSAL.search(text))


def caller_confirmed_goal_complete(user_text: str) -> bool:
    text = user_text or ""
    if not text.strip() or looks_like_question(text):
        return False
    if _STAY_ON_LINE.search(text):
        return False
    return bool(_GOAL_COMPLETE_USER.search(text) or _CALLER_DONE.search(text))


def _user_wants_hangup(user_text: str) -> bool:
    text = user_text or ""
    if caller_explicit_end_request(text):
        return True
    if _NEGATED_END.search(text):
        return False
    if _OPT_OUT.search(text) or _CALLER_DONE.search(text):
        return True
    if looks_like_question(text):
        return False
    return bool(_GOODBYE.search(text))


def _force_end(reason: str, farewell: str, spoken: str, language: str) -> dict[str, Any]:
    text = (farewell or spoken or "").strip() or default_farewell_for(language)
    return {"should_end": True, "reason": reason, "farewell": text[:240]}


def validate_end_call(
    raw: Any,
    *,
    user_text: str,
    language: str = "te-IN",
    call_status: str | None = "active",
    already_armed: bool = False,
    allowed_reasons: frozenset[str] | None = None,
    barge_in_flight: bool = False,
    last_stt_partial_at: float | None = None,
    now: float | None = None,
    completed_turns: int = 0,
    memory_snapshot: dict[str, Any] | None = None,
    call_end_policy: dict[str, Any] | None = None,
    spoken_text: str = "",
) -> EndCallDecision:
    parsed = parse_end_call_payload(raw)
    user = user_text or ""
    spoken = spoken_text or ""
    lang = normalize_compile_language(language)

    # Don't-call / goodbye always wins over a wrong model reason (e.g. goal_complete).
    if _user_wants_hangup(user):
        parsed = _force_end("goodbye", parsed.get("farewell") or "", spoken, lang)
    elif caller_firm_refusal(user):
        parsed = _force_end("firm_refusal", parsed.get("farewell") or "", spoken, lang)
    elif caller_requested_callback(user):
        parsed = _force_end("goal_complete", parsed.get("farewell") or "", spoken, lang)
    elif parsed["should_end"] and _STAY_ON_LINE.search(user):
        logger.info("[END_CALL] rejected code=stay_on_line reason=%s", parsed.get("reason"))
        return EndCallDecision(False, False, "none", parsed.get("farewell") or "", "stay_on_line")
    elif (
        parsed["should_end"]
        and caller_wants_to_continue(user)
        and parsed.get("reason") in {"firm_refusal", "goal_complete"}
        and not caller_firm_refusal(user)
        and not caller_confirmed_goal_complete(user)
    ):
        logger.info("[END_CALL] rejected code=caller_engaged reason=%s", parsed.get("reason"))
        return EndCallDecision(False, False, "none", "", "caller_engaged")
    elif not parsed["should_end"]:
        # Repair missed end_call tool when the turn already closed the conversation.
        if caller_confirmed_goal_complete(user) and (
            agent_spoke_closing(spoken) or parsed.get("farewell")
        ):
            parsed = _force_end("goal_complete", parsed.get("farewell") or "", spoken, lang)
        elif agent_spoke_closing(spoken) and (
            memory_has_lead_handoff(memory_snapshot)
            or (user_short_close_ack(user) and completed_turns >= 1)
        ):
            parsed = _force_end("goal_complete", parsed.get("farewell") or "", spoken, lang)

    if not parsed["should_end"]:
        return EndCallDecision(False, False, "none", "", None)

    reason = parsed["reason"]
    farewell = parsed["farewell"] or spoken or default_farewell_for(lang)

    def _reject(code: str) -> EndCallDecision:
        logger.info("[END_CALL] rejected code=%s reason=%s lang=%s", code, reason, lang)
        return EndCallDecision(False, False, reason, farewell, code)

    if already_armed:
        return _reject("already_armed")
    if barge_in_flight:
        return _reject("barge_in_flight")
    if call_status and call_status != "active":
        return _reject("call_not_active")
    clock = now if now is not None else time.monotonic()
    if last_stt_partial_at and (clock - last_stt_partial_at) < 0.4:
        return _reject("caller_still_talking")
    if reason not in HANGUP_REASONS:
        return _reject("reason_invalid")
    allowed = allowed_reasons if allowed_reasons is not None else allowed_reasons_for(call_end_policy)
    if reason not in allowed:
        return _reject("policy_overlay")
    if not user.strip():
        return _reject("empty_user_turn")
    if looks_like_question(user) and reason != "abuse":
        if not (_OPT_OUT.search(user) or _CALLER_DONE.search(user)
                or caller_explicit_end_request(user) or caller_requested_callback(user)):
            return _reject("user_asked_question")
    if not _evidence_ok(
        reason,
        user,
        language=lang,
        completed_turns=completed_turns,
        memory_snapshot=memory_snapshot,
        spoken_text=spoken,
    ):
        return _reject("no_evidence")
    if len(farewell) > 240:
        return _reject("farewell_too_long")

    return EndCallDecision(True, True, reason, farewell, None)
