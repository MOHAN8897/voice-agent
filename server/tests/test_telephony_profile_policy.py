"""Inbound telephony policy: the decision the live PSTN path makes.

Covers the cases the rollout must get right — enabled, disabled, in hours, after
hours, timezone, greeting selection, and every fallback that keeps a live call
working when configuration is missing or malformed.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from server.services.saas.telephony_profile import (
    DEFAULT_TIMEZONE,
    ROUTE_AGENT,
    ROUTE_DECLINE,
    ROUTE_TRANSFER,
    ROUTE_VOICEMAIL,
    TelephonyProfileError,
    evaluate_inbound_policy,
    is_within_business_hours,
    normalize_after_hours_action,
    normalize_business_hours,
    normalize_greeting_phrase,
    normalize_timezone,
    normalize_transfer_number,
)

IST_10AM = datetime(2026, 3, 3, 4, 30, tzinfo=timezone.utc)  # Tuesday 10:00 IST
IST_11PM = datetime(2026, 3, 3, 17, 30, tzinfo=timezone.utc)  # Tuesday 23:00 IST


def profile(**overrides):
    base = {
        "agent_id": "agent-1",
        "greeting_phrase": None,
        "business_hours": {},
        "timezone": DEFAULT_TIMEZONE,
        "after_hours_action": "voicemail",
        "transfer_number": None,
        "inbound_enabled": True,
        "outbound_enabled": True,
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# Backward compatibility
# --------------------------------------------------------------------------


def test_missing_profile_falls_back_to_legacy_behaviour():
    """An agent with no profile must ring and answer exactly as it does today."""
    decision = evaluate_inbound_policy(None)
    assert decision.should_answer is True
    assert decision.route == ROUTE_AGENT
    assert decision.used_fallback is True
    assert decision.greeting_phrase is None


def test_profile_with_no_hours_always_answers():
    decision = evaluate_inbound_policy(profile(), at=IST_11PM)
    assert decision.should_answer is True
    assert decision.route == ROUTE_AGENT
    assert decision.after_hours is False


# --------------------------------------------------------------------------
# inbound_enabled
# --------------------------------------------------------------------------


def test_inbound_disabled_never_answers():
    decision = evaluate_inbound_policy(profile(inbound_enabled=False), at=IST_10AM)
    assert decision.should_answer is False
    assert decision.route == ROUTE_DECLINE
    assert decision.reason == "inbound_disabled"


def test_inbound_enabled_answers_in_hours():
    decision = evaluate_inbound_policy(profile(inbound_enabled=True), at=IST_10AM)
    assert decision.should_answer is True
    assert decision.route == ROUTE_AGENT


# --------------------------------------------------------------------------
# Business hours
# --------------------------------------------------------------------------

WEEKDAY_9_TO_6 = {"tue": [{"open": "09:00", "close": "18:00"}]}


def test_within_business_hours():
    assert is_within_business_hours(WEEKDAY_9_TO_6, tz_name=DEFAULT_TIMEZONE, at=IST_10AM) is True


def test_outside_business_hours():
    assert is_within_business_hours(WEEKDAY_9_TO_6, tz_name=DEFAULT_TIMEZONE, at=IST_11PM) is False


def test_weekday_without_windows_is_closed():
    hours = {"mon": [{"open": "09:00", "close": "18:00"}]}
    assert is_within_business_hours(hours, tz_name=DEFAULT_TIMEZONE, at=IST_10AM) is False


def test_no_business_hours_configured_is_always_open():
    assert is_within_business_hours({}, at=IST_11PM) is True
    assert is_within_business_hours(None, at=IST_11PM) is True


def test_closed_date_is_outside_hours():
    hours = {
        "tue": [{"open": "09:00", "close": "18:00"}],
        "closed": ["2026-03-03"],  # Tuesday
    }
    assert is_within_business_hours(hours, tz_name=DEFAULT_TIMEZONE, at=IST_10AM) is False


def test_closed_dates_only_leave_other_days_open():
    hours = normalize_business_hours({"closed": ["2026-12-25"]})
    assert hours["closed"] == ["2026-12-25"]
    assert is_within_business_hours(hours, tz_name=DEFAULT_TIMEZONE, at=IST_10AM) is True


def test_normalize_rejects_bad_closed_date():
    with pytest.raises(TelephonyProfileError):
        normalize_business_hours({"closed": ["25-12-2026"]})


def test_window_crossing_midnight():
    hours = {"tue": [{"open": "22:00", "close": "02:00"}]}
    assert is_within_business_hours(hours, tz_name=DEFAULT_TIMEZONE, at=IST_11PM) is True
    assert is_within_business_hours(hours, tz_name=DEFAULT_TIMEZONE, at=IST_10AM) is False


# --------------------------------------------------------------------------
# Timezone
# --------------------------------------------------------------------------


def test_timezone_shifts_the_decision():
    """Same instant, different business timezone, different answer."""
    hours = {"tue": [{"open": "09:00", "close": "18:00"}]}
    # 10:00 IST is 04:30 UTC — inside IST hours, far outside London hours.
    assert is_within_business_hours(hours, tz_name="Asia/Kolkata", at=IST_10AM) is True
    assert is_within_business_hours(hours, tz_name="Europe/London", at=IST_10AM) is False


def test_unknown_timezone_falls_back_to_utc_and_does_not_raise():
    assert is_within_business_hours(WEEKDAY_9_TO_6, tz_name="Not/AZone", at=IST_10AM) in (True, False)


def test_policy_honours_configured_timezone():
    decision = evaluate_inbound_policy(
        profile(business_hours=WEEKDAY_9_TO_6, timezone="Europe/London"), at=IST_10AM
    )
    assert decision.after_hours is True


# --------------------------------------------------------------------------
# After-hours actions
# --------------------------------------------------------------------------


def test_after_hours_voicemail_answers_and_routes_to_voicemail():
    decision = evaluate_inbound_policy(
        profile(business_hours=WEEKDAY_9_TO_6, after_hours_action="voicemail"), at=IST_11PM
    )
    assert decision.should_answer is True
    assert decision.route == ROUTE_VOICEMAIL
    assert decision.after_hours is True
    assert decision.reason == "after_hours_voicemail"


def test_after_hours_hangup_declines():
    decision = evaluate_inbound_policy(
        profile(business_hours=WEEKDAY_9_TO_6, after_hours_action="hangup"), at=IST_11PM
    )
    assert decision.should_answer is False
    assert decision.route == ROUTE_DECLINE


def test_after_hours_always_action_ignores_hours():
    decision = evaluate_inbound_policy(
        profile(business_hours=WEEKDAY_9_TO_6, after_hours_action="always"), at=IST_11PM
    )
    assert decision.should_answer is True
    assert decision.route == ROUTE_AGENT
    assert decision.after_hours is False


def test_after_hours_transfer_routes_to_transfer():
    decision = evaluate_inbound_policy(
        profile(
            business_hours=WEEKDAY_9_TO_6,
            after_hours_action="transfer",
            transfer_number="+14155552671",
        ),
        at=IST_11PM,
    )
    assert decision.should_answer is True
    assert decision.route == ROUTE_TRANSFER


def test_transfer_without_a_number_keeps_answering():
    """A misconfigured transfer must not drop the call."""
    decision = evaluate_inbound_policy(
        profile(business_hours=WEEKDAY_9_TO_6, after_hours_action="transfer"), at=IST_11PM
    )
    assert decision.should_answer is True
    assert decision.route == ROUTE_AGENT
    assert decision.reason == "after_hours_transfer_unconfigured"


# --------------------------------------------------------------------------
# Greeting
# --------------------------------------------------------------------------


def test_greeting_phrase_is_used_when_set():
    decision = evaluate_inbound_policy(profile(greeting_phrase="Thanks for calling Bright Cars."))
    assert decision.greeting_phrase == "Thanks for calling Bright Cars."


def test_greeting_phrase_absent_falls_back_to_the_brain():
    """No configured greeting means today's behaviour: derive from the compiled brain."""
    decision = evaluate_inbound_policy(profile())
    assert decision.greeting_phrase is None


# --------------------------------------------------------------------------
# Malformed configuration must never break a live call
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "broken",
    [
        {"timezone": "Not/AZone"},
        {"after_hours_action": "explode"},
        {"business_hours": {"funday": [{"open": "09:00", "close": "18:00"}]}},
        {"business_hours": {"mon": [{"open": "25:99", "close": "18:00"}]}},
        {"business_hours": "not-an-object"},
        {"transfer_number": "555-not-e164"},
    ],
)
def test_malformed_profile_falls_back_to_answering(broken):
    decision = evaluate_inbound_policy(profile(**broken), at=IST_10AM)
    assert decision.should_answer is True
    assert decision.route == ROUTE_AGENT
    assert decision.used_fallback is True
    assert decision.greeting_phrase is None


def test_malformed_hours_do_not_silence_the_number():
    """Bad hours are treated as always-open, not as permanently closed."""
    hours = {"funday": [{"open": "09:00", "close": "18:00"}]}
    # Unknown keys are ignored — no weekday windows means always open (except closed dates).
    assert is_within_business_hours(hours, at=IST_10AM) is True
    decision = evaluate_inbound_policy(profile(business_hours=hours), at=IST_10AM)
    assert decision.used_fallback is True
    assert decision.should_answer is True


# --------------------------------------------------------------------------
# Validation helpers
# --------------------------------------------------------------------------


def test_normalizers_accept_valid_input():
    assert normalize_timezone("Europe/London") == "Europe/London"
    assert normalize_timezone("") == DEFAULT_TIMEZONE
    assert normalize_greeting_phrase("  Hello   there  ") == "Hello there"
    assert normalize_greeting_phrase("   ") is None
    assert normalize_after_hours_action("HANGUP") == "hangup"
    assert normalize_transfer_number("+14155552671") == "+14155552671"
    assert normalize_business_hours(WEEKDAY_9_TO_6) == WEEKDAY_9_TO_6


@pytest.mark.parametrize(
    "fn,value",
    [
        (normalize_timezone, "Not/AZone"),
        (normalize_greeting_phrase, "x" * 501),
        (normalize_after_hours_action, "explode"),
        (normalize_transfer_number, "5551234"),
        (normalize_business_hours, {"funday": []}),
        (normalize_business_hours, {"mon": [{"open": "9am", "close": "6pm"}]}),
        (normalize_business_hours, {"mon": [{"open": "09:00", "close": "09:00"}]}),
        (normalize_business_hours, "nope"),
    ],
)
def test_normalizers_reject_invalid_input(fn, value):
    with pytest.raises(TelephonyProfileError):
        fn(value)


def test_paused_agent_declines_inbound():
    decision = evaluate_inbound_policy(profile(agent_status="paused"), at=IST_10AM)
    assert decision.should_answer is False
    assert decision.route == ROUTE_DECLINE
    assert decision.reason == "agent_paused"

    decision_inactive = evaluate_inbound_policy(profile(agent_status="inactive"), at=IST_10AM)
    assert decision_inactive.should_answer is False
    assert decision_inactive.reason == "agent_paused"


def test_transfer_action_populates_transfer_number():
    target = "+919876543210"
    decision = evaluate_inbound_policy(
        profile(
            business_hours=WEEKDAY_9_TO_6,
            after_hours_action="transfer",
            transfer_number=target,
        ),
        at=IST_11PM,
    )
    assert decision.should_answer is True
    assert decision.route == ROUTE_TRANSFER
    assert decision.reason == "after_hours_transfer"
    assert decision.transfer_number == target
    assert decision.to_dict()["transferNumber"] == target

