"""Server-side hangup gate — LLM may propose end_call; this decides."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from server.call.call_end_policy import HANGUP_REASONS as POLICY_REASONS, allowed_reasons_for
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
    r"mat karo|no interest)\b|"
    r"\b(vaddu|ledu)\b.{0,48}interest|interest.{0,24}\b(vaddu|ledu)\b|"
    r"interest\s*లేదు|"
    r"(?:వద్దు.{0,48}(?:interest|call)|(?:interest|call).{0,24}వద్దు)",
    re.I | re.S,
)
_ABUSE = re.compile(
    r"\b(kill you|rape|bomb|terrorist)\b",
    re.I,
)
_GOAL_DONE = re.compile(
    r"\b(booked|scheduled|ticket[_ ]?id|order[_ ]?id|confirmed slot|visit booked)\b",
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
    r"^\s*(?:thanks|thank you)[,.]?\s+that'?s (?:all|it)\s*[.!]?\s*$|"
    r"^\s*that'?s (?:all|it)(?:[,.]?\s*(?:thanks|thank you))?\s*[.!]?\s*$",
    re.I,
)
_GOAL_COMPLETE_USER = re.compile(
    r"\b(that answers (?:it|my question)|that(?:'s| is) (?:sorted|resolved)|"
    r"i (?:have|got) (?:the|my) answer|i know .{1,40} now|"
    r"that is all i needed|that(?:'s| is) what i needed)\b",
    re.I,
)
_OPT_OUT = re.compile(
    r"don't call|do not call|stop calling|keep calling|stop the calls|never (?:call|contact)|please stop calling",
    re.I,
)


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
) -> bool:
    text = user_text or ""
    if reason == "goodbye":
        return bool(_GOODBYE.search(text) or _CALLER_DONE.search(text))
    if reason == "firm_refusal":
        # Need a prior turn so we already stopped pushing (not first-pitch hangup).
        return bool(_REFUSAL.search(text)) and completed_turns >= 1
    if reason == "abuse":
        return bool(_ABUSE.search(text))
    if reason == "goal_complete":
        if looks_like_question(text):
            return False
        return bool(_GOAL_COMPLETE_USER.search(text)) or memory_has_goal_complete(memory_snapshot)
    if reason == "out_of_scope":
        # Agent must have had one chance to redirect.
        return bool(text.strip()) and not looks_like_question(text) and completed_turns >= 1
    return False


def _user_wants_hangup(user_text: str) -> bool:
    text = user_text or ""
    if _OPT_OUT.search(text) or _CALLER_DONE.search(text):
        return True
    if looks_like_question(text):
        return False
    return bool(_GOODBYE.search(text))


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
) -> EndCallDecision:
    parsed = parse_end_call_payload(raw)
    user = user_text or ""
    # Don't-call / goodbye always wins over a wrong model reason (e.g. goal_complete).
    if _user_wants_hangup(user):
        parsed = {
            "should_end": True,
            "reason": "goodbye",
            "farewell": parsed.get("farewell") or "",
        }
    elif parsed["should_end"] and _STAY_ON_LINE.search(user):
        logger.info("[END_CALL] rejected code=stay_on_line reason=%s", parsed.get("reason"))
        return EndCallDecision(False, False, "none", parsed.get("farewell") or "", "stay_on_line")
    if not parsed["should_end"]:
        return EndCallDecision(False, False, "none", "", None)

    reason = parsed["reason"]
    farewell = parsed["farewell"]
    lang = normalize_compile_language(language)

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
        if not (_OPT_OUT.search(user) or _CALLER_DONE.search(user)):
            return _reject("user_asked_question")
    if not _evidence_ok(
        reason,
        user,
        language=lang,
        completed_turns=completed_turns,
        memory_snapshot=memory_snapshot,
    ):
        return _reject("no_evidence")
    if len(farewell) > 240:
        return _reject("farewell_too_long")

    return EndCallDecision(True, True, reason, farewell, None)
