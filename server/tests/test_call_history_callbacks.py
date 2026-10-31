"""Call history: callback dials are linked to the call they returned, and every
reason a call never connected has its own label.

Uses the disposable SQLite ``queue`` fixture; no carrier or network.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from server.call.call_timeline import annotate_callbacks
from server.call.hangup_causes import OUTCOME_LABELS, classify_hangup, outcome_for_item
from server.db.models.entities import CallAttempt, CallCallback
from server.tests.test_durable_followups import NOW, queue  # noqa: F401 - shared fixture


@pytest.mark.parametrize("cause,kind", [
    ("NO_ANSWER", "no_answer"),
    ("CALL_REJECTED", "declined"),
    ("USER_BUSY", "busy"),
    ("SUBSCRIBER_ABSENT", "unreachable"),
    ("UNALLOCATED_NUMBER", "invalid_number"),
    ("NETWORK_OUT_OF_ORDER", "connect_failed"),
])
def test_each_outbound_outcome_has_its_own_kind_and_label(cause, kind):
    outcome = classify_hangup(cause, direction="outbound", answered=False, connected=False)
    words = outcome_for_item({"status": outcome.status, "direction": "outbound", "end_reason": outcome.end_reason})
    assert words["outcome_kind"] == kind
    assert words["outcome_label"] == OUTCOME_LABELS[kind]


def test_inbound_drop_is_not_called_a_switched_off_phone():
    words = outcome_for_item({"status": "failed", "direction": "inbound", "end_reason": "unreachable"})
    assert words["outcome_kind"] == "connect_failed"
    words = outcome_for_item({"status": "missed", "direction": "inbound", "end_reason": "no_answer"})
    assert words["outcome_kind"] == "missed_call"


def test_answered_call_has_no_failure_kind():
    assert outcome_for_item({"status": "outbound", "direction": "outbound"})["outcome_kind"] is None


async def _attempt(session, tenant_id, control, *, status, end_reason=None, linked_call_id=None, minutes=0):
    row = CallAttempt(
        attempt_id=uuid.uuid4(), tenant_id=tenant_id, provider="vobiz", provider_call_control_id=control,
        direction="outbound", from_number="+917900000001", to_number="+918800000002", status=status,
        end_reason=end_reason, linked_call_id=linked_call_id, policy_reason="outbound_dial",
        started_at=NOW + timedelta(minutes=minutes), created_at=NOW + timedelta(minutes=minutes),
    )
    session.add(row)
    return row


async def test_callbacks_are_linked_both_ways_with_their_real_result(queue):  # noqa: F811
    tenant = queue.principal.tenant_id
    async with queue.factory() as session:
        busy = await _attempt(session, tenant, "c-busy", status="declined", end_reason="busy")
        declined = await _attempt(session, tenant, "c-declined", status="declined", end_reason="rejected", minutes=1)
        await _attempt(session, tenant, "c-unplaced", status="failed", end_reason="dial_failed", minutes=2)
        # First callback (of the busy call) was declined; the second (of that) rang out.
        session.add_all([
            CallCallback(callback_id=uuid.uuid4(), tenant_id=tenant, user_id=queue.principal.user_id,
                         original_attempt_id=busy.attempt_id, agent_id=str(queue.aid), to_e164="+918800000002",
                         dial_request_id="r1", mode="manual", status="dialed", provider="vobiz",
                         provider_call_control_id="c-declined", created_at=NOW + timedelta(minutes=1)),
            CallCallback(callback_id=uuid.uuid4(), tenant_id=tenant, user_id=None,
                         original_attempt_id=declined.attempt_id, agent_id=str(queue.aid), to_e164="+918800000002",
                         dial_request_id="r2", mode="ai_redial", status="failed",
                         created_at=NOW + timedelta(minutes=2)),
            # A caller's own "call me back" request is not a dial and marks nothing.
            CallCallback(callback_id=uuid.uuid4(), tenant_id=tenant, original_attempt_id=declined.attempt_id,
                         agent_id=str(queue.aid), to_e164="+918800000002", dial_request_id="r3",
                         mode="requested", status="requested", created_at=NOW + timedelta(minutes=3)),
        ])
        await session.commit()
        busy_id, declined_id = str(busy.attempt_id), str(declined.attempt_id)

    items = [
        {"call_id": busy_id, "is_attempt": True, "_control": "c-busy"},
        {"call_id": declined_id, "is_attempt": True, "_control": "c-declined"},
        # A carrier-refused dial is stored under dialfail:<dial_request_id>.
        {"call_id": str(uuid.uuid4()), "is_attempt": True, "_control": "dialfail:r2"},
    ]
    await annotate_callbacks(items, tenant_id=str(tenant))
    by_control = {c: i for c, i in zip(("busy", "declined", "unplaced"), items)}

    assert by_control["busy"]["callback_of"] is None
    assert by_control["busy"]["callbacks"]["count"] == 1
    assert by_control["busy"]["callbacks"]["last_result"] == "Declined"

    declined_row = by_control["declined"]
    assert declined_row["callback_of"]["id"] == busy_id
    assert declined_row["callback_of"]["mode"] == "manual"
    assert declined_row["callback_of"]["by"] == queue.principal.email
    assert declined_row["callbacks"]["count"] == 1  # the requested row is not counted
    assert declined_row["callbacks"]["last_result"] == "Not placed"

    assert by_control["unplaced"]["callback_of"]["id"] == declined_id
    assert by_control["unplaced"]["callback_of"]["mode"] == "ai_redial"
    # The carrier id never leaves the server.
    assert all("_control" not in item for item in items)


async def test_annotation_never_breaks_history_without_a_database(monkeypatch):
    from server.db import connection

    monkeypatch.setattr(connection, "get_session_factory", lambda: None)
    items = [{"call_id": str(uuid.uuid4()), "_control": "x"}]
    await annotate_callbacks(items, tenant_id=str(uuid.uuid4()))
    assert items == [{"call_id": items[0]["call_id"], "callback_of": None, "callbacks": None}]
