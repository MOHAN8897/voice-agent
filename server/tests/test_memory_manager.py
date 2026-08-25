"""Object B — op validation, event log, sole mutator."""
from __future__ import annotations

from server.call.memory_manager import memory_manager


def test_apply_set_fact_and_event_log(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from server.config.env import get_settings

    get_settings.cache_clear()
    memory_manager.reset_for_tests()
    memory_manager.init("c1")
    result = memory_manager.apply_proposals(
        "c1",
        [{"op": "set_fact", "key": "city", "value": "Hyderabad"}],
        turn_seq=1,
    )
    assert result["snapshot"]["facts"]["city"] == "Hyderabad"
    events = memory_manager.list_events("c1")
    assert len(events) == 1
    assert events[0]["applied"] is True
    disk = (tmp_path / "calls" / "c1" / "memory_snapshot.json").read_text(encoding="utf-8")
    assert "Hyderabad" in disk
    memory_manager.reset_for_tests()
    get_settings.cache_clear()


def test_reject_unknown_op_and_bad_key(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from server.config.env import get_settings

    get_settings.cache_clear()
    memory_manager.reset_for_tests()
    memory_manager.init("c2")
    result = memory_manager.apply_proposals(
        "c2",
        [
            {"op": "delete_all"},
            {"op": "set_fact", "key": "not a key", "value": "x"},
            {"op": "set_preference", "key": "language", "value": "te-en mix"},
        ],
        turn_seq=2,
    )
    assert "language" in result["snapshot"]["preferences"]
    assert result["event"]["validation_errors"]
    assert any("unknown op" in e for e in result["event"]["validation_errors"])
    memory_manager.reset_for_tests()
    get_settings.cache_clear()


def test_append_context_and_summary_caps(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKING_MEMORY_MAX_CHARS", "40")
    monkeypatch.setenv("ROLLING_SUMMARY_MAX_TOKENS", "10")
    from server.config.env import get_settings

    get_settings.cache_clear()
    memory_manager.reset_for_tests()
    memory_manager.init("c3")
    memory_manager.apply_proposals(
        "c3",
        [{"op": "append_context", "value": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa extra"}],
        turn_seq=1,
    )
    snap = memory_manager.get_snapshot("c3")
    assert len(snap["important_context"]) <= 40
    memory_manager.apply_proposals(
        "c3",
        [{"op": "update_summary", "value": "word " * 80}],
        turn_seq=2,
    )
    snap = memory_manager.get_snapshot("c3")
    assert len(snap["summary"]) <= 80
    memory_manager.reset_for_tests()
    get_settings.cache_clear()


def test_snapshot_at_turn_replays_events(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from server.config.env import get_settings

    get_settings.cache_clear()
    memory_manager.reset_for_tests()
    memory_manager.init("c4")
    memory_manager.apply_proposals("c4", [{"op": "set_fact", "key": "name", "value": "Ravi"}], turn_seq=1)
    memory_manager.apply_proposals("c4", [{"op": "set_fact", "key": "city", "value": "Hyderabad"}], turn_seq=2)
    at1 = memory_manager.snapshot_at_turn("c4", 1)
    assert at1["facts"] == {"name": "Ravi"}
    assert "city" not in at1["facts"]
    memory_manager.reset_for_tests()
    get_settings.cache_clear()


def test_twenty_turns_retain_early_facts(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from server.config.env import get_settings
    from server.call.memory_projection import build

    get_settings.cache_clear()
    memory_manager.reset_for_tests()
    memory_manager.init("long")
    memory_manager.apply_proposals(
        "long",
        [{"op": "set_fact", "key": "name", "value": "Ravi"}],
        turn_seq=1,
    )
    for i in range(2, 21):
        memory_manager.apply_proposals(
            "long",
            [{"op": "set_fact", "key": f"t{i}", "value": str(i)}],
            turn_seq=i,
        )
    snap = memory_manager.get_snapshot("long")
    assert snap["facts"]["name"] == "Ravi"
    proj = build(snap, include_summary=False)
    assert "Ravi" in proj
    assert "user said" not in proj
    memory_manager.reset_for_tests()
    get_settings.cache_clear()


def test_manual_correction_is_audited(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from server.config.env import get_settings

    get_settings.cache_clear()
    memory_manager.reset_for_tests()
    memory_manager.init("c5")
    memory_manager.manual_correction(
        "c5",
        [{"op": "set_fact", "key": "name", "value": "Corrected"}],
        actor="admin@local",
        reason="misheard STT",
        turn_seq=9,
    )
    event = memory_manager.list_events("c5")[0]
    assert event["source"] == "manual_correction"
    assert event["actor"] == "admin@local"
    assert event["reason"] == "misheard STT"
    memory_manager.reset_for_tests()
    get_settings.cache_clear()
