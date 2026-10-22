"""Dev telephony JSON store — history pagination and contacts."""
from __future__ import annotations

from server.services.dev_telephony_store import DevTelephonyStore


def test_record_dial_and_list_history_pagination():
    store = DevTelephonyStore()
    store.reset_for_tests()
    agent_a = "agent-a"
    agent_b = "agent-b"
    for i in range(7):
        store.record_dial(
            provider="telnyx",
            external_id=f"ext-{i}",
            agent_id=agent_a if i < 5 else agent_b,
            source_session_id="sess-1",
            from_e164="+15551234567",
            to_e164=f"+91987654321{i}",
            stack_override={"pipeline": "realtime_text"},
            language="te-IN",
            tier="medium",
        )
    page1, total_a = store.list_history(agent_id=agent_a, limit=5, offset=0)
    assert total_a == 5
    assert len(page1) == 5
    page2, _ = store.list_history(agent_id=agent_a, limit=5, offset=5)
    assert len(page2) == 0

    page_b, total_b = store.list_history(agent_id=agent_b, limit=5, offset=0)
    assert total_b == 2
    assert len(page_b) == 2


def test_sync_registry_row_updates_status_and_events():
    store = DevTelephonyStore()
    store.reset_for_tests()
    entry = store.record_dial(
        provider="telnyx",
        external_id="cc-123",
        agent_id="agent-a",
        source_session_id="sess-1",
        from_e164="+15551234567",
        to_e164="+919876543210",
        stack_override={"pipeline": "realtime_voice"},
        language="te-IN",
        tier="medium",
    )
    store.sync_registry_row(
        {"call_control_id": "cc-123", "status": "ringing", "internal_call_id": None},
        provider="telnyx",
    )
    row = store.get_history(entry["history_id"])
    assert row is not None
    assert row["status"] == "ringing"
    assert any(ev.get("stage") == "ringing" for ev in row.get("events") or [])

    store.sync_registry_row(
        {
            "call_control_id": "cc-123",
            "status": "streaming",
            "internal_call_id": "internal-abc",
        },
        provider="telnyx",
    )
    row = store.get_history(entry["history_id"])
    assert row is not None
    assert row["internal_call_id"] == "internal-abc"
    assert row["pipeline"] == "realtime_voice"

    store.sync_registry_row(
        {"call_control_id": "cc-123", "status": "completed", "internal_call_id": "internal-abc"},
        provider="telnyx",
    )
    row = store.get_history(entry["history_id"])
    assert row is not None
    assert row["status"] == "ended"
    assert row.get("ended_at")


def test_contacts_crud():
    store = DevTelephonyStore()
    store.reset_for_tests()
    created = store.upsert_contact(name="Test User", phone="+919876543210", notes="dev dial")
    assert created["contact_id"]
    assert created["phone"] == "+919876543210"

    contacts = store.list_contacts()
    assert len(contacts) == 1

    updated = store.upsert_contact(
        contact_id=created["contact_id"],
        name="Updated",
        phone="+919876543210",
        notes="still dev",
    )
    assert updated["name"] == "Updated"

    assert store.delete_contact(created["contact_id"]) is True
    assert store.list_contacts() == []


def test_list_and_get_history_persist_finalized_costs(monkeypatch):
    store = DevTelephonyStore()
    store.reset_for_tests()
    entry = store.record_dial(
        provider="telnyx",
        external_id="cc-cost",
        agent_id="agent-a",
        source_session_id="sess-1",
        from_e164="+15551234567",
        to_e164="+919876543210",
        stack_override={"pipeline": "realtime_voice"},
        language="te-IN",
        tier="medium",
    )
    with store._lock:
        store._data["history"][0]["internal_call_id"] = "internal-cost"

    def fake_review(_cid: str):
        return {
            "usage": {"cost_inr": 12.0, "duration_sec": 30, "pipeline": "realtime_voice"},
            "cost_usd": 0.14,
            "cost_inr": 12.0,
            "model_cost_inr": 4.0,
            "model_cost_usd": 0.05,
            "telnyx_inr": 8.0,
            "telnyx_usd": 0.09,
            "pipeline": "realtime_voice",
            "duration_sec": 30,
            "end_reason": "hangup",
        }

    def fake_meta(_cid: str):
        return {"duration_sec": 30, "end_reason": "hangup"}

    monkeypatch.setattr("server.call.call_ledger.call_ledger.review_fields", fake_review)
    monkeypatch.setattr("server.call.call_ledger.call_ledger.read_meta", fake_meta)

    page, total = store.list_history(agent_id="agent-a", limit=5, offset=0)
    assert total == 1
    assert page[0]["duration_sec"] == 30
    assert page[0]["cost"]["telnyx_inr"] == 8.0
    assert page[0]["cost"]["model_cost_inr"] == 4.0
    assert page[0]["cost"]["cost_inr"] == 12.0

    import json

    raw = json.loads(store._path().read_text(encoding="utf-8"))
    stored = next(r for r in raw["history"] if r["history_id"] == entry["history_id"])
    assert stored["duration_sec"] == 30
    assert stored["cost"]["telnyx_inr"] == 8.0

    detail = store.get_history(entry["history_id"])
    assert detail is not None
    assert detail["cost"]["cost_inr"] == 12.0
    assert detail["pipeline"] == "realtime_voice"
