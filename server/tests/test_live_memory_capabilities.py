"""Regressions from Premium call A60BA6EC: facts, action truth and closing."""
import json
from types import SimpleNamespace

import pytest

from server.brain.capabilities import apply_available_tools, order_confirmation_allowed_from_script
from server.brain.compiled_brain_artifact import assemble_unified_brain, refresh_platform_sections
from server.call import close_classifier
from server.call.action_proof import proof_for_tool_result, replace_unavailable_action_promises
from server.call.memory_guard import grounded_turn_operations
from server.call.memory_manager import MemoryManager


@pytest.mark.parametrize("name", ["Sai Kiran", "సాయి కిరణ్", "साई किरण", "சாய் கிரண்", "ಸಾಯಿ ಕಿರಣ್"])
def test_full_names_survive_grounding(name):
    text = f"నా పేరు {name}."
    ops = grounded_turn_operations([{"op": "set_fact", "key": "caller_name", "value": name, "evidence": text}], text)
    assert ops == [{"op": "set_fact", "key": "caller_name", "value": name}]


def test_invented_facts_sensitive_fields_and_conclusions_are_rejected():
    text = "100 cards. My PIN is 1234."
    raw = [
        {"op": "set_fact", "key": "quantity", "value": "100", "evidence": "100 cards"},
        {"op": "set_fact", "key": "delivery_address", "value": "Hyderabad", "evidence": "100 cards"},
        {"op": "set_fact", "key": "bank_pin", "value": "1234", "evidence": "1234"},
        {"op": "set_fact", "key": "order_confirmed", "value": "100", "evidence": "100"},
    ]
    assert grounded_turn_operations(raw, text) == [{"op": "set_fact", "key": "quantity", "value": "100"}]


def test_late_merge_cannot_undo_quantity_correction_even_after_restart(tmp_path, monkeypatch):
    from server.config.env import get_settings

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        manager = MemoryManager()
        for turn, value in [(2, "20"), (8, "100")]:
            manager.apply_proposals("corrected", [{"op": "set_fact", "key": "quantity", "value": value}], turn_seq=turn)
        restarted = MemoryManager()
        restarted.apply_proposals("corrected", [{"op": "set_fact", "key": "quantity", "value": "20"}], turn_seq=2)
        assert restarted.get_snapshot("corrected")["facts"]["quantity"] == "100"
        assert json.loads((tmp_path / "calls/corrected/memory_snapshot.json").read_text())["facts"]["quantity"] == "100"
        restarted.apply_proposals("corrected", [{"op": "set_fact", "key": "city", "value": "Hyderabad"}], turn_seq=3)
        historical = restarted.snapshot_at_turn("corrected", 3)
        assert historical["facts"] == {"quantity": "20", "city": "Hyderabad"}
    finally:
        get_settings.cache_clear()


def test_concurrent_memory_merges_publish_latest_cache(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from server.call import redis_memory_cache
    from server.config.env import get_settings

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    entered, release = Event(), Event()
    cache = {}

    def publish(call_id, snap):
        if snap["facts"]["quantity"] == "20":
            entered.set()
            assert release.wait(2)
        cache[call_id] = snap

    monkeypatch.setattr(redis_memory_cache, "set_snapshot", publish)
    monkeypatch.setattr(redis_memory_cache, "get_snapshot", cache.get)
    manager = MemoryManager()
    try:
        with ThreadPoolExecutor(2) as pool:
            first = pool.submit(manager.apply_proposals, "cache-order", [{"op": "set_fact", "key": "quantity", "value": "20"}], turn_seq=2)
            assert entered.wait(2)
            second = pool.submit(manager.apply_proposals, "cache-order", [{"op": "set_fact", "key": "quantity", "value": "100"}], turn_seq=8)
            release.set()
            first.result(timeout=3)
            second.result(timeout=3)
        assert MemoryManager().get_snapshot("cache-order")["facts"]["quantity"] == "100"
    finally:
        release.set()
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_pinned_control_step_extracts_memory_without_large_speech_schema(monkeypatch):
    from server import providers

    observed = {}

    class Adapter:
        async def stream_live_turn(self, **kwargs):
            observed.update(kwargs)
            yield {"done": True, "text": json.dumps({"decision": "continue", "memory_operations": [
                {"op": "set_fact", "key": "caller_name", "value": "Sai Kiran", "evidence": "Sai Kiran"}
            ]})}

    registry = SimpleNamespace(is_provider_enabled=lambda *_: True, is_model_allowed=lambda *_: True,
                               get_llm=lambda *_: Adapter())
    monkeypatch.setattr(providers, "get_provider_registry", lambda: registry)
    result = await close_classifier.classify_close_turn(
        transcript="నా పేరు Sai Kiran.", agent_previous="మీ పేరు?", language="te-IN",
        llm=SimpleNamespace(provider="sarvam", model="pinned-premium", config={}), extract_memory=True,
    )
    assert result["memory_operations"][0]["value"] == "Sai Kiran"
    assert observed["model"] == "pinned-premium"
    assert observed["max_output_tokens"] == 512
    assert "schema" not in observed


def test_acknowledgement_cannot_close_unfinished_request_but_explicit_stop_can():
    raw = {"decision": "close", "reason": "goodbye", "evidence": "ఓకే అండి, థ్యాంక్ యూ", "explicit_end": False}
    assert close_classifier.parse_classifier_output(raw, raw["evidence"], unfinished_request=True) is None
    raw.update(evidence="అంతే అంతే థ్యాంక్ యూ", explicit_end=True)
    assert close_classifier.parse_classifier_output(raw, raw["evidence"], unfinished_request=True)["decision"] == "close"


def test_current_tool_manifest_replaces_revoked_permissions_without_changing_business():
    text = assemble_unified_brain(language="te-IN", script="Cards cost 25 rupees. Collect delivery address and confirm the order.")
    assert order_confirmation_allowed_from_script(text)
    tools = [{"name": "GOOGLECALENDAR_FIND_FREE_SLOTS", "description": "Check availability", "parameters": {"required": ["date"]}}]
    current = apply_available_tools(text, tools)
    assert current.count("--- CALL CAPABILITIES ---") == 1
    assert "Cards cost 25 rupees" in current
    assert "GOOGLECALENDAR_FIND_FREE_SLOTS; required: date" in current
    assert "order_confirmation: not_allowed" in current
    assert "GOOGLECALENDAR_FIND_FREE_SLOTS" in refresh_platform_sections(current, "te-IN")
    assert "GOOGLECALENDAR_FIND_FREE_SLOTS" not in apply_available_tools(current, [])


def test_local_enquiry_receipt_does_not_grant_email_or_team_handoff():
    assert proof_for_tool_result("SAVE_ENQUIRY", {"status": "ok"}) == "enquiry_saved"
    assert proof_for_tool_result("SAVE_ENQUIRY", {"status": "unknown"}) is None
    text = "Your details are saved. I will send them to the team."
    result = replace_unavailable_action_promises(text, "en-IN", saved_request=True)
    assert "Your details are saved." in result
    assert "I will send them to the team" not in result


def test_telugu_english_confirmation_needs_server_proof():
    from server.call.action_proof import unproven_claim

    text = "మీ one hundred visiting cards order confirm చేస్తున్నాను."
    assert unproven_claim(text, []) == "order_confirmed"
    assert unproven_claim(text, ["order_confirmed"]) is None
