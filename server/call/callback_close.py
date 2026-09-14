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
    return match.group(0) if match else ""


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
    if phase == PHASE_CLOSING_ALLOWED:
        return (
            "[Internal] Caller already asked to be contacted later. Confirm the callback in one "
            "short sentence, thank them, say goodbye, and call end_call with should_end true "
            "and reason=goal_complete. Do not pitch or ask another question."
        )
    return None


def spoken_collect_instruction(field: str, language: str = "en-IN") -> str:
    """Instruction injected when the model pitches instead of collecting a field."""
    lang_key = "te" if (language or "").lower().startswith("te") else (
        "hi" if (language or "").lower().startswith("hi") else "en"
    )
    prompts = {
        "phone": {
            "en": "Acknowledge the callback request warmly, then ask only for the best phone number. Do not say goodbye.",
            "te": "Callback request ni warmly acknowledge chesi, best phone number మాత్రమే అడుగు. Goodbye చెప్పవద్దు.",
            "hi": "Callback request ko warmly acknowledge karke sirf best phone number poochho. Goodbye mat kaho.",
        },
        "name": {
            "en": "Say: Certainly, I can arrange that. May I have your name before I let you go?",
            "te": "Say: తప్పకుండా, callback arrange చేస్తాను. మీరు వెళ్లే ముందు మీ పేరు చెప్పగలరా?",
            "hi": "Say: Zaroor, main callback arrange kar deta hoon. Jaane se pehle aapka naam bata denge?",
        },
        "timing": {
            "en": "Acknowledge briefly, then ask only what day or time works best for the callback. Do not say goodbye.",
            "te": "Brief ga acknowledge chesi, callback కి ఏ రోజు లేదా సమయం బాగుంటుందో మాత్రమే అడుగు. Goodbye చెప్పవద్దు.",
            "hi": "Briefly acknowledge karke sirf callback ka din ya samay poochho. Goodbye mat kaho.",
        },
    }
    return prompts.get(field, prompts["name"])[lang_key]


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
    from server.call.end_call_validate import (
        caller_asked_to_record_details,
        caller_requested_callback,
        memory_with_live_lead,
        _lead_name_and_phone,
    )

    extra = {k: str(v).strip() for k, v in (extra_slots or {}).items() if str(v).strip()}
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
