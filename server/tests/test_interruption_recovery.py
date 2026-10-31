"""Regressions for the two silent Premium calls on 2026-10-26."""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from server.services import pstn_voice_core as core
from server.tests.test_pstn_vad_barge_audit import SttEvents


@pytest.mark.asyncio
async def test_filtered_barge_final_releases_idle_state_and_next_question():
    loop = core.PstnVoiceLoop(session_id="filtered-barge", call_id=None, on_agent_wire=AsyncMock())
    echo = "We currently only sell visiting cards and identity cards."
    loop._last_tts_text = echo
    loop._set_phase(core.PHASE_INTERRUPTING)
    loop._awaiting_barge_final = True
    loop._barge_epoch = time.monotonic()
    loop._awaiting_barge_final_at = loop._barge_epoch
    question = "What is the minimum budget for visiting cards?"
    loop._stt = SttEvents([
        {"event": "transcript.final", "text": echo},
        {"event": "transcript.final", "text": question},
    ])
    loop._launch_turn = Mock()
    try:
        await loop._stt_reader()
        if loop._coalesce_task:
            await asyncio.wait_for(loop._coalesce_task, timeout=0.5)
        assert loop._phase == core.PHASE_LISTENING
        assert not loop._awaiting_barge_final
        loop._launch_turn.assert_called_once_with(question)
    finally:
        await loop.close()


def test_repeated_partial_of_current_request_does_not_cancel_its_reply():
    loop = core.PstnVoiceLoop(session_id="duplicate-partial", call_id=None, on_agent_wire=AsyncMock())
    loop._set_phase(core.PHASE_THINKING)
    loop._turn_busy = True
    loop._current_turn_transcript = "What is the best price range for these cards?"
    loop._last_vad_voice_at = time.monotonic()
    loop._has_barge_voice = Mock(return_value=True)
    loop._think_partial_kind = "speech"
    loop._think_partial_started_at = time.monotonic() - 1
    assert not loop._should_think_cancel("What is the best price range for these cards?")
    assert not loop._should_think_cancel("What is the best price range")
    assert loop._should_think_cancel("stop")


def test_only_a_burst_of_committed_interruptions_requests_a_polite_nudge(monkeypatch):
    from server.services import user_turn_hints as hints

    ticks = [100.0]
    monkeypatch.setattr(hints.time, "monotonic", lambda: ticks[0])
    ctx = SimpleNamespace(slow_down_nudged=False)
    hints.note_caller_interruption(ctx)
    ticks[0] += hints.INTERRUPTION_WINDOW_SEC + 1
    hints.note_caller_interruption(ctx)
    hints.note_caller_interruption(ctx)
    assert not getattr(ctx, "interruption_nudge_pending", False)
    hints.note_caller_interruption(ctx)
    assert ctx.interruption_nudge_pending
    assert len(ctx.interruption_times) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_first", [False, True])
async def test_polite_request_is_in_one_usable_reply_and_never_repeated(monkeypatch, cancel_first):
    from server.call import call_context, close_classifier
    from server.call.live_turn_orchestrator import LiveTurnOrchestrator
    from server.config.env import get_settings
    from server.prompts.agent_voice_rules import slow_down_fallback_for

    ctx = SimpleNamespace(pipeline="composed_voice", status="active", resolved_stack=SimpleNamespace(llm=None),
                          compiled_brain_text="Answer questions only.", interruption_nudge_pending=True,
                          slow_down_nudged=False, agent_hangup_armed=False, call_end_policy=None)
    monkeypatch.setattr(call_context, "get", lambda _: ctx)
    monkeypatch.setattr(close_classifier, "start_close_classification", lambda **_: None)
    monkeypatch.setenv("ENABLE_CALL_ARCHIVE", "false")
    get_settings.cache_clear()
    orchestrator = LiveTurnOrchestrator()
    monkeypatch.setattr(orchestrator, "_memory_blocks", AsyncMock(return_value=(None, None)))
    monkeypatch.setattr(orchestrator, "_maybe_build_live_input", lambda **_: [])

    speech_calls = 0

    async def speech(**_kwargs):
        nonlocal speech_calls
        speech_calls += 1
        if cancel_first and speech_calls == 1:
            raise asyncio.CancelledError
        yield {"done": True, "text": "Each card costs 25 rupees.", "response_contract": "speech_text"}

    monkeypatch.setattr(orchestrator, "_stream_llm", speech)
    try:
        async def turn():
            events = [event async for event in orchestrator.handle_user_turn_stream(
                transcript="What is the price?", language_code="en-IN", call_id="polite", session_id="polite")]
            return next(event for event in events if event.get("done"))

        if cancel_first:
            with pytest.raises(asyncio.CancelledError):
                await turn()
            assert ctx.interruption_nudge_pending and not ctx.slow_down_nudged
        first = await turn()
        line = slow_down_fallback_for("en-IN")
        assert first["text"].count(line) == 1
        assert "twenty five rupees" in first["text"] and not first["end_call"].get("should_end")
        assert ctx.slow_down_nudged and not ctx.interruption_nudge_pending
        second = await turn()
        assert line not in second["text"]
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_reply_contract_follows_compiled_developer_brain_and_turn_hints():
    from server.call.live_turn_orchestrator import LiveTurnOrchestrator

    observed = {}

    class Adapter:
        uses_plain_live_speech = True

        async def stream_live_turn(self, **kwargs):
            observed.update(kwargs)
            yield {"done": True, "text": "The minimum is not provided."}

    events = [event async for event in LiveTurnOrchestrator()._stream_composed_speech(
        adapter=Adapter(), messages=[
            {"role": "developer", "content": "Business workflow: ask whether they wish to order."},
            {"role": "system", "content": "Caller is still enquiring."},
            {"role": "user", "content": "What is the minimum? I am not buying now."},
        ], schema=None, stream_kwargs={"max_output_tokens": 1280}, call_id=None,
        provider="sarvam", model="sarvam-105b-conversations")]
    messages = observed["input_messages"]
    assert messages[0]["role"] == "developer"
    # The static contract follows the compiled brain and precedes per-turn
    # messages, so the provider's prefix cache covers every static byte.
    assert messages[1]["content"].startswith("Speech delivery contract:")
    assert messages[2]["content"] == "Caller is still enquiring."
    assert messages[3]["role"] == "user"
    assert events[-1]["response_contract"] == "speech_text"


@pytest.mark.asyncio
@pytest.mark.parametrize("intro", [False, True])
async def test_committed_interruptions_are_counted_without_changing_opening(intro, monkeypatch):
    from server.call import call_context

    ctx = SimpleNamespace(slow_down_nudged=False, interruption_times=[])
    monkeypatch.setattr(call_context, "get", lambda _: ctx)
    loop = core.PstnVoiceLoop(session_id="committed", call_id="committed", on_agent_wire=AsyncMock())
    loop.interrupt_tts = AsyncMock()
    loop._set_phase(core.PHASE_INTRO if intro else core.PHASE_SPEAKING)
    try:
        await loop._commit_barge("wait, I have a question")
        assert len(ctx.interruption_times) == (0 if intro else 1)
    finally:
        await loop.close()
