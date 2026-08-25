"""Cache key must stay on compiled brain + budget — projection C is dynamic."""
from __future__ import annotations

from server.agent.instruction_builder import build_live_input
from server.services.prompt_cache_key import compute_cache_key, compute_cache_key_versioned


def test_cache_key_ignores_projection():
    k1 = compute_cache_key_versioned("cb_v1", 2000)
    k2 = compute_cache_key_versioned("cb_v1", 2000)
    assert k1 == k2
    msgs_a = build_live_input(
        compiled_brain_text="brain",
        history=[],
        transcript="turn-1",
        enable_cache=True,
        memory_projection="",
    )
    msgs_b = build_live_input(
        compiled_brain_text="brain",
        history=[],
        transcript="turn-2",
        enable_cache=True,
        memory_projection="name: Ravi | city: Hyderabad",
    )
    assert msgs_a[0]["content"][0]["text"] == msgs_b[0]["content"][0]["text"]
    assert "prompt_cache_breakpoint" in msgs_a[0]["content"][0]
    assert compute_cache_key("brain", 2000) == compute_cache_key("brain", 2000)
    assert "Ravi" not in msgs_a[0]["content"][0]["text"]
    assert any("Ravi" in json_text(m) for m in msgs_b[1:])


def json_text(msg: dict) -> str:
    return str(msg.get("content"))
