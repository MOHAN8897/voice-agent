"""Canonical call status classification — the contract every consumer filters on."""
from __future__ import annotations

import pytest

from server.call.call_status import (
    CALL_STATUSES,
    MISSED_DURATION_SECONDS,
    STATUS_ANSWERED,
    STATUS_DECLINED,
    STATUS_FAILED,
    STATUS_IN_PROGRESS,
    STATUS_MISSED,
    STATUS_OUTBOUND,
    STATUS_VOICEMAIL,
    classify_call_status,
    normalize_call_statuses,
    status_for_record,
)


def test_status_vocabulary_is_stable():
    """The console, callbacks and analytics all filter on this exact set."""
    assert set(CALL_STATUSES) == {
        "answered",
        "missed",
        "outbound",
        "declined",
        "failed",
        "voicemail",
        "in_progress",
    }


@pytest.mark.parametrize(
    "reason,expected",
    [
        ("busy", STATUS_DECLINED),
        ("rejected", STATUS_DECLINED),
        ("declined", STATUS_DECLINED),
        ("cancelled", STATUS_DECLINED),
        ("no_answer", STATUS_MISSED),
        ("no-answer", STATUS_MISSED),
        ("unanswered", STATUS_MISSED),
        ("timeout", STATUS_MISSED),
        ("voicemail", STATUS_VOICEMAIL),
        ("answering_machine", STATUS_VOICEMAIL),
        ("after_hours", STATUS_VOICEMAIL),
    ],
)
def test_carrier_reason_wins_over_duration(reason, expected):
    """A busy signal must read as declined even after a long duration."""
    assert (
        classify_call_status(direction="inbound", duration_sec=300, end_reason=reason) == expected
    )


def test_inbound_short_call_is_missed():
    assert (
        classify_call_status(direction="inbound", duration_sec=MISSED_DURATION_SECONDS - 1)
        == STATUS_MISSED
    )


def test_inbound_conversation_is_answered():
    assert (
        classify_call_status(direction="inbound", duration_sec=MISSED_DURATION_SECONDS, end_reason="pstn_hangup")
        == STATUS_ANSWERED
    )


def test_completed_outbound_is_outbound():
    assert (
        classify_call_status(direction="outbound", duration_sec=120, end_reason="pstn_hangup")
        == STATUS_OUTBOUND
    )


def test_outbound_that_rang_out_is_missed_not_outbound():
    assert (
        classify_call_status(direction="outbound", duration_sec=0, end_reason="no_answer")
        == STATUS_MISSED
    )


def test_provider_fault_before_answer_is_failed():
    assert (
        classify_call_status(direction="outbound", duration_sec=0, end_reason="provider_failure")
        == STATUS_FAILED
    )


def test_provider_fault_after_a_real_call_still_counts_as_answered():
    """A carrier error 60s into a conversation did not stop the call happening."""
    assert (
        classify_call_status(direction="inbound", duration_sec=60, end_reason="provider_failure")
        == STATUS_ANSWERED
    )


def test_open_call_is_in_progress_never_missed():
    """A ringing call must not be reported as missed."""
    assert classify_call_status(direction="inbound", duration_sec=0, in_progress=True) == STATUS_IN_PROGRESS
    assert (
        classify_call_status(direction="inbound", duration_sec=42, in_progress=True) == STATUS_IN_PROGRESS
    )


def test_materialised_status_is_preferred_when_valid():
    assert (
        status_for_record(
            {"status": "voicemail", "direction": "inbound", "duration_sec": 99, "ended_at": "x"}
        )
        == STATUS_VOICEMAIL
    )


def test_legacy_row_without_status_is_derived():
    """Rows written before the status column must behave identically."""
    legacy = {
        "direction": "inbound",
        "duration_sec": 0,
        "end_reason": None,
        "ended_at": "2026-01-01T00:00:00+00:00",
    }
    assert status_for_record(legacy) == STATUS_MISSED


def test_open_legacy_row_is_in_progress():
    legacy = {"direction": "inbound", "duration_sec": 12, "ended_at": None}
    assert status_for_record(legacy) == STATUS_IN_PROGRESS


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("missed", ["missed"]),
        ("missed,voicemail", ["missed", "voicemail"]),
        (["missed", "missed", "nope"], ["missed"]),
        ("", []),
        (None, []),
        ("in_progress", ["in_progress"]),
    ],
)
def test_normalize_call_statuses(raw, expected):
    assert normalize_call_statuses(raw) == expected


def test_bad_duration_does_not_raise():
    assert classify_call_status(direction="inbound", duration_sec=None) == STATUS_MISSED
    assert classify_call_status(direction="inbound", duration_sec="oops") == STATUS_MISSED
