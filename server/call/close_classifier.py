"""One tiny close-decision step for turns whose reply carries no close signal.

Plain-speech providers (Sarvam) deliver the caller-facing words only, so the
spoken reply can never carry an ``end_call``. This step asks the same pinned
model one narrow question — continue, clarify or close — and returns only a
label, a one-word reason and an exact quote. It never speaks, never writes
memory, and fails open so a classifier outage keeps the call connected.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from server.call.close_decision import evidence_matches
from server.providers.base import StageSelection
from server.utils.logger import log_pstn

#: Hard cap on the classifier request; the caller never waits for it alone.
CLASSIFIER_TIMEOUT_SEC = 4.0
#: How long a completed reply may wait for an unfinished decision before the
#: turn continues without one. The call stays open, never unclassified-closed.
CLASSIFIER_MERGE_TIMEOUT_SEC = 2.0
#: Long turns are requests/questions, not endings. This only saves a call; the
#: model still makes the decision for every turn that reaches it.
_MAX_TURN_WORDS = 16

_REASON_MAP = {
    "done": "goal_complete",
    "finished": "goal_complete",
    "complete": "goal_complete",
    "completed": "goal_complete",
    "goal_complete": "goal_complete",
    "satisfied": "goal_complete",
    "all_good": "goal_complete",
    "all_set": "goal_complete",
    "resolved": "goal_complete",
    "goodbye": "goodbye",
    "bye": "goodbye",
    "closed": "goodbye",
    "ended": "goodbye",
    "ending": "goodbye",
    "farewell": "goodbye",
    "thanks": "goodbye",
    "thank_you": "goodbye",
    "refused": "not_interested",
    "refusal": "not_interested",
    "not_interested": "not_interested",
    "stop_contact": "firm_refusal",
    "opt_out": "firm_refusal",
    "optout": "firm_refusal",
    "firm_refusal": "firm_refusal",
    "abuse": "abuse",
}

_SYSTEM = """You are the close detector for a live phone call. You do not speak.
Decide only whether the caller's last turn ends this call based on the caller's words and the agent's previous turn.

Allowed decisions:
- "close": the caller clearly signals the conversation is finished: nothing more is needed, satisfied with all information, a goodbye, a refusal, or a request to stop contact.
- "clarify": the turn is unintelligible or ambiguous; the agent should ask one short question.
- "continue": every other case. A question, a request for details, interest, a deferral ("not now", "call me later"), or a bare thanks/okay in the middle of a call that does not say the conversation is over.

Rules:
- Judge meaning in any language, dialect, or mixed script (e.g., Telugu, Hindi, English, Tamil, Kannada, Marathi, Bengali, etc.). Never rely on a fixed phrase list.
- Evaluate the caller's words in context of the agent's previous statement:
  * An ending expression like "that's all, thank you", "that's all I needed", "సరే ఓకే థాంక్స్" (Alright okay thanks), "అంతే అంతే థ్యాంక్ యూ" (That is all, thank you), "बस इतना ही धन्यवाद", "அவ்வளவுதான் நன்றி" signals completion -> "close".
  * Refusals like "not interested", "వద్దు", "नहीं चाहिए" -> "close".
  * Polite thanks alone in the middle of a call (e.g. agent answered price/location, caller says "thanks") is NOT an ending -> "continue".
  * Questions or asking for more (e.g. "thanks, but one more question", "what is the price?") -> "continue".
  * If the caller still wants or asks anything at all -> "continue".
- "evidence" must be a short quote copied from the caller's last turn.

Return one JSON object only:
{"decision":"continue|clarify|close","reason":"done|goodbye|refused|stop_contact|abuse|unclear|question|wants_more|none","evidence":"exact caller words"}"""


def close_turn_plausible(transcript: str) -> bool:
    """Cheap, phrase-free prefilter: only short non-question turns can end a call."""
    text = (transcript or "").strip()
    if not text or "?" in text:
        return False
    return len(text.split()) <= _MAX_TURN_WORDS


def previous_agent_line(session_id: str) -> str:
    """The last delivered agent turn, used to judge a bare thanks/okay in context."""
    from server.agent.conversation_manager import conversation_manager

    history = conversation_manager.get_context_for_brain(session_id, max_turns=1)
    for message in reversed(history):
        if message.get("role") != "assistant":
            continue
        text = str(message.get("content") or "").replace("[interrupted]", "").strip()
        if text:
            return text[-400:]
    return ""


def classifier_available(llm: StageSelection | None) -> bool:
    """True whenever an LLM adapter is available to classify plausible close turns."""
    if llm is None or not getattr(llm, "provider", None) or not getattr(llm, "model", None):
        return False
    try:
        from server.providers import get_provider_registry

        registry = get_provider_registry()
        if not registry.is_provider_enabled(llm.provider, "llm"):
            return False
        if not registry.is_model_allowed(llm.provider, "llm", llm.model):
            return False
        adapter = registry.get_llm(llm.provider)
        return adapter is not None
    except Exception:
        return False


def _json_object(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", raw).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(raw[start : end + 1])
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def parse_classifier_output(raw: Any, transcript: str) -> dict[str, Any] | None:
    """Keep only a grounded close; every other answer leaves the call open."""
    if not isinstance(raw, dict):
        return None
    if str(raw.get("decision") or "").strip().lower() != "close":
        return None
    raw_reason = str(raw.get("reason") or "").strip().lower()
    reason = _REASON_MAP.get(raw_reason)
    if reason is None:
        reason = (
            "goal_complete"
            if any(w in raw_reason for w in ("done", "finish", "complete", "satisf"))
            else "goodbye"
        )
    evidence = re.sub(r"\s+", " ", str(raw.get("evidence") or "")).strip()[:200]
    if not evidence and len(transcript.split()) <= _MAX_TURN_WORDS:
        evidence = transcript.strip()[:200]
    if not evidence_matches(evidence, transcript):
        # A paraphrase is not evidence; an invented close must never end a call.
        return None
    return {"decision": "close", "reason": reason, "evidence": evidence}


async def classify_close_turn(
    *,
    transcript: str,
    agent_previous: str,
    language: str,
    llm: StageSelection,
    call_id: str | None = None,
) -> dict[str, Any] | None:
    """Run the tiny decision step; any failure returns None (call continues)."""
    try:
        from server.providers import get_provider_registry

        registry = get_provider_registry()
        if (
            not registry.is_provider_enabled(llm.provider, "llm")
            or not registry.is_model_allowed(llm.provider, "llm", llm.model)
        ):
            return None
        adapter = registry.get_llm(llm.provider)
    except Exception:
        return None

    payload = json.dumps(
        {
            "language": language,
            "agent_previous": (agent_previous or "")[:400],
            "caller_last_turn": (transcript or "")[:400],
        },
        ensure_ascii=False,
    )
    output = ""
    usage: dict[str, Any] = {}
    try:
        async with asyncio.timeout(CLASSIFIER_TIMEOUT_SEC):
            async for event in adapter.stream_live_turn(
                model=llm.model,
                api_mode=(llm.config or {}).get("api_mode"),
                max_output_tokens=128,
                temperature=0,
                reasoning_effort=None,
                input_messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": payload},
                ],
            ):
                if event.get("done"):
                    output = str(event.get("text") or "").strip()
                    usage = event.get("usage") or {}
    except Exception as exc:
        log_pstn(
            "close.classifier.failed",
            call_id=call_id,
            provider=llm.provider,
            model=llm.model,
            error_type=type(exc).__name__,
        )
        return None

    proposal = parse_classifier_output(_json_object(output), transcript)
    log_pstn(
        "close.classifier",
        call_id=call_id,
        provider=llm.provider,
        model=llm.model,
        decision=(proposal or {}).get("decision", "continue"),
        reason=(proposal or {}).get("reason"),
        evidence_chars=len((proposal or {}).get("evidence", "")),
        output_tokens=int(usage.get("output_tokens") or 0),
    )
    return proposal


def start_close_classification(
    *,
    transcript: str,
    agent_previous: str,
    language: str,
    llm: StageSelection,
    call_id: str | None = None,
) -> asyncio.Task | None:
    """Begin the decision concurrently with the reply; None when not applicable."""
    if not close_turn_plausible(transcript) or not classifier_available(llm):
        return None
    return asyncio.create_task(
        classify_close_turn(
            transcript=transcript,
            agent_previous=agent_previous,
            language=language,
            llm=llm,
            call_id=call_id,
        ),
        name=f"close-classifier-{call_id or 'unknown'}",
    )


async def resolve_close_proposal(task: asyncio.Task | None, *, call_id: str | None = None) -> dict[str, Any] | None:
    """Take the decision if ready; a slow classifier never delays the reply."""
    if task is None:
        return None
    try:
        return await asyncio.wait_for(task, timeout=CLASSIFIER_MERGE_TIMEOUT_SEC)
    except Exception:
        if not task.done():
            task.cancel()
        log_pstn("close.classifier.skipped", call_id=call_id, reason="not_ready")
        return None
