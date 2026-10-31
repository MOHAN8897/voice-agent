"""Server-owned callback / lead-close phases.

The model speaks; this machine decides whether hangup is allowed yet.
Works with CallContext when present, or as a pure function of the latest
utterance + extra slots (Realtime tests often have no CallContext).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

PHASE_IDLE = "idle"
PHASE_CALLBACK_REQUESTED = "callback_requested"
PHASE_COLLECTING_NAME = "collecting_name"
PHASE_COLLECTING_PHONE = "collecting_phone"
PHASE_CLOSING_ALLOWED = "closing_allowed"
PHASE_HANGUP_EXECUTED = "hangup_executed"

COLLECTING_PHASES = frozenset({PHASE_COLLECTING_NAME, PHASE_COLLECTING_PHONE})

_TIMING_RE = re.compile(
    r"\b(tomorrow|today|tonight|morning|afternoon|evening|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"at\s+\d{1,2}(?::\d{2})?)\b",
    re.I,
)


@dataclass(frozen=True)
class CallbackCloseState:
    phase: str
    name: str = ""
    phone: str = ""
    when: str = ""
    missing: str | None = None
    hint: str | None = None


def extract_callback_when(*texts: str) -> str:
    blob = " ".join(t for t in texts if t)
    match = _TIMING_RE.search(blob)
    if match:
        return match.group(0)
    from server.call.callback_day_parts import detect, has_explicit_clock

    # Day parts and clock times in every script ("రేపు ఈవెనింగ్", "शाम 5 बजे").
    for text in reversed([t for t in texts if t]):
        if detect(text) or has_explicit_clock(text):
            return text.strip()[:120]
    return ""


def hint_for_phase(phase: str, missing: str | None = None) -> str | None:
    if phase == PHASE_COLLECTING_NAME or missing == "name":
        return (
            "[Internal] Caller asked you to record their details and contact them later. "
            "Acknowledge briefly, ask ONLY for their name, then wait. Do not pitch. Do not say goodbye yet."
        )
    if phase == PHASE_COLLECTING_PHONE or missing == "phone":
        return (
            "[Internal] Caller asked you to record their details and contact them later. "
            "Acknowledge briefly, ask ONLY for the best phone number, then wait. Do not pitch. Do not say goodbye yet."
        )
    if missing == "timing":
        return (
            "[Internal] Caller wants a call later but gave no time. In a few words acknowledge, then ask "
            "only when to call them, as one question. Do not ask them to call or tell you later, do not "
            "pitch, and do not close or say goodbye yet."
        )
    if phase == PHASE_CLOSING_ALLOWED:
        return (
            "[Internal] Caller already asked to be contacted later. Propose a close with "
            "reason=goal_complete so the platform can save the request and confirm it. "
            "Do not claim that a callback is arranged or saved before the platform confirms persistence. "
            "Never speak a farewell; the platform does on approval. Do not pitch or ask another question."
        )
    return None


def spoken_collect_instruction(field: str, language: str = "en-IN") -> str:
    """Instruction injected when the model pitches instead of collecting a field."""
    requested = {"phone": "the best phone number", "name": "the caller's name", "timing": "the preferred callback day or time"}.get(field, "the caller's name")
    return (f"In the selected call language ({language}), acknowledge the callback request and ask only for {requested}. "
        "Do not pitch or say goodbye. The request is pending: never say it is arranged, saved or scheduled before platform confirmation.")


def callback_time_reply(ctx: Any, control: Any, spoken: str, language: str) -> str | None:
    """The reply for a busy or call-me-later turn that still has no time.

    The order is fixed for every language: a short acknowledgement, then one
    question asking when to call; the callback is saved and the call closed only
    after the answer. Model wording such as "tell me when you are free and I'll
    note it" is replaced (call 35002575 issue 8). The decision is structural: the
    turn classifier's verified callback intent and its empty time, not phrases.
    Returns None when the turn is not a callback still missing its time.
    """
    from server.call.call_end_policy import callback_time_question_for, callback_time_reply_for

    if not isinstance(control, dict):
        return None
    held = control.get("callback_time_needed") is True
    requested_now = (
        control.get("contact_intent") == "callback" and control.get("contact_verified") is True
        and control.get("decision") != "close"
        and not str(control.get("callback_time") or "").strip() and not control.get("agent_asked_time")
        and ctx is not None and not str(getattr(ctx, "callback_when", "") or "").strip()
        and not getattr(ctx, "callback_time_prompted", False)
    )
    if not held and not requested_now:
        return None
    if ctx is not None:
        ctx.callback_time_prompted = True
    text = (spoken or "").strip()
    if str(control.get("remaining_request") or "").strip() and text:
        # The caller also asked something: keep that answer and add the one question.
        return text if "?" in text else f"{text} {callback_time_question_for(language)}"
    return callback_time_reply_for(language)


def _persist(ctx: Any, state: CallbackCloseState) -> None:
    if ctx is None:
        return
    ctx.callback_close_phase = state.phase
    ctx.callback_name = state.name
    ctx.callback_phone = state.phone
    ctx.callback_when = state.when
    if state.phase != PHASE_IDLE and not ctx.callback_request_text and state.hint:
        pass


def mark_hangup_executed(call_id: str | None) -> None:
    if not call_id:
        return
    from server.call import call_context

    ctx = call_context.get(call_id)
    if ctx is None:
        return
    ctx.callback_close_phase = PHASE_HANGUP_EXECUTED


def advance_callback_close(
    ctx: Any | None,
    user_text: str,
    memory_snapshot: dict[str, Any] | None = None,
    *,
    extra_slots: dict[str, str] | None = None,
    request_text: str = "",
) -> CallbackCloseState:
    """Advance (or derive) the callback close phase for this utterance."""
    from server.call.caller_intent import caller_revoked_callback
    from server.call.end_call_validate import (
        caller_asked_to_record_details,
        caller_requested_hangup,
        caller_firm_refusal,
        caller_requested_callback,
        memory_with_live_lead,
        _lead_name_and_phone,
    )

    extra = {k: str(v).strip() for k, v in (extra_slots or {}).items() if str(v).strip()}
    if caller_revoked_callback(user_text):
        # "I am not asking you to call me later" cancels the intent. A stale
        # callback phase must not outlive the caller's correction.
        if ctx is not None:
            ctx.callback_request_text = ""
        state = CallbackCloseState(PHASE_IDLE)
        _persist(ctx, state)
        return state
    if caller_requested_hangup(user_text) or caller_firm_refusal(user_text):
        if ctx is not None:
            ctx.callback_request_text = ""
        state = CallbackCloseState(PHASE_IDLE)
        _persist(ctx, state)
        return state
    prev_phase = str(getattr(ctx, "callback_close_phase", "") or PHASE_IDLE)
    if prev_phase == PHASE_HANGUP_EXECUTED:
        name = str(getattr(ctx, "callback_name", "") or extra.get("name") or "")
        phone = str(getattr(ctx, "callback_phone", "") or extra.get("phone") or "")
        when = str(getattr(ctx, "callback_when", "") or extra.get("timing") or extra.get("when") or "")
        return CallbackCloseState(PHASE_HANGUP_EXECUTED, name, phone, when, None, None)

    intent = (request_text or str(getattr(ctx, "callback_request_text", "") or "")).strip()
    if caller_requested_callback(user_text):
        intent = (user_text or "").strip()
        if ctx is not None:
            ctx.callback_request_text = intent

    in_flow = bool(intent) and (
        caller_requested_callback(intent) or prev_phase not in {PHASE_IDLE, ""}
    )
    if not in_flow:
        state = CallbackCloseState(PHASE_IDLE)
        _persist(ctx, state)
        return state

    snap = memory_with_live_lead(memory_snapshot, user_text or intent)
    extracted_name, extracted_phone = _lead_name_and_phone(user_text or intent, snap)
    name = (
        extra.get("name")
        or extracted_name
        or str(getattr(ctx, "callback_name", "") or "")
    ).strip()
    phone = (
        extra.get("phone")
        or extra.get("callback_phone")
        or extracted_phone
        or str(getattr(ctx, "callback_phone", "") or "")
    ).strip()
    when = (
        extra.get("timing")
        or extra.get("when")
        or extract_callback_when(intent, user_text)
        or str(getattr(ctx, "callback_when", "") or "")
    ).strip()

    if caller_asked_to_record_details(intent):
        if not name:
            phase, missing = PHASE_COLLECTING_NAME, "name"
        elif not phone:
            phase, missing = PHASE_COLLECTING_PHONE, "phone"
        else:
            phase, missing = PHASE_CLOSING_ALLOWED, None
    else:
        phase, missing = PHASE_CLOSING_ALLOWED, None
    if phase == PHASE_CLOSING_ALLOWED and not when and ctx is not None and not getattr(ctx, "callback_time_prompted", False):
        # Busy / call-me-later: acknowledge, ask the time once, then save and close.
        ctx.callback_time_prompted = True
        missing = "timing"

    state = CallbackCloseState(
        phase=phase,
        name=name,
        phone=phone,
        when=when,
        missing=missing,
        hint=hint_for_phase(phase, missing),
    )
    _persist(ctx, state)
    return state
