"""A speech-only reply drafted alongside the control decision, used only for plain turns.

Call d8236122 (2 Nov 2026): each reply waited ~1 s for the close/contact classifier
before the reply model was even asked, so callers heard ~2 s gaps. The draft makes a
plain turn cost max(classifier, reply) instead of classifier + reply; every other turn
(action, business question, contact change, close, wait) discards it.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.call import close_classifier
from server.call.live_turn_orchestrator import live_turn_orchestrator, plain_control_turn

DELAY = 0.3
PLAIN = {"decision": "continue", "contact_intent": "none", "remaining_request": "", "action_request": "none",
         "wait_for_caller": False, "memory_operations": []}


@pytest.mark.parametrize("change,plain", [
    ({}, True),
    ({"action_request": "write"}, False),
    ({"action_request": "read"}, False),
    ({"action_request": "unknown"}, False),
    ({"remaining_request": "what is the price"}, False),
    ({"contact_intent": "callback"}, False),
    ({"decision": "close"}, False),
    ({"close_verified": True}, False),
    ({"wait_for_caller": True}, False),
])
def test_only_a_turn_with_nothing_to_do_is_plain(change, plain):
    assert plain_control_turn({**PLAIN, **change}) is plain
    assert plain_control_turn(None) is False


async def _turn(monkeypatch, decision, *, draft_text="Draft reply about the cards.", normal_text="Normal reply.", lookup=None,
                transcript="okay, sounds good"):
    from server.call import call_context
    from server.config.env import get_settings
    from server.providers.base import StageSelection

    cid = str(uuid.uuid4())
    ctx = SimpleNamespace(
        call_id=cid, session_id=cid, tenant_id=None, agent_id="agent", started_at=datetime.now(timezone.utc),
        components={}, status="active", end_reason=None, pipeline="composed_voice", agent_hangup_armed=False,
        call_end_policy=None, barge_in_flight=False, last_stt_partial_at=None, contact_preference="none",
        compiled_brain_text="--- BUSINESS ---\nVisiting cards cost 25 rupees each.",
        resolved_stack=SimpleNamespace(language="en-IN", llm=StageSelection(provider="sarvam", model="m", config={})),
    )
    replies: list[bool] = []
    seen_control: list[object] = []

    async def classify(**_kwargs):
        await asyncio.sleep(DELAY)
        return dict(decision)

    async def stream(**kwargs):
        speculative = kwargs.get("speculative_speech_only", False)
        replies.append(speculative)
        # The draft must never see the decision; the normal reply always does.
        seen_control.append(None if speculative else kwargs["ctx"].turn_control)
        await asyncio.sleep(DELAY)
        text = draft_text if speculative else normal_text
        yield {"delta": text}
        yield {"done": True, "text": text, "finish_reason": "stop", "response_contract": "speech_text"}

    monkeypatch.setattr(call_context, "get", lambda identifier: ctx if identifier == cid else None)
    monkeypatch.setattr(close_classifier, "start_close_classification", lambda **kw: asyncio.create_task(classify(**kw)))
    monkeypatch.setattr(close_classifier, "previous_agent_line", lambda _: "Anything else?")
    monkeypatch.setattr("server.call.business_answer_plan.resolve_business_answers",
                        lookup or AsyncMock(return_value=[{"question": "price", "status": "stated"}]))
    monkeypatch.setattr("server.call.language_switch.language_check_due", lambda *_a, **_k: False)
    monkeypatch.setattr(live_turn_orchestrator, "_stream_llm", stream)
    monkeypatch.setattr(live_turn_orchestrator, "_memory_blocks", AsyncMock(return_value=(None, None)))
    monkeypatch.setattr(live_turn_orchestrator, "_maybe_build_live_input", lambda **_: [])
    monkeypatch.setattr(live_turn_orchestrator, "_after_assistant", AsyncMock())
    monkeypatch.setenv("ENABLE_CALL_ARCHIVE", "false")
    get_settings.cache_clear()
    started = time.perf_counter()
    try:
        chunks = [chunk async for chunk in live_turn_orchestrator.handle_user_turn_stream(
            transcript=transcript, call_id=cid, session_id=cid, language_code="en-IN")]
    finally:
        get_settings.cache_clear()
    elapsed = time.perf_counter() - started
    done = next(chunk for chunk in reversed(chunks) if chunk.get("done"))
    return done, replies, seen_control, elapsed


@pytest.mark.asyncio
async def test_plain_turn_uses_the_draft_and_saves_a_model_round(monkeypatch):
    done, replies, _, elapsed = await _turn(monkeypatch, PLAIN)
    assert done["text"] == "Draft reply about the cards."
    assert replies == [True], "a plain turn must not ask the reply model twice"
    # classifier and draft ran together: ~1 round, not 2.
    assert elapsed < DELAY * 1.8, elapsed


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    {"action_request": "write"},
    {"remaining_request": "what is the price"},
    {"contact_intent": "callback"},
])
async def test_any_other_turn_discards_the_draft_and_takes_the_normal_path(monkeypatch, change):
    decision = {**PLAIN, **change}
    done, replies, seen_control, _ = await _turn(monkeypatch, decision)
    assert done["text"] == "Normal reply."
    assert replies == [True, False]
    # The normal reply is asked with the final decision in place.
    assert seen_control[-1] == decision


@pytest.mark.asyncio
async def test_empty_draft_falls_back_to_the_normal_reply(monkeypatch):
    done, replies, _, _ = await _turn(monkeypatch, PLAIN, draft_text="")
    assert done["text"] == "Normal reply."
    assert replies == [True, False]


@pytest.mark.asyncio
async def test_business_lookup_runs_alongside_the_classifier(monkeypatch):
    lookup_started = []

    async def lookup(ctx, caller):
        lookup_started.append(time.perf_counter())
        await asyncio.sleep(DELAY)
        return [{"question": "price", "status": "stated"}]

    began = time.perf_counter()
    done, _, _, elapsed = await _turn(monkeypatch, {**PLAIN, "remaining_request": "what is the price"}, lookup=lookup,
                                      transcript="what is the price of the cards?")
    assert done["text"] == "Normal reply."
    assert lookup_started and lookup_started[0] - began < DELAY / 2, "lookup waited for the classifier"
    # classifier ∥ lookup, then the reply: two rounds, not three.
    assert elapsed < DELAY * 2.8, elapsed


@pytest.mark.asyncio
async def test_speech_only_never_selects_or_runs_an_action():
    orchestrator = live_turn_orchestrator
    selection = AsyncMock()

    async def speech(**_kwargs):
        yield {"done": True, "text": "Okay."}

    original_speech, original_turn = orchestrator._stream_composed_speech, orchestrator._stream_composed_turn
    orchestrator._stream_composed_speech = speech
    orchestrator._stream_composed_turn = selection
    try:
        chunks = [chunk async for chunk in orchestrator._composed_tool_turn(
            ctx=SimpleNamespace(turn_control={"action_request": "write"}),
            adapter=SimpleNamespace(selects_tools_without_schema=True),
            llm_sel=SimpleNamespace(provider="sarvam", model="m"), stream_kwargs={}, messages=[],
            tool_schemas=[{"name": "CREATE_ORDER"}], call_id=None, record_request_usage=lambda _c: None,
            allow_retry=False, speech_only=True,
        )]
    finally:
        orchestrator._stream_composed_speech, orchestrator._stream_composed_turn = original_speech, original_turn
    assert [chunk["text"] for chunk in chunks if chunk.get("done")] == ["Okay."]
    selection.assert_not_called()
