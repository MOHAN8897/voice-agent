"""Independent negative controls; failures are retained as audit evidence."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from server.call.memory_guard import grounded_turn_operations
from server.call.memory_manager import MemoryManager, empty_snapshot
from server.services.tool_router import VoxlyToolRouter
from server.services.saas.lead_scoring import score_outcome


def test_rejected_product_cannot_become_selected_product():
    caller = "నాకు మగ్స్ వద్దు, కార్డులు కావాలి"
    operations = grounded_turn_operations([
        {"op": "set_fact", "key": "product", "value": "మగ్స్", "evidence": caller}
    ], caller)
    assert operations == [], "Rejected mugs were accepted as the selected product"


def test_same_email_create_deduplicates_when_optional_phone_is_added():
    router = VoxlyToolRouter()
    first = router._generate_idempotency_key("tenant", "call", "HUBSPOT_CREATE_CONTACT", {
        "email": "audit@example.invalid", "firstname": "Test"
    })
    second = router._generate_idempotency_key("tenant", "call", "HUBSPOT_CREATE_CONTACT", {
        "email": "audit@example.invalid", "firstname": "Test", "phone": "+12025550123"
    })
    assert first == second, "Adding an optional phone permits a second CREATE for the same email"


def test_new_lead_without_buying_evidence_gets_no_interest_points():
    result = score_outcome({"disposition": "new_lead", "disposition_confidence": .95, "facts": {}})
    interest = next(c for c in result["components"] if c["signal"] == "interest")
    assert interest["points"] == 0, "Generic new_lead is being treated as buying evidence"


def test_delayed_old_memory_write_cannot_replace_new_snapshot(monkeypatch):
    manager = MemoryManager()
    manager._state["call"] = empty_snapshot()
    manager._events["call"] = []
    old_write_entered, release_old = Event(), Event()
    persisted = {}

    def write(_call, snapshot):
        if snapshot["facts"]["city"] == "Old":
            old_write_entered.set()
            assert release_old.wait(5)
        persisted["snapshot"] = snapshot

    monkeypatch.setattr(manager, "_append_event", lambda *args: None)
    monkeypatch.setattr(manager, "_write_snapshot", write)
    monkeypatch.setattr("server.call.redis_memory_cache.set_snapshot", lambda *args: None)
    with ThreadPoolExecutor(max_workers=2) as workers:
        old = workers.submit(manager.apply_proposals, "call", [
            {"op": "set_fact", "key": "city", "value": "Old"}], turn_seq=1)
        assert old_write_entered.wait(5)
        try:
            new = workers.submit(manager.apply_proposals, "call", [
                {"op": "set_fact", "key": "city", "value": "New"}], turn_seq=2)
            new.result(timeout=5)
        finally:
            release_old.set()
        old.result(timeout=5)
    assert manager.peek_snapshot("call")["facts"]["city"] == "New"
    assert persisted["snapshot"]["facts"]["city"] == "New", "Old disk/cache state overwrote the newer memory"
