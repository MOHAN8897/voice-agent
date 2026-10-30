"""Carrier hangup causes -> canonical call status and plain-words reason.

Vobiz (https://www.vobiz.ai/docs/cdr) reports ``hangup_cause`` values such as
``NO_ANSWER``, ``USER_BUSY``, ``CALL_REJECTED``, ``ORIGINATOR_CANCEL`` and
``UNALLOCATED_NUMBER``; Plivo-style accounts also send human names like
"Busy Line" or "No Answer". Telnyx sends lower-case causes such as
``user_busy``, ``timeout`` or ``call_rejected``. Every value is normalised to an
upper-snake token, then mapped onto:

* a canonical status (``server/call/call_status.py``), and
* a short ``end_reason`` token (<= 50 chars, stored on ``call_attempts``).

``outcome_for_item`` turns a timeline row into the owner-facing label
("No answer", "Busy", "Declined", "Failed", "Missed call", "Voicemail") and one
sentence explaining why, so the console never has to decode carrier jargon.
Pure functions only: safe on webhook paths and in tests.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Final

from server.call.call_status import (
    STATUS_ANSWERED,
    STATUS_DECLINED,
    STATUS_FAILED,
    STATUS_MISSED,
    STATUS_OUTBOUND,
    STATUS_VOICEMAIL,
)

# end_reason tokens written by this module. They also match the token lists in
# call_status.py so legacy re-classification agrees with the stored status.
REASON_NO_ANSWER: Final = "no_answer"
REASON_BUSY: Final = "busy"
REASON_REJECTED: Final = "rejected"
REASON_CALLER_CANCELLED: Final = "caller_cancelled_no_answer"
REASON_INVALID_NUMBER: Final = "invalid_number_failed"
REASON_UNREACHABLE: Final = "unreachable"
REASON_NETWORK: Final = "carrier_failure"
REASON_DIAL_FAILED: Final = "dial_failed"
REASON_NOT_CONNECTED: Final = "agent_not_connected_failed"
REASON_VOICEMAIL: Final = "voicemail"
REASON_NORMAL: Final = "normal_clearing"

#: Normalised carrier cause -> end_reason token.
_CAUSE_TO_REASON: Final[dict[str, str]] = {
    # Nobody picked up.
    "NO_ANSWER": REASON_NO_ANSWER,
    "NO_USER_RESPONSE": REASON_NO_ANSWER,
    "TIMEOUT": REASON_NO_ANSWER,
    "RING_TIMEOUT": REASON_NO_ANSWER,
    "ALLOTTED_TIMEOUT": REASON_NO_ANSWER,
    "RECOVERY_ON_TIMER_EXPIRE": REASON_NO_ANSWER,
    # Busy.
    "USER_BUSY": REASON_BUSY,
    "BUSY": REASON_BUSY,
    "BUSY_LINE": REASON_BUSY,
    # Declined by the person or their phone.
    "CALL_REJECTED": REASON_REJECTED,
    "REJECTED": REASON_REJECTED,
    "DECLINED": REASON_REJECTED,
    # Caller hung up while it was still ringing.
    "ORIGINATOR_CANCEL": REASON_CALLER_CANCELLED,
    "CANCELLED": REASON_CALLER_CANCELLED,
    "CANCELED": REASON_CALLER_CANCELLED,
    "CANCEL": REASON_CALLER_CANCELLED,
    # The number itself is bad: never retry.
    "INVALID_NUMBER": REASON_INVALID_NUMBER,
    "INVALID_NUMBER_FORMAT": REASON_INVALID_NUMBER,
    "UNALLOCATED_NUMBER": REASON_INVALID_NUMBER,
    "NO_ROUTE_DESTINATION": REASON_INVALID_NUMBER,
    "NUMBER_CHANGED": REASON_INVALID_NUMBER,
    # Switched off / out of coverage.
    "DESTINATION_OUT_OF_ORDER": REASON_UNREACHABLE,
    "SUBSCRIBER_ABSENT": REASON_UNREACHABLE,
    "UNREACHABLE": REASON_UNREACHABLE,
    # Network / platform faults.
    "SERVICE_UNAVAILABLE": REASON_NETWORK,
    "SERVER_ERROR": REASON_NETWORK,
    "MEDIA_TIMEOUT": REASON_NETWORK,
    "PROTOCOL_ERROR": REASON_NETWORK,
    "NETWORK_OUT_OF_ORDER": REASON_NETWORK,
    "NORMAL_TEMPORARY_FAILURE": REASON_NETWORK,
    "SWITCH_CONGESTION": REASON_NETWORK,
    "UNKNOWN": REASON_NETWORK,
    "UNSPECIFIED": REASON_NETWORK,
    "FAILED": REASON_NETWORK,
    # Voicemail / answering machine.
    "MACHINE_DETECTED": REASON_VOICEMAIL,
    "VOICEMAIL": REASON_VOICEMAIL,
    # Ordinary hangup: the outcome depends on whether anyone answered.
    "NORMAL_CLEARING": REASON_NORMAL,
    "NORMAL_HANGUP": REASON_NORMAL,
    "NORMAL": REASON_NORMAL,
    "HANGUP": REASON_NORMAL,
    "COMPLETED": REASON_NORMAL,
    "END_OF_XML_INSTRUCTIONS": REASON_NORMAL,
}

#: SIP response code -> end_reason, used when no named cause is sent.
_SIP_TO_REASON: Final[dict[int, str]] = {
    404: REASON_INVALID_NUMBER,
    410: REASON_INVALID_NUMBER,
    484: REASON_INVALID_NUMBER,
    480: REASON_UNREACHABLE,
    486: REASON_BUSY,
    600: REASON_BUSY,
    603: REASON_REJECTED,
    408: REASON_NO_ANSWER,
    487: REASON_CALLER_CANCELLED,
    500: REASON_NETWORK,
    502: REASON_NETWORK,
    503: REASON_NETWORK,
}

_REASON_TO_STATUS: Final[dict[str, str]] = {
    REASON_NO_ANSWER: STATUS_MISSED,
    REASON_CALLER_CANCELLED: STATUS_MISSED,
    REASON_BUSY: STATUS_DECLINED,
    REASON_REJECTED: STATUS_DECLINED,
    REASON_INVALID_NUMBER: STATUS_FAILED,
    REASON_UNREACHABLE: STATUS_FAILED,
    REASON_NETWORK: STATUS_FAILED,
    REASON_DIAL_FAILED: STATUS_FAILED,
    REASON_NOT_CONNECTED: STATUS_FAILED,
    REASON_VOICEMAIL: STATUS_VOICEMAIL,
}

#: Reasons after which an automatic recall must never be attempted.
NON_RETRYABLE_REASONS: Final[frozenset[str]] = frozenset({REASON_INVALID_NUMBER})


def normalize_cause(value: Any) -> str:
    """'Busy Line' / 'user_busy' / 'USER-BUSY' -> 'USER_BUSY'-style token."""
    text = str(value or "").strip()
    if not text:
        return ""
    return re.sub(r"[^A-Z0-9]+", "_", text.upper()).strip("_")


def reason_for_cause(cause: Any, sip_code: Any = None) -> str | None:
    token = normalize_cause(cause)
    if token in _CAUSE_TO_REASON:
        return _CAUSE_TO_REASON[token]
    # Partial matches for verbose names ("Rejected By Callee", "No Answer Timeout").
    for needle, reason in (
        ("NO_ANSWER", REASON_NO_ANSWER), ("BUSY", REASON_BUSY), ("REJECT", REASON_REJECTED),
        ("DECLIN", REASON_REJECTED), ("CANCEL", REASON_CALLER_CANCELLED), ("UNALLOCATED", REASON_INVALID_NUMBER),
        ("INVALID", REASON_INVALID_NUMBER), ("MACHINE", REASON_VOICEMAIL), ("VOICEMAIL", REASON_VOICEMAIL),
        ("TIMEOUT", REASON_NO_ANSWER),
    ):
        if needle in token:
            return reason
    try:
        code = int(str(sip_code).strip()) if sip_code not in (None, "") else None
    except (TypeError, ValueError):
        code = None
    if code is not None and code in _SIP_TO_REASON:
        return _SIP_TO_REASON[code]
    return None


@dataclass(frozen=True)
class HangupOutcome:
    status: str
    end_reason: str
    retryable: bool


def classify_hangup(
    cause: Any,
    *,
    direction: str,
    answered: bool,
    connected: bool,
    sip_code: Any = None,
) -> HangupOutcome:
    """Map one carrier hangup onto a canonical status for an attempt row.

    ``answered``: the carrier reported an answer (AnswerTime / billsec / answered event).
    ``connected``: the agent actually spoke (a ``calls`` row exists for it).
    """
    reason = reason_for_cause(cause, sip_code)
    outbound = str(direction or "").lower() == "outbound"
    if connected:
        return HangupOutcome(STATUS_OUTBOUND if outbound else STATUS_ANSWERED, reason or REASON_NORMAL, False)
    if reason in (None, REASON_NORMAL):
        if answered:
            # Answered by the network but the agent never got on the line.
            reason = REASON_NOT_CONNECTED if outbound else REASON_CALLER_CANCELLED
        else:
            # A "normal" hangup with no answer is the ring timing out (outbound) or
            # the caller giving up before the agent picked up (inbound).
            reason = REASON_NO_ANSWER if outbound else REASON_CALLER_CANCELLED
    status = _REASON_TO_STATUS.get(reason, STATUS_FAILED)
    return HangupOutcome(status, reason, reason not in NON_RETRYABLE_REASONS)


# ---------------------------------------------------------------------------
# Owner-facing wording
# ---------------------------------------------------------------------------

_REASON_TEXT_OUTBOUND: Final[dict[str, str]] = {
    REASON_NO_ANSWER: "They didn't pick up before the ringing stopped.",
    REASON_BUSY: "Their line was busy.",
    REASON_REJECTED: "They declined the call.",
    REASON_CALLER_CANCELLED: "The call was cancelled before they answered.",
    REASON_INVALID_NUMBER: "This number isn't valid or isn't in service.",
    REASON_UNREACHABLE: "Their phone was switched off or out of coverage.",
    REASON_NETWORK: "The phone network couldn't connect the call.",
    REASON_DIAL_FAILED: "The call couldn't be placed.",
    REASON_NOT_CONNECTED: "They answered, but the agent couldn't join the call.",
    REASON_VOICEMAIL: "The call went to voicemail.",
}
_REASON_TEXT_INBOUND: Final[dict[str, str]] = {
    REASON_NO_ANSWER: "Nobody answered before the caller hung up.",
    REASON_CALLER_CANCELLED: "The caller hung up before the agent answered.",
    REASON_BUSY: "The line was busy.",
    REASON_REJECTED: "The call was declined.",
    REASON_NETWORK: "The phone network dropped the call before it connected.",
    REASON_UNREACHABLE: "The phone network dropped the call before it connected.",
    REASON_NOT_CONNECTED: "The agent couldn't join the call.",
    REASON_VOICEMAIL: "The caller reached voicemail.",
}
_POLICY_TEXT: Final[dict[str, str]] = {
    "after_hours_voicemail": "It came in outside working hours and went to voicemail.",
    "after_hours_hangup": "It came in outside working hours, so it wasn't answered.",
    "inbound_disabled": "Incoming calls are switched off for this number.",
    "number_disabled": "Incoming calls are switched off for this number.",
    "insufficient_balance": "Your wallet balance was too low to answer.",
    "tenant_quarantined": "The account was paused, so the call wasn't answered.",
}


def _reason_key(end_reason: Any) -> str:
    raw = str(end_reason or "").strip().lower()
    if not raw:
        return ""
    if raw in _REASON_TEXT_OUTBOUND or raw in _REASON_TEXT_INBOUND:
        return raw
    mapped = reason_for_cause(raw)
    return mapped or raw


def outcome_for_item(item: dict[str, Any]) -> dict[str, str | None]:
    """``{"outcome_label", "outcome_reason"}`` for a timeline row (call or attempt)."""
    status = str(item.get("status") or "").lower()
    outbound = str(item.get("direction") or "").lower() == "outbound"
    key = _reason_key(item.get("end_reason"))
    policy = str(item.get("policy_reason") or "").lower()
    if status == STATUS_MISSED:
        label = "No answer" if outbound else "Missed call"
    elif status == STATUS_DECLINED:
        label = "Busy" if key == REASON_BUSY else "Declined"
    elif status == STATUS_FAILED:
        label = "Invalid number" if key == REASON_INVALID_NUMBER else "Failed"
    elif status == STATUS_VOICEMAIL:
        label = "Voicemail"
    else:
        return {"outcome_label": None, "outcome_reason": None}
    reason: str | None = None
    if not outbound and policy in _POLICY_TEXT:
        reason = _POLICY_TEXT[policy]
    if reason is None:
        table = _REASON_TEXT_OUTBOUND if outbound else _REASON_TEXT_INBOUND
        reason = table.get(key)
    if reason is None:
        reason = {
            STATUS_MISSED: "They didn't pick up." if outbound else "Nobody answered this call.",
            STATUS_DECLINED: "The line was busy or the call was declined.",
            STATUS_FAILED: "The call couldn't be connected.",
            STATUS_VOICEMAIL: "The call went to voicemail.",
        }[status]
    return {"outcome_label": label, "outcome_reason": reason}
