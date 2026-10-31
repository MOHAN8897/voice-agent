"""Instruction builder migration tests — Phase 2."""
from server.agent.instruction_builder import LIVE_TURN_DISCIPLINE, build_live_input
from server.services.prompt_cache_key import compute_cache_key_versioned


def test_build_live_input_developer_slot():
    msgs = build_live_input(
        compiled_brain_text="compiled brain text",
        history=[{"role": "assistant", "content": "hello"}],
        transcript="user says hi",
        enable_cache=True,
    )
    assert msgs[0]["role"] == "developer"
    assert msgs[0]["content"][0]["text"] == "compiled brain text"
    assert "prompt_cache_breakpoint" in msgs[0]["content"][0]
    turn = msgs[-1]["content"][0]["text"]
    assert turn.startswith(LIVE_TURN_DISCIPLINE)
    assert turn.endswith("user says hi")
    assert "Answer first" in turn
    assert "never re-ask" in turn


def test_versioned_cache_key_stable():
    k1 = compute_cache_key_versioned("cb_v20260825_abc", 2000)
    k2 = compute_cache_key_versioned("cb_v20260825_abc", 2000)
    k3 = compute_cache_key_versioned("cb_v20260825_def", 2000)
    assert k1 == k2
    assert k1 != k3
    assert ":cb-" in k1
