"""Validated permissions and timezone-aware scheduling. No carrier or LLM calls."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, model_validator

from server.call.callback_day_parts import DEFAULT_DAY_PARTS, legal_hours


class FollowUpConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    callbackMode: Literal["review", "automatic"] = "review"
    missedMode: Literal["off", "review", "automatic"] = "off"
    missedDelayMinutes: int = Field(30, ge=5, le=10080)
    timezone: str = "Asia/Kolkata"
    startTime: str = "09:00"
    endTime: str = "18:00"
    weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5])
    maxAttempts: int = Field(1, ge=1, le=3)
    retryDelayMinutes: int = Field(180, ge=30, le=10080)
    dailyLimit: int = Field(20, ge=1, le=500)
    cooldownMinutes: int = Field(360, ge=30, le=43200)
    expiryDays: int = Field(7, ge=1, le=90)
    scoringEnabled: bool = True
    scoreWeights: dict[str, int] = Field(default_factory=lambda: {"interest": 40, "requirements": 25, "timing": 25, "contact": 10})
    scoreFactKeys: dict[str, list[str]] = Field(default_factory=lambda: {
        "requirements": ["requirement", "requirements", "product", "service", "product_interest", "budget", "quantity", "need"],
        "timing": ["callback_when", "callback_time", "preferred_time", "timeline", "purchase_timeline", "appointment_time", "slot"],
        "contact": ["phone", "callback_phone", "phone_number", "mobile", "email"],
    })
    hotThreshold: int = Field(70, ge=1, le=100)
    warmThreshold: int = Field(40, ge=1, le=99)
    # --- Auto-recall for calls that didn't connect -------------------------------------
    # Inbound missed calls use ``missedMode`` (above); outbound calls the other person
    # didn't answer, was busy for, declined or that failed use ``recallOutboundMode``.
    recallOutboundMode: Literal["off", "review", "automatic"] = "off"
    recallOutcomes: list[Literal["no_answer", "busy", "declined", "failed"]] = Field(
        default_factory=lambda: ["no_answer", "busy", "declined"])
    #: Recall attempts per missed/unanswered call (both directions).
    recallMaxAttempts: int = Field(3, ge=1, le=5)
    #: Gap between recall attempts; 1440 = next day.
    recallSpacingMinutes: int = Field(120, ge=30, le=10080)
    #: Double the gap after each further no-answer (2 h, 4 h, 8 h…).
    recallBackoff: bool = True
    #: Never ring someone straight back after they rejected the call.
    recallMinGapAfterRejectMinutes: int = Field(60, ge=15, le=1440)
    #: Calls to the same number per day across all automatic follow-ups.
    recallMaxPerNumberPerDay: int = Field(2, ge=1, le=5)
    quietHoursEnabled: bool = False
    quietStart: str = "13:00"
    quietEnd: str = "14:00"
    skipHolidays: bool = True
    #: Extra no-call dates (YYYY-MM-DD) on top of the employee's closed days.
    holidays: list[str] = Field(default_factory=list, max_length=60)
    #: How vague callback times ("evening", "after lunch") map to clock windows.
    dayParts: dict[str, dict[str, str]] = Field(default_factory=lambda: {k: dict(v) for k, v in DEFAULT_DAY_PARTS.items()})

    @model_validator(mode="after")
    def validate_schedule(self):
        try:
            ZoneInfo(self.timezone)
            start, end = time.fromisoformat(self.startTime), time.fromisoformat(self.endTime)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError("Choose a valid timezone and HH:MM calling window") from exc
        if start.tzinfo or end.tzinfo or start >= end or len(self.startTime) != 5 or len(self.endTime) != 5:
            raise ValueError("Calling window must start before it ends on the same day")
        if not self.weekdays or len(set(self.weekdays)) != len(self.weekdays) or any(d < 0 or d > 6 for d in self.weekdays):
            raise ValueError("Choose unique calling weekdays (Monday=0)")
        if set(self.scoreWeights) != {"interest", "requirements", "timing", "contact"} or any(type(v) is not int or v < 0 for v in self.scoreWeights.values()) or sum(self.scoreWeights.values()) != 100:
            raise ValueError("The four score weights must be nonnegative integers totaling 100")
        if self.warmThreshold >= self.hotThreshold:
            raise ValueError("Warm threshold must be lower than hot threshold")
        if set(self.scoreFactKeys) != {"requirements", "timing", "contact"} or any(
            not keys or len(keys) > 20 or any(not key.strip() or len(key) > 64 for key in keys)
            for keys in self.scoreFactKeys.values()
        ):
            raise ValueError("Choose 1–20 memory field keys for each score signal (up to 64 characters each)")
        if self.recallOutboundMode != "off" and not self.recallOutcomes:
            raise ValueError("Choose which unanswered calls to call back")
        try:
            quiet_start, quiet_end = time.fromisoformat(self.quietStart), time.fromisoformat(self.quietEnd)
        except ValueError as exc:
            raise ValueError("Quiet hours must be HH:MM times") from exc
        if self.quietHoursEnabled and quiet_start >= quiet_end:
            raise ValueError("Quiet hours must start before they end")
        for value in self.holidays:
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("Holidays must be dates like 2026-11-14") from exc
        if set(self.dayParts) - set(DEFAULT_DAY_PARTS):
            raise ValueError("Unknown time-of-day name")
        for key, window in self.dayParts.items():
            try:
                opens, closes = time.fromisoformat(window["start"]), time.fromisoformat(window["end"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Set a start and end time for {key.replace('_', ' ')}") from exc
            if opens >= closes:
                raise ValueError(f"The {key.replace('_', ' ')} window must start before it ends")
        self.dayParts = {**{k: dict(v) for k, v in DEFAULT_DAY_PARTS.items()}, **self.dayParts}
        return self

    def recall_attempt_limit(self, kind: str) -> int:
        """Attempts allowed for a job: callbacks keep ``maxAttempts``; recalls use the recall limit."""
        return self.maxAttempts if kind == "callback" else self.recallMaxAttempts

    def recall_gap_minutes(self, *, attempts_made: int, declined: bool) -> int:
        """Gap before the next recall, with exponential back-off after repeated no-answers."""
        gap = self.recallSpacingMinutes
        if self.recallBackoff and attempts_made > 1:
            gap = min(10080, gap * (2 ** (attempts_made - 1)))
        if declined:
            gap = max(gap, self.recallMinGapAfterRejectMinutes)
        return gap


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def timing_model_snapshot(selected: Any) -> dict:
    """Scheduling is post-call analysis, never a change to a tier's speech model.

    Live probes showed the conversation-specialized speech model normalizing six
    hours to thirty minutes. Use the same configured analyzer as call outcomes,
    pin its model on the job, and never fall back to a different model on failure.
    """
    from server.realtime.models import http_openai_model
    return {"provider": "openai", "model": http_openai_model(), "options": {}, "purpose": "configured_post_call_analysis"}


def local_instant(value: str, timezone_name: str) -> datetime:
    """Reject ambiguous/nonexistent local DST times rather than inventing an offset."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        return utc(parsed)
    zone = ZoneInfo(timezone_name)
    candidates = {utc(parsed.replace(tzinfo=zone, fold=fold)) for fold in (0, 1)
                  if utc(parsed.replace(tzinfo=zone, fold=fold)).astimezone(zone).replace(tzinfo=None) == parsed}
    if len(candidates) != 1:
        raise ValueError("Time is ambiguous or does not exist in the selected timezone; choose an explicit offset")
    return candidates.pop()


def next_allowed(now: datetime, config: FollowUpConfig, profile: dict | None = None) -> datetime | None:
    """Intersect automation window with agent hours/holidays, including DST and overnight hours."""
    zone = ZoneInfo(config.timezone)
    origin = utc(now).replace(second=0, microsecond=0)
    if origin < utc(now):
        origin += timedelta(minutes=1)
    profile = profile or {}
    start, end = time.fromisoformat(config.startTime), time.fromisoformat(config.endTime)
    # Legal calling hours (TRAI 09:00-21:00 in India) always bound the tenant window.
    legal_start, legal_end = legal_hours(config.timezone)
    start, end = max(start, legal_start), min(end, legal_end)
    quiet = (time.fromisoformat(config.quietStart), time.fromisoformat(config.quietEnd)) if config.quietHoursEnabled else None
    holidays = set(config.holidays) if config.skipHolidays else set()
    # Bounded scan: at most 14 * 1440 local minutes; no network, typically first iteration.
    for minute in range(14 * 1440 + 1):
        # Check now exactly; otherwise use future minute boundaries, never a grace period before opening.
        candidate = utc(now) if minute == 0 else origin + timedelta(minutes=minute - 1)
        local = candidate.astimezone(zone)
        if local.weekday() not in config.weekdays or not start <= local.time() < end:
            continue
        if quiet and quiet[0] <= local.time() < quiet[1]:
            continue
        if local.date().isoformat() in holidays:
            continue
        hours = profile.get("business_hours") or {}
        if within_profile_hours(candidate, hours, profile.get("timezone") or config.timezone):
            return candidate
    return None


def within_profile_hours(at: datetime, hours: dict, zone_name: str) -> bool:
    """Overnight hours belong to the day on which they open; malformed hours fail closed."""
    local = utc(at).astimezone(ZoneInfo(zone_name))
    if local.date().isoformat() in hours.get("closed", []):
        return False
    days = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    if not any(day in hours for day in days):
        return True
    try:
        for offset in (0, -1):
            date = local.date() + timedelta(days=offset)
            if date.isoformat() in hours.get("closed", []):
                continue
            for entry in hours.get(days[date.weekday()], []):
                opens, closes = time.fromisoformat(entry["open"]), time.fromisoformat(entry["close"])
                if offset == 0 and ((opens < closes and opens <= local.time() < closes) or (opens > closes and local.time() >= opens)):
                    return True
                if offset == -1 and opens > closes and local.time() < closes:
                    return True
    except (ValueError, KeyError, TypeError):
        return False
    return False


def extracted_due(payload: dict, request_text: str, requested_at: datetime, config: FollowUpConfig) -> datetime | None:
    """Only a grounded, explicit timing proposal may enter the automatic queue."""
    evidence = str(payload.get("evidence") or "").strip()
    if not evidence:
        return None
    from server.call.close_decision import evidence_matches
    if not evidence_matches(evidence, request_text):
        return None
    try:
        if payload.get("kind") == "relative":
            minutes = payload.get("delay_minutes")
            if type(minutes) is not int or not 1 <= minutes <= config.expiryDays * 1440:
                return None
            due = utc(requested_at) + timedelta(minutes=minutes)
        elif payload.get("kind") == "absolute":
            # Caller timezone overrides require tenant review; never guess timezone from a number.
            if payload.get("timezone") not in (None, "", config.timezone):
                return None
            value = str(payload.get("local_datetime") or "")
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is not None and parsed.utcoffset() != parsed.astimezone(ZoneInfo(config.timezone)).utcoffset():
                return None
            due = local_instant(value, config.timezone)
        else:
            return None
        return due if utc(requested_at) < due <= utc(requested_at) + timedelta(days=config.expiryDays) else None
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        return None
