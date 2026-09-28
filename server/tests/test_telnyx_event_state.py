from server.services.telnyx_event_state import event_state_patch


def test_leg_events_advance_monotonically():
    row = {}
    p1 = event_state_patch(row, "call.ringing", event_id="e1", occurred_at="2026-09-28T10:00:00Z")
    row.update(p1)
    p2 = event_state_patch(row, "call.answered", event_id="e2", occurred_at="2026-09-28T10:00:01Z")
    row.update(p2)
    assert row["status"] == "answered"
    # Out-of-order ringing must not downgrade answered.
    p3 = event_state_patch(row, "call.ringing", event_id="e3", occurred_at="2026-09-28T10:00:02Z")
    assert p3 == {}


def test_media_events_do_not_touch_leg_status():
    row = {"status": "answered"}
    patch = event_state_patch(row, "streaming.stopped", event_id="m1", occurred_at="2026-09-28T10:00:03Z")
    assert patch.get("media_status") == "stopped"
    assert "status" not in patch


def test_duplicate_event_id_ignored():
    row = {"leg_event_id": "e1", "status": "ringing"}
    assert event_state_patch(row, "call.ringing", event_id="e1") == {}
