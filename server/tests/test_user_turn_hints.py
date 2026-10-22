"""Verbose-caller slow-down hints."""
from types import SimpleNamespace

from server.call.live_turn_orchestrator import live_turn_orchestrator
from server.services.user_turn_hints import should_nudge_slow_down


def test_should_nudge_slow_down_for_long_monologue():
    long_text = " ".join(["word"] * 40)
    assert should_nudge_slow_down(long_text)
    assert not should_nudge_slow_down("Hi, I need the price please.")


def test_anti_repeat_hint_after_first_turn():
    from server.agent.conversation_manager import conversation_manager

    session_id = "anti-repeat-test"
    conversation_manager.add_turn(session_id, "What plots do you have?", "We have villas from fifty lakhs.")
    hint = live_turn_orchestrator._maybe_anti_repeat_hint(session_id)
    assert hint is not None
    assert "fifty lakhs" in hint.lower()
    assert "do not repeat" in hint.lower()


def test_slow_down_hint_once_per_call():
    ctx = SimpleNamespace(slow_down_nudged=False)
    long_text = " ".join(["detail"] * 42)
    first = live_turn_orchestrator._maybe_slow_down_hint(
        long_text,
        language_code="en-IN",
        call_id=None,
        ctx=ctx,
    )
    second = live_turn_orchestrator._maybe_slow_down_hint(
        long_text,
        language_code="en-IN",
        call_id=None,
        ctx=ctx,
    )
    assert first is not None
    assert "slowly" in first.lower()
    assert second is None
    assert ctx.slow_down_nudged
