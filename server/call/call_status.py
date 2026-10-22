"""Canonical call status — one status vocabulary for every consumer.

The console, callbacks, analytics and campaigns all filter on ``status`` instead of
re-deriving "was this missed?" from raw columns. The value is computed from fields
the platform already records (``direction``, ``duration_sec``, ``end_reason``,
``disposition``) and is materialised on the ``calls`` / ``call_attempts`` rows so it
can be indexed and filtered in SQL. Rows written before the column existed fall back
to this same pure classifier, so historical data behaves identically.

``in_progress`` is part of the canonical set because a ringing call is a real,
observable state that none of the terminal statuses can express; without it every
open call would be misreported as "missed".
"""
from __future__ import annotations

from typing import Any, Final

STATUS_IN_PROGRESS: Final = "in_progress"
STATUS_ANSWERED: Final = "answered"
STATUS_MISSED: Final = "missed"
STATUS_OUTBOUND: Final = "outbound"
STATUS_DECLINED: Final = "declined"
STATUS_FAILED: Final = "failed"
STATUS_VOICEMAIL: Final = "voicemail"

#: Ordered so the first entry is the sensible default filter for "recent activity".
CALL_STATUSES: Final[tuple[str, ...]] = (
    STATUS_ANSWERED,
    STATUS_MISSED,
    STATUS_OUTBOUND,
    STATUS_DECLINED,
    STATUS_FAILED,
    STATUS_VOICEMAIL,
    STATUS_IN_PROGRESS,
)

TERMINAL_CALL_STATUSES: Final[frozenset[str]] = frozenset(CALL_STATUSES) - {STATUS_IN_PROGRESS}

#: An inbound call this short, with no transcript, is a hang-up — not a conversation.
MISSED_DURATION_SECONDS: Final = 5

# Tokens are matched against the values the platform already writes:
#  * server/call/call_lifecycle_service.py :: END_REASONS  (pstn_hangup, user_stop, …)
#  * server/services/outbound_dial_guard.py  :: carrier statuses (busy, no-answer, …)
#  * server/call/call_controller.py           :: action reasons (voicemail, transfer, …)
_VOICEMAIL_TOKENS: Final = (
    "voicemail",
    "answering_machine",
    "answering machine",
    "after_hours",
    "after-hours",
)
_NO_ANSWER_TOKENS: Final = (
    "no_answer",
    "no-answer",
    "noanswer",
    "unanswered",
    "not_answered",
    "no_response",
    "noresponse",
    "timeout",
    "timed_out",
    "ring_timeout",
    "outbound_ring",
)
_DECLINED_TOKENS: Final = (
    "busy",
    "rejected",
    "declined",
    "cancelled",
    "canceled",
    "refused",
)
_FAILED_TOKENS: Final = (
    "failed",
    "failure",
    "error",
    "unavailable",
    "unreachable",
    "carrier",
    "provider_failure",
    "runtime_failure",
    "stale_recovery",
    "superseded",
    "stream_error",
    "stream-error",
)


def _tokens(*values: Any) -> str:
    parts: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip().lower()
        if text:
            parts.append(text)
    return " ".join(parts)


def _matches(haystack: str, needles: tuple[str, ...]) -> bool:
    return any(token in haystack for token in needles)


def is_valid_call_status(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower() in CALL_STATUSES


def normalize_call_statuses(value: Any) -> list[str]:
    """Accept a comma separated string or an iterable; keep only known statuses."""
    if value is None:
        return []
    raw: list[Any]
    if isinstance(value, str):
        raw = [part for part in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        raw = list(value)
    else:
        return []
    out: list[str] = []
    for item in raw:
        token = str(item or "").strip().lower()
        if token and token in CALL_STATUSES and token not in out:
            out.append(token)
    return out


def classify_call_status(
    *,
    direction: Any = None,
    duration_sec: Any = None,
    end_reason: Any = None,
    disposition: Any = None,
    in_progress: bool = False,
) -> str:
    """Map a call's recorded fields onto one canonical status.

    Pure and side-effect free: safe to call on the write path, on reads of legacy
    rows, and in tests without any fixtures.
    """
    haystack = _tokens(end_reason, disposition)

    if _matches(haystack, _VOICEMAIL_TOKENS):
        return STATUS_VOICEMAIL
    if _matches(haystack, _NO_ANSWER_TOKENS):
        return STATUS_MISSED
    if _matches(haystack, _DECLINED_TOKENS):
        return STATUS_DECLINED

    try:
        duration = int(duration_sec) if duration_sec is not None else 0
    except (TypeError, ValueError):
        duration = 0
    duration = max(0, duration)

    if in_progress:
        return STATUS_IN_PROGRESS

    if _matches(haystack, _FAILED_TOKENS):
        # A carrier fault that happened after a real conversation is still a call
        # that was answered; only pre-answer faults are "failed".
        return STATUS_FAILED if duration < MISSED_DURATION_SECONDS else STATUS_ANSWERED

    if str(direction or "").strip().lower() == "outbound":
        return STATUS_OUTBOUND

    if duration < MISSED_DURATION_SECONDS:
        return STATUS_MISSED

    return STATUS_ANSWERED


def status_for_record(record: dict[str, Any]) -> str:
    """Classify a call/attempt dict, preferring an already-materialised status."""
    stored = record.get("status")
    if is_valid_call_status(stored):
        return str(stored).strip().lower()
    return classify_call_status(
        direction=record.get("direction"),
        duration_sec=record.get("duration_sec"),
        end_reason=record.get("end_reason") or record.get("hangup_reason"),
        disposition=record.get("disposition"),
        in_progress=not bool(record.get("ended_at")),
    )


def is_in_progress_record(record: dict[str, Any]) -> bool:
    return not bool(record.get("ended_at"))


def status_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    """Counts per canonical status, always including every status as a key."""
    counts = {status: 0 for status in CALL_STATUSES}
    for record in records:
        counts[status_for_record(record)] = counts.get(status_for_record(record), 0) + 1
    return counts
