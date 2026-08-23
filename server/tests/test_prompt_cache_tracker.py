"""Tests for prompt cache tracker and turn telemetry."""
from server.agent.conversation_manager import conversation_manager
from server.services.prompt_cache_tracker import PromptCacheTracker


def test_get_turn_number_empty_session():
    conversation_manager.clear("turn-test")
    assert conversation_manager.get_turn_number("turn-test") == 1
    conversation_manager.add_turn("turn-test", "hi", "hello")
    assert conversation_manager.get_turn_number("turn-test") == 2
    assert conversation_manager.get_completed_turns("turn-test") == 1
    conversation_manager.clear("turn-test")


def test_cache_tracker_hit_then_write():
    tracker = PromptCacheTracker()
    key = "telugu-voice:v5:cfg-abc123"

    ev1 = tracker.record(
        cache_key=key,
        session_id="s1",
        turn=1,
        input_tokens=1072,
        cached_tokens=0,
        cache_write_tokens=1060,
        request_id="r1",
    )
    assert ev1 is not None
    assert ev1.event == "write"
    assert ev1.turns_since_last_write is None

    ev2 = tracker.record(
        cache_key=key,
        session_id="s1",
        turn=2,
        input_tokens=1106,
        cached_tokens=1060,
        cache_write_tokens=0,
        request_id="r2",
    )
    assert ev2 is not None
    assert ev2.event == "hit"

    ev3 = tracker.record(
        cache_key=key,
        session_id="s1",
        turn=18,
        input_tokens=1191,
        cached_tokens=0,
        cache_write_tokens=1060,
        request_id="r3",
    )
    assert ev3 is not None
    assert ev3.event == "write"
    assert ev3.turns_since_last_write == 2  # global turn 3, last write at global 1

    snap = tracker.snapshot()
    assert snap["global_turns"] == 3
    assert snap["per_key"][key]["writes"] == 2
    assert snap["per_key"][key]["hits"] == 1


def test_metrics_record_brain_turn():
    from server.utils.metrics import Metrics

    m = Metrics()
    m.record_brain_turn(
        call_id="call-1",
        turn=2,
        usage={
            "input_tokens": 1106,
            "output_tokens": 23,
            "cached_tokens": 1060,
            "cache_write_tokens": 0,
        },
        layers={"brain": 1058, "history": 12, "transcript": 6, "summary": 0},
        ttft_ms=1400,
        total_ms=1450,
        prep_ms=3,
        request_id="resp_x",
        cache_key="telugu-voice:v5:cfg-test",
        cache_event="hit",
        model="gpt-5.6-luna",
    )
    snap = m.snapshot()
    assert snap["brain_ttft_ms"]["count"] == 1
    assert snap["steady_turn_ttft_ms"]["count"] == 1
    assert len(snap["recent_brain_turns"]) == 1
    turn = snap["recent_brain_turns"][0]
    assert turn["call"] == "call-1"
    assert turn["turn"] == 2
    assert turn["cached_tokens"] == 1060
    assert turn["brain_tokens_est"] == 1058
    assert turn["ttft_ms"] == 1400
