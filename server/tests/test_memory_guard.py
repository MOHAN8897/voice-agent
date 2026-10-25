"""Facts, not conclusions — call notes must not settle the outcome on their own."""
from __future__ import annotations

from server.call.memory_guard import sanitize_model_operations, suppress_stale_conclusions


def test_rejects_call_conclusions_without_an_approved_close():
    kept, rejected = sanitize_model_operations(
        [
            {"op": "set_fact", "key": "outcome", "value": "firm_refusal"},
            {"op": "append_context", "value": "The conversation is closed"},
            {"op": "set_fact", "key": "budget", "value": "5000"},
        ]
    )
    assert kept == [{"op": "set_fact", "key": "budget", "value": "5000"}]
    assert any(code.startswith("call_conclusion:") for code in rejected)


def test_rejects_commerce_conclusions_without_tool_proof():
    ops = [
        {"op": "set_fact", "key": "converted", "value": "true"},
        {"op": "set_fact", "key": "order_confirmed", "value": "yes"},
        {"op": "append_context", "value": "lead is qualified"},
    ]
    kept, rejected = sanitize_model_operations(ops)
    assert kept == []
    assert len(rejected) == 3


def test_tool_proof_allows_the_order_fact():
    ops = [{"op": "set_fact", "key": "order_confirmed", "value": "true"}]
    kept, rejected = sanitize_model_operations(ops, order_proof=True)
    assert kept == ops
    assert rejected == []


def test_gate_approval_allows_the_close_reason_fact():
    ops = [{"op": "set_fact", "key": "outcome", "value": "firm_refusal"}]
    kept, rejected = sanitize_model_operations(ops, close_approved=True)
    assert kept == ops
    assert rejected == []


def test_model_summary_is_always_rejected():
    kept, rejected = sanitize_model_operations(
        [{"op": "update_summary", "value": "Caller refused."}],
        close_approved=True,
        order_proof=True,
    )
    assert kept == []
    assert rejected == ["model_update_summary"]


def test_plain_facts_pass_through():
    ops = [
        {"op": "set_fact", "key": "product", "value": "visiting cards"},
        {"op": "set_fact", "key": "quantity", "value": "500"},
        {"op": "append_context", "value": "Caller asked the price of visiting cards"},
    ]
    kept, rejected = sanitize_model_operations(ops)
    assert kept == ops
    assert rejected == []


def test_non_dict_operations_are_dropped_silently():
    kept, rejected = sanitize_model_operations([None, "set_fact", 3])
    assert kept == []
    assert rejected == []


def _declined_snapshot():
    return {
        "facts": {"outcome": "firm refusal", "product": "visiting cards"},
        "preferences": {"do_not_call": "true"},
    }


def test_stale_decline_is_suppressed_when_the_caller_now_shows_interest():
    filtered = suppress_stale_conclusions(
        _declined_snapshot(), "Actually I am interested, tell me the price"
    )
    assert filtered["facts"] == {"product": "visiting cards"}
    assert filtered["preferences"] == {}


def test_stale_decline_survives_when_the_caller_reaffirms_it():
    snap = _declined_snapshot()
    filtered = suppress_stale_conclusions(
        snap, "No, I am not interested, do not send details"
    )
    assert filtered["facts"]["outcome"] == "firm refusal"
    assert filtered["preferences"]["do_not_call"] == "true"


def test_snapshot_is_untouched_when_the_current_turn_is_neutral():
    snap = _declined_snapshot()
    assert suppress_stale_conclusions(snap, "hello") is snap
    assert suppress_stale_conclusions(snap, "") is snap
