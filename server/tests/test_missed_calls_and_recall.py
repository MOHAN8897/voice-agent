"""Missed/rejected calls in history, auto-recall settings, and vague callback times.

No carrier, network or LLM: carrier webhooks are driven with fixture payloads, the
follow-up worker runs against a disposable SQLite database (``queue`` fixture).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from server.call.call_store import call_attempt_store, call_store
from server.call.callback_day_parts import (
    has_explicit_clock,
    resolve_callback_window,
)
from server.call.hangup_causes import classify_hangup, outcome_for_item, reason_for_cause
from server.db.models.entities import CallAttempt, CallCallback
from server.db.models.followup_models import AgentFollowUpPolicy, FollowUpJob
from server.services.saas import followup_service as svc
from server.services.saas.followup_policy import FollowUpConfig, next_allowed
from server.tests.test_durable_followups import NOW, PHONE, queue  # noqa: F401 - shared fixture

IST = "Asia/Kolkata"
# Fri 30 Oct 2026, 14:30 IST.
FRI_AFTERNOON = datetime(2026, 10, 30, 9, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _clean_stores():
    call_store.reset_for_tests()
    call_attempt_store.reset_for_tests()
    yield
    call_store.reset_for_tests()
    call_attempt_store.reset_for_tests()


# --------------------------------------------------------------------------------------
# 1. Hangup causes -> status and plain words
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize("cause,direction,status,label", [
    ("NO_ANSWER", "outbound", "missed", "No answer"),
    ("No Answer", "outbound", "missed", "No answer"),
    ("USER_BUSY", "outbound", "declined", "Busy"),
    ("Busy Line", "outbound", "declined", "Busy"),
    ("CALL_REJECTED", "outbound", "declined", "Declined"),
    ("REJECTED", "outbound", "declined", "Declined"),
    ("UNALLOCATED_NUMBER", "outbound", "failed", "Invalid number"),
    ("INVALID_NUMBER", "outbound", "failed", "Invalid number"),
    # Network faults read as "Couldn't connect", a switched-off phone as "Unreachable",
    # so an owner can tell a bad network from a phone that was off.
    ("NETWORK_OUT_OF_ORDER", "outbound", "failed", "Couldn't connect"),
    ("SERVICE_UNAVAILABLE", "outbound", "failed", "Couldn't connect"),
    ("SUBSCRIBER_ABSENT", "outbound", "failed", "Unreachable"),
    ("DESTINATION_OUT_OF_ORDER", "outbound", "failed", "Unreachable"),
    ("NORMAL_CLEARING", "outbound", "missed", "No answer"),  # rang out, nobody answered
    ("ORIGINATOR_CANCEL", "inbound", "missed", "Missed call"),
    ("NORMAL_CLEARING", "inbound", "missed", "Missed call"),
    ("user_busy", "outbound", "declined", "Busy"),  # Telnyx casing
    ("timeout", "outbound", "missed", "No answer"),
])
def test_vobiz_and_telnyx_hangup_causes_map_to_plain_outcomes(cause, direction, status, label):
    outcome = classify_hangup(cause, direction=direction, answered=False, connected=False)
    assert outcome.status == status
    item = {"status": outcome.status, "direction": direction, "end_reason": outcome.end_reason}
    words = outcome_for_item(item)
    assert words["outcome_label"] == label
    assert words["outcome_reason"] and words["outcome_reason"].endswith(".")


def test_sip_codes_and_invalid_numbers_are_not_retryable():
    assert reason_for_cause("", sip_code=486) == "busy"
    assert reason_for_cause(None, sip_code="603") == "rejected"
    outcome = classify_hangup("UNALLOCATED_NUMBER", direction="outbound", answered=False, connected=False)
    assert outcome.retryable is False
    assert classify_hangup("USER_BUSY", direction="outbound", answered=False, connected=False).retryable


def test_connected_calls_keep_their_answered_status():
    assert classify_hangup("NORMAL_CLEARING", direction="outbound", answered=True, connected=True).status == "outbound"
    assert classify_hangup("NORMAL_CLEARING", direction="inbound", answered=True, connected=True).status == "answered"


# --------------------------------------------------------------------------------------
# 2. Unanswered calls now appear in the history
# --------------------------------------------------------------------------------------

async def test_unanswered_outbound_dial_appears_in_history_with_reason():
    from server.call.call_timeline import list_timeline
    from server.call.carrier_attempts import record_outbound_dial
    from server.routes.vobiz import _record_vobiz_attempt_end

    tenant, agent = str(uuid.uuid4()), str(uuid.uuid4())
    await record_outbound_dial(provider="vobiz", tenant_id=tenant, agent_id=agent, from_e164="+918000000001",
                               to_e164="+919000000002", result={"ok": True, "call_control_id": "req-1"},
                               dial_request_id="d1")
    # Replayed dial responses never reset the row.
    await record_outbound_dial(provider="vobiz", tenant_id=tenant, agent_id=agent, from_e164="+918000000001",
                               to_e164="+919000000002", result={"ok": True, "call_control_id": "req-1"},
                               dial_request_id="d1")
    payload = {"CallUUID": "call-1", "RequestUUID": "req-1", "HangupCause": "USER_BUSY", "Direction": "outbound",
               "From": "+918000000001", "To": "+919000000002", "AnswerTime": ""}
    local = {"tenant_id": tenant, "agent_id": agent, "direction": "outbound"}
    await _record_vobiz_attempt_end(payload, local, "call-1", "req-1", "track-1", "USER_BUSY", None)

    items, total = await list_timeline(tenant_id=tenant, agent_id=agent)
    assert total == 1
    row = items[0]
    assert row["status"] == "declined" and row["direction"] == "outbound"
    assert row["outcome_label"] == "Busy"
    assert row["outcome_reason"] == "Their line was busy."
    assert row["caller_phone"] == "+919000000002"  # the person we dialled, not our caller ID
    # The status filter used by the console finds it.
    declined, _ = await list_timeline(tenant_id=tenant, statuses=["declined"])
    assert [i["call_id"] for i in declined] == [row["call_id"]]


async def test_no_answer_and_carrier_refusal_are_both_recorded():
    from server.call.call_timeline import list_timeline
    from server.call.carrier_attempts import record_outbound_dial
    from server.routes.vobiz import _record_vobiz_attempt_end

    tenant, agent = str(uuid.uuid4()), str(uuid.uuid4())
    await record_outbound_dial(provider="vobiz", tenant_id=tenant, agent_id=agent, from_e164=None,
                               to_e164="+919000000003", result={"ok": True, "call_control_id": "req-2"})
    await _record_vobiz_attempt_end({"HangupCause": "NO_ANSWER"}, {"tenant_id": tenant, "direction": "outbound"},
                                    "req-2", "req-2", "", "NO_ANSWER", None)
    await record_outbound_dial(provider="vobiz", tenant_id=tenant, agent_id=agent, from_e164=None,
                               to_e164="+919000000004", result={"ok": False, "code": "dial_failed"},
                               dial_request_id="d-fail")
    # Policy refusals (DND, wallet) never rang anyone and are not history rows.
    await record_outbound_dial(provider="vobiz", tenant_id=tenant, agent_id=agent, from_e164=None,
                               to_e164="+919000000005", result={"ok": False, "code": "dnc_blocked"},
                               dial_request_id="d-dnd")
    items, _ = await list_timeline(tenant_id=tenant)
    by_phone = {i["caller_phone"]: i for i in items}
    assert by_phone["+919000000003"]["outcome_label"] == "No answer"
    assert by_phone["+919000000004"]["status"] == "failed"
    assert by_phone["+919000000004"]["outcome_reason"] == "The call couldn't be placed."
    assert "+919000000005" not in by_phone


async def test_inbound_vobiz_call_nobody_answered_is_a_missed_call(monkeypatch):
    from server.call.call_timeline import list_timeline
    from server.routes import vobiz

    tenant, agent = str(uuid.uuid4()), str(uuid.uuid4())
    monkeypatch.setattr(vobiz, "_vobiz_callback_tenant_id", AsyncMock(return_value=tenant))
    payload = {"CallUUID": "in-1", "HangupCause": "ORIGINATOR_CANCEL", "Direction": "inbound",
               "From": "+919000000009", "To": "+918000000001"}
    await vobiz._record_vobiz_attempt_end(payload, {"agent_id": agent, "inbound_declined_reason": "after_hours_hangup"},
                                          "in-1", "", "", "ORIGINATOR_CANCEL", None)
    items, _ = await list_timeline(tenant_id=tenant, statuses=["missed"])
    assert len(items) == 1
    assert items[0]["outcome_label"] == "Missed call"
    assert items[0]["caller_phone"] == "+919000000009"
    assert "outside working hours" in items[0]["outcome_reason"]


async def test_connected_call_hangup_links_instead_of_adding_a_missed_row():
    from server.call.call_timeline import list_timeline
    from server.call.carrier_attempts import record_outbound_dial
    from server.routes.vobiz import _record_vobiz_attempt_end

    tenant, agent = str(uuid.uuid4()), str(uuid.uuid4())
    await record_outbound_dial(provider="vobiz", tenant_id=tenant, agent_id=agent, from_e164=None,
                               to_e164="+919000000006", result={"ok": True, "call_control_id": "req-3"})
    await _record_vobiz_attempt_end({"HangupCause": "NORMAL_CLEARING", "AnswerTime": "2026-10-30 10:00:00"},
                                    {"tenant_id": tenant, "direction": "outbound"}, "req-3", "req-3", "", "NORMAL_CLEARING",
                                    str(uuid.uuid4()))
    # A late duplicate hangup must not turn it into a missed call.
    await _record_vobiz_attempt_end({"HangupCause": "NO_ANSWER"}, {"tenant_id": tenant, "direction": "outbound"},
                                    "req-3", "req-3", "", "NO_ANSWER", None)
    items, _ = await list_timeline(tenant_id=tenant, statuses=["missed", "declined", "failed"])
    assert items == []


# --------------------------------------------------------------------------------------
# 3. Vague callback times
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize("text,label,display", [
    ("రేపు ఈవెనింగ్", "tomorrow evening", "Sat 31 Oct, 5:00–7:30 pm"),
    ("call me in the evening", "this evening", "Fri 30 Oct, 5:00–7:30 pm"),
    ("tomorrow morning", "tomorrow morning", "Sat 31 Oct, 10:00 am–12:00 pm"),
    ("शाम को कॉल करना", "this evening", "Fri 30 Oct, 5:00–7:30 pm"),
    ("कल सुबह", "tomorrow morning", "Sat 31 Oct, 10:00 am–12:00 pm"),
    ("நாளை மாலை", "tomorrow evening", "Sat 31 Oct, 5:00–7:30 pm"),
    ("రేపు మధ్యాహ్నం", "tomorrow afternoon", "Sat 31 Oct, 2:00–4:00 pm"),
    ("after lunch", "today after lunch", "Fri 30 Oct, 2:00–3:00 pm"),
    ("night", "tonight", "Fri 30 Oct, 7:30–8:30 pm"),
    ("end of day", "today end of day", "Fri 30 Oct, 5:30–6:30 pm"),
    ("Monday evening", "Monday evening", "Mon 2 Nov, 5:00–7:30 pm"),
    ("ఎల్లుండి ఉదయం", "day after tomorrow morning", "Sun 1 Nov, 10:00 am–12:00 pm"),
])
def test_day_parts_resolve_in_tenant_timezone(text, label, display):
    resolved = resolve_callback_window(text, now=FRI_AFTERNOON, timezone_name=IST, spread_key="k")
    assert resolved is not None, text
    assert resolved["label"] == label
    assert resolved["display"] == display
    assert resolved["summary"] == f"{label} → {display}"
    start, end, at = (datetime.fromisoformat(resolved[k]) for k in ("start", "end", "scheduledAt"))
    assert start <= at < end
    assert at - max(start, FRI_AFTERNOON) <= timedelta(minutes=25)  # start of window plus a small spread


def test_passed_window_moves_to_next_day_and_never_breaks_legal_hours():
    late = datetime(2026, 10, 30, 15, 0, tzinfo=timezone.utc)  # 20:30 IST
    resolved = resolve_callback_window("evening", now=late, timezone_name=IST)
    assert resolved["display"].startswith("Sat 31 Oct")
    # A tenant cannot stretch "night" beyond 21:00 IST (TRAI).
    wide = resolve_callback_window("night", now=FRI_AFTERNOON, timezone_name=IST,
                                   day_parts={"night": {"start": "20:00", "end": "23:00"}})
    assert wide["display"] == "Fri 30 Oct, 8:00–9:00 pm"


def test_morning_said_in_the_afternoon_means_tomorrow_and_skips_closed_days():
    resolved = resolve_callback_window("morning", now=FRI_AFTERNOON, timezone_name=IST, weekdays=[0, 1, 2, 3, 4])
    assert resolved["display"].startswith("Mon 2 Nov")


def test_explicit_times_and_vague_words_are_left_alone():
    assert has_explicit_clock("tomorrow at 5 pm")
    assert has_explicit_clock("कल 5 बजे")
    assert has_explicit_clock("రేపు 5 గంటలకు")
    assert resolve_callback_window("tomorrow at 5 pm", now=FRI_AFTERNOON) is None
    assert resolve_callback_window("later", now=FRI_AFTERNOON) is None
    assert resolve_callback_window("call me some time", now=FRI_AFTERNOON) is None


def test_configured_windows_are_used_and_validated():
    cfg = FollowUpConfig(dayParts={"evening": {"start": "18:00", "end": "20:00"}})
    assert cfg.dayParts["evening"] == {"start": "18:00", "end": "20:00"}
    assert cfg.dayParts["morning"] == {"start": "10:00", "end": "12:00"}  # defaults kept
    with pytest.raises(ValueError):
        FollowUpConfig(dayParts={"evening": {"start": "20:00", "end": "18:00"}})
    with pytest.raises(ValueError):
        FollowUpConfig(dayParts={"brunch": {"start": "11:00", "end": "12:00"}})


async def test_vague_callback_request_is_scheduled_at_window_without_llm(queue, monkeypatch):
    cfg = FollowUpConfig(enabled=True, timezone=IST, callbackMode="automatic")
    await svc.save_policy(queue.principal, queue.aid, cfg, 0, True)
    extract = AsyncMock(return_value=None)
    monkeypatch.setattr(svc, "_extract_time", extract)
    async with queue.factory() as session:
        callback = CallCallback(callback_id=uuid.uuid4(), tenant_id=queue.principal.tenant_id, agent_id=str(queue.aid),
            original_call_id=uuid.uuid4(), to_e164=PHONE, dial_request_id="requested:vague", mode="requested",
            status="requested")
        session.add(callback)
        await session.flush()
        await svc.capture_request(session, callback, request_text="రేపు ఈవెనింగ్ కాల్ చేయండి",
                                  requested_when="రేపు ఈవెనింగ్", llm={"provider": "fixture", "model": "m"})
        await session.commit()
    async with queue.factory() as session:
        row = await session.scalar(select(FollowUpJob))
    assert row.status == "scheduled" and row.reason == "requested_window_resolved"
    window = row.payload["resolvedWindow"]
    # NOW is Wed 28 Oct 15:30 IST -> tomorrow evening is Thu 29 Oct 17:00-19:30 IST.
    assert window["summary"] == "tomorrow evening → Thu 29 Oct, 5:00–7:30 pm"
    due = row.due_at.replace(tzinfo=timezone.utc)
    assert datetime(2026, 10, 29, 11, 30, tzinfo=timezone.utc) <= due < datetime(2026, 10, 29, 14, 0, tzinfo=timezone.utc)
    assert svc.job_public(row)["resolvedWindow"]["display"] == "Thu 29 Oct, 5:00–7:30 pm"
    extract.assert_not_awaited()


# --------------------------------------------------------------------------------------
# 4. Auto-recall settings and the follow-up worker
# --------------------------------------------------------------------------------------

def test_recall_defaults_follow_industry_practice():
    cfg = FollowUpConfig()
    assert cfg.recallOutboundMode == "off" and cfg.missedMode == "off"  # opt-in
    assert cfg.recallMaxAttempts == 3 and cfg.recallSpacingMinutes == 120
    assert cfg.recallMinGapAfterRejectMinutes == 60 and cfg.recallMaxPerNumberPerDay == 2
    assert cfg.recallBackoff and cfg.skipHolidays
    assert cfg.recall_gap_minutes(attempts_made=1, declined=False) == 120
    assert cfg.recall_gap_minutes(attempts_made=2, declined=False) == 240
    assert FollowUpConfig(recallSpacingMinutes=30).recall_gap_minutes(attempts_made=1, declined=True) == 60
    with pytest.raises(ValueError):
        FollowUpConfig(recallMaxAttempts=6)
    with pytest.raises(ValueError):
        FollowUpConfig(quietHoursEnabled=True, quietStart="14:00", quietEnd="13:00")


def test_calling_window_respects_trai_hours_quiet_hours_and_holidays():
    cfg = FollowUpConfig(timezone=IST, startTime="07:00", endTime="23:00", weekdays=[0, 1, 2, 3, 4, 5, 6],
                         quietHoursEnabled=True, quietStart="13:00", quietEnd="14:00", holidays=["2026-10-31"])
    early = datetime(2026, 10, 30, 1, 30, tzinfo=timezone.utc)  # 07:00 IST
    assert next_allowed(early, cfg).astimezone().isoformat()  # sanity
    assert next_allowed(early, cfg) == datetime(2026, 10, 30, 3, 30, tzinfo=timezone.utc)  # 09:00 IST
    lunch = datetime(2026, 10, 30, 7, 45, tzinfo=timezone.utc)  # 13:15 IST
    assert next_allowed(lunch, cfg) == datetime(2026, 10, 30, 8, 30, tzinfo=timezone.utc)  # 14:00 IST
    late = datetime(2026, 10, 30, 15, 45, tzinfo=timezone.utc)  # 21:15 IST Fri -> Sat is a holiday
    assert next_allowed(late, cfg) == datetime(2026, 11, 1, 3, 30, tzinfo=timezone.utc)  # Sun 09:00 IST


async def _enable_recall(queue, **kwargs):
    cfg = FollowUpConfig(enabled=True, timezone="UTC", startTime="00:00", endTime="23:59",
                         weekdays=[0, 1, 2, 3, 4, 5, 6], recallOutboundMode="automatic", **kwargs)
    return await svc.save_policy(queue.principal, queue.aid, cfg, 0, True)


async def _outbound_attempt(queue, *, status, end_reason, control=None, policy_reason="outbound_dial", to=PHONE):
    async with queue.factory() as session:
        row = CallAttempt(tenant_id=queue.principal.tenant_id, agent_id=queue.aid, direction="outbound",
            provider="vobiz", provider_call_control_id=control or str(uuid.uuid4()), status=status, end_reason=end_reason,
            policy_reason=policy_reason, from_number="+12025550124", to_number=to,
            started_at=NOW, ended_at=NOW, created_at=NOW)
        session.add(row)
        await session.commit()
        return row


async def test_unanswered_outbound_calls_become_recall_jobs(queue):
    await _enable_recall(queue, recallOutcomes=["no_answer", "busy"])
    await _outbound_attempt(queue, status="declined", end_reason="busy")
    await _outbound_attempt(queue, status="declined", end_reason="rejected", to="+12025550199")  # not chosen
    await _outbound_attempt(queue, status="missed", end_reason="no_answer", policy_reason="campaign_dial",
                            to="+12025550188")  # campaigns keep their own retry rules
    await _outbound_attempt(queue, status="failed", end_reason="invalid_number_failed", to="+12025550177")
    await svc.run_once()
    queue.dial.assert_not_awaited()  # first recall waits for the spacing
    async with queue.factory() as session:
        rows = {r.phone: r for r in (await session.scalars(select(FollowUpJob))).all()}
    assert set(rows) == {PHONE}
    job = rows[PHONE]
    assert job.kind == "recall" and job.status == "scheduled" and job.reason == "unanswered_outbound"
    assert job.payload["outcome"] == "busy"
    # Busy -> at least the spacing (120 min) and the reject gap (60 min).
    assert job.due_at.replace(tzinfo=timezone.utc) == NOW + timedelta(minutes=120)


async def test_review_mode_queues_recalls_for_approval(queue):
    cfg = FollowUpConfig(enabled=True, timezone="UTC", recallOutboundMode="review")
    await svc.save_policy(queue.principal, queue.aid, cfg, 0, True)
    await _outbound_attempt(queue, status="missed", end_reason="no_answer")
    await svc.run_once()
    async with queue.factory() as session:
        job = await session.scalar(select(FollowUpJob))
    assert job.status == "needs_review" and job.reason == "approval_required"
    assert svc.job_public(job)["outcome"] == "no_answer"


async def test_dnd_numbers_are_never_recalled(queue):
    from server.db.models.phase5_models import DncEntry
    await _enable_recall(queue)
    async with queue.factory() as session:
        session.add(DncEntry(tenant_id=queue.principal.tenant_id, phone_e164=PHONE, active=True))
        await session.commit()
    await _outbound_attempt(queue, status="missed", end_reason="no_answer")
    await svc.run_once()
    async with queue.factory() as session:
        job = await session.scalar(select(FollowUpJob))
    assert job.status == "suppressed" and job.reason == "do_not_call"


async def test_recall_retries_back_off_and_stop_at_the_limit(queue):
    await _enable_recall(queue, recallMaxAttempts=2, recallSpacingMinutes=60)
    row = FollowUpJob(tenant_id=queue.principal.tenant_id, agent_id=queue.aid, origin_key="recall:x", source_id=str(uuid.uuid4()),
        kind="recall", phone=PHONE, status="scheduled", reason="unanswered_outbound", due_at=NOW,
        expires_at=NOW + timedelta(days=2), authorized_by=queue.principal.user_id, billing_tenant_id=queue.principal.tenant_id,
        payload={}, created_at=NOW, updated_at=NOW)
    async with queue.factory() as session:
        session.add(row)
        await session.commit()
    await svc.run_once()
    queue.dial.assert_awaited_once()
    await _outbound_attempt(queue, status="missed", end_reason="no_answer", control="synthetic-control")
    await svc.run_once()
    async with queue.factory() as session:
        pending = await session.get(FollowUpJob, row.id)
        assert pending.status == "scheduled" and pending.reason == "retry_unanswered"
        # Second attempt: 60 min doubled by back-off.
        assert pending.due_at.replace(tzinfo=timezone.utc) == NOW + timedelta(minutes=120)


async def test_invalid_number_stops_recalls(queue):
    await _enable_recall(queue)
    row = FollowUpJob(tenant_id=queue.principal.tenant_id, agent_id=queue.aid, origin_key="recall:y", source_id=str(uuid.uuid4()),
        kind="recall", phone=PHONE, status="dialed", reason="dial_accepted", control_id="ctl-invalid", attempts=1,
        expires_at=NOW + timedelta(days=2), authorized_by=queue.principal.user_id, billing_tenant_id=queue.principal.tenant_id,
        payload={}, created_at=NOW, updated_at=NOW)
    async with queue.factory() as session:
        session.add(row)
        await session.commit()
    await _outbound_attempt(queue, status="failed", end_reason="invalid_number_failed", control="ctl-invalid")
    await svc.run_once()
    async with queue.factory() as session:
        done = await session.get(FollowUpJob, row.id)
    assert done.status == "completed" and done.reason == "number_invalid"


async def test_turning_recall_off_cancels_pending_recalls_and_consent_is_required(queue):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as denied:
        await svc.save_policy(queue.principal, queue.aid, FollowUpConfig(enabled=True, recallOutboundMode="automatic"), 0, False)
    assert denied.value.status_code == 422
    await _enable_recall(queue)
    await _outbound_attempt(queue, status="missed", end_reason="no_answer")
    await svc.run_once()
    async with queue.factory() as session:
        policy = await session.scalar(select(AgentFollowUpPolicy))
        config = {**policy.config, "recallOutboundMode": "off"}
    await svc.save_policy(queue.principal, queue.aid, FollowUpConfig.model_validate(config), 1, False)
    async with queue.factory() as session:
        job = await session.scalar(select(FollowUpJob))
    assert job.status == "cancelled" and job.reason == "automation_disabled"
