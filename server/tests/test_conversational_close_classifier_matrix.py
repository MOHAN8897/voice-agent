"""Comprehensive simulative test matrix for conversational close classification.

Validates:
1. Speech and call control separation: model plain speech remains simple;
   close decision is evaluated via the lightweight classifier step.
2. Context-aware conversational endings without regex phrase lists:
   - "అంతే అంతే థ్యాంక్ యూ" ("that's all, thank you") -> real ending (1 farewell, 1 hangup)
   - "సరే ఓకే థాంక్స్" -> real ending (1 farewell, 1 hangup)
   - "that's all I needed" -> real ending (1 farewell, 1 hangup)
   - "thanks" in the middle of a call -> non-ending, call stays open
   - "thanks, but one more question" -> non-ending, call stays open
3. Multilingual coverage: Telugu, Hindi, English, Tamil, Kannada.
4. Server gatekeeper facts verification:
   - Open question from caller -> blocked
   - Unfinished task / pending tool result -> blocked
   - Incomplete caller turn / caller still speaking -> blocked
   - Polite thanks alone without prior conclusion -> blocked
5. Server owns the farewell: model goodbye text is never spoken;
   the approved server template farewell is spoken.
6. Carrier hangup verification:
   - Hangup logs reason="agent_ended", never "ws_disconnect".
   - Quiet-time fallback and farewell playback completion are respected.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from server.call.call_end_policy import server_farewell_for
from server.call.close_call_executor import execute_agent_close
from server.call.close_classifier import (
    close_turn_plausible,
    parse_classifier_output,
)
from server.call.end_call_validate import validate_end_call
from server.call.live_turn_orchestrator import live_turn_orchestrator
from server.config.env import get_settings
from server.prompts.agent_voice_rules import CALL_END_FAREWELLS


# ---------------------------------------------------------------------------
# 1. Classifier Turn Plausibility & Parsing Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "transcript,expected_plausible",
    [
        ("అంతే అంతే థ్యాంక్ యూ", True),
        ("సరే ఓకే థాంక్స్", True),
        ("that's all I needed", True),
        ("thanks", True),
        ("thanks, but one more question", True),  # <= 16 words, no ?, passes prefilter to model
        ("Can you tell me the price?", False),  # Question mark -> not plausible ending
        ("What about the warranty and delivery timeline?", False),
        ("This is a very long description explaining my whole situation and asking many questions about everything in detail", False),  # > 16 words
    ],
)
def test_close_turn_plausible_filtering(transcript: str, expected_plausible: bool):
    assert close_turn_plausible(transcript) == expected_plausible


@pytest.mark.parametrize(
    "raw_json,transcript,expected_decision,expected_reason",
    [
        (
            {"decision": "close", "reason": "done", "evidence": "అంతే అంతే థ్యాంక్ యూ"},
            "అంతే అంతే థ్యాంక్ యూ",
            "close",
            "goal_complete",
        ),
        (
            {"decision": "close", "reason": "goodbye", "evidence": "సరే ఓకే థాంక్స్"},
            "సరే ఓకే థాంక్స్",
            "close",
            "goodbye",
        ),
        (
            {"decision": "close", "reason": "done", "evidence": "that's all I needed"},
            "that's all I needed",
            "close",
            "goal_complete",
        ),
        (
            {"decision": "close", "reason": "completed", "evidence": "बस इतना ही धन्यवाद"},
            "बस इतना ही धन्यवाद",
            "close",
            "goal_complete",
        ),
        (
            {"decision": "close", "reason": "goodbye", "evidence": "அவ்வளவுதான் நன்றி"},
            "அவ்வளவுதான் நன்றி",
            "close",
            "goodbye",
        ),
        (
            {"decision": "close", "reason": "satisfied", "evidence": "ಇಷ್ಟೇ ಸಾಕು ಧನ್ಯವಾದಗಳು"},
            "ಇಷ್ಟೇ ಸಾಕು ಧನ್ಯವಾದಗಳು",
            "close",
            "goal_complete",
        ),
        (
            {"decision": "continue", "reason": "none", "evidence": "thanks"},
            "thanks",
            None,  # parse_classifier_output returns None for continue
            None,
        ),
        (
            {"decision": "continue", "reason": "question", "evidence": "one more question"},
            "thanks, but one more question",
            None,
            None,
        ),
        # Paraphrased quote that does not match transcript should be rejected
        (
            {"decision": "close", "reason": "done", "evidence": "invented quote not in text"},
            "అంతే అంతే థ్యాంక్ యూ",
            None,
            None,
        ),
    ],
)
def test_parse_classifier_output(raw_json, transcript, expected_decision, expected_reason):
    parsed = parse_classifier_output(raw_json, transcript)
    if expected_decision is None:
        assert parsed is None
    else:
        assert parsed is not None
        assert parsed["decision"] == expected_decision
        assert parsed["reason"] == expected_reason
        assert parsed["evidence"] in transcript or transcript in parsed["evidence"]


# ---------------------------------------------------------------------------
# 2. Server Gatekeeper Validation Tests Across All Languages
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "language,user_text,reason",
    [
        ("te-IN", "అంతే అంతే థ్యాంక్ యూ", "goal_complete"),
        ("te-IN", "సరే ఓకే థాంక్స్", "goodbye"),
        ("en-IN", "that's all I needed", "goal_complete"),
        ("hi-IN", "बस इतना ही धन्यवाद", "goal_complete"),
        ("ta-IN", "அவ்வளவுதான் நன்றி", "goodbye"),
        ("kn-IN", "ಇಷ್ಟೇ ಸಾಕು ಧನ್ಯವಾದಗಳು", "goal_complete"),
    ],
)
def test_gatekeeper_approves_real_conversational_endings(language: str, user_text: str, reason: str):
    proposal = {
        "decision": "close",
        "reason": reason,
        "evidence": user_text,
    }
    decision = validate_end_call(
        proposal,
        user_text=user_text,
        language=language,
        call_status="active",
        classifier_sourced=True,
    )
    assert decision.accepted is True
    assert decision.should_end is True
    assert decision.reason == reason
    expected_farewell = CALL_END_FAREWELLS[language]
    assert decision.farewell == expected_farewell


def test_gatekeeper_rejects_bare_thanks_in_middle_of_call():
    """A bare 'thanks' in the middle of a call without prior agent conclusion stays open."""
    proposal = {
        "decision": "close",
        "reason": "goodbye",
        "evidence": "thanks",
    }
    decision = validate_end_call(
        proposal,
        user_text="thanks",
        language="en-IN",
        call_status="active",
        spoken_text="The fee is five thousand rupees.",  # Middle of call answer
        classifier_sourced=True,
    )
    assert decision.accepted is False
    assert decision.should_end is False
    assert decision.reject_code == "no_evidence"


def test_gatekeeper_rejects_thanks_with_one_more_question():
    """'thanks, but one more question' must never close the call."""
    proposal = {
        "decision": "close",
        "reason": "goodbye",
        "evidence": "thanks",
    }
    decision = validate_end_call(
        proposal,
        user_text="thanks, but one more question",
        language="en-IN",
        call_status="active",
        classifier_sourced=True,
    )
    assert decision.accepted is False
    assert decision.should_end is False
    assert decision.reject_code == "caller_engaged"


def test_gatekeeper_rejects_when_caller_asks_question():
    """An open question from the caller blocks close even if an ending phrase is attached."""
    proposal = {
        "decision": "close",
        "reason": "goodbye",
        "evidence": "thank you",
    }
    decision = validate_end_call(
        proposal,
        user_text="What is the timing? thank you",
        language="en-IN",
        call_status="active",
        classifier_sourced=True,
    )
    assert decision.accepted is False
    assert decision.reject_code == "user_asked_question"


def test_gatekeeper_rejects_when_pending_tool_result_unfinished():
    """An unfinished task or pending tool result blocks close."""
    proposal = {
        "decision": "close",
        "reason": "goal_complete",
        "evidence": "that's all I needed",
    }
    decision = validate_end_call(
        proposal,
        user_text="that's all I needed",
        language="en-IN",
        call_status="active",
        pending_tool_result=True,  # Server is still waiting for external tool result
        classifier_sourced=True,
    )
    assert decision.accepted is False
    assert decision.reject_code == "tool_result_pending"


def test_gatekeeper_rejects_when_caller_is_still_talking():
    """Incomplete turn / STT active within 400ms blocks premature hangup."""
    proposal = {
        "decision": "close",
        "reason": "goal_complete",
        "evidence": "that's all I needed",
    }
    decision = validate_end_call(
        proposal,
        user_text="that's all I needed",
        language="en-IN",
        call_status="active",
        last_stt_partial_at=100.0,
        now=100.2,  # 200ms elapsed (< 400ms)
        classifier_sourced=True,
    )
    assert decision.accepted is False
    assert decision.reject_code == "caller_still_talking"


# ---------------------------------------------------------------------------
# 3. Live Turn Orchestrator Full Turn Simulation
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _disable_archive_for_tests(monkeypatch):
    monkeypatch.setenv("ENABLE_CALL_ARCHIVE", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_live_turn_simulation_telugu_ending_replaces_speech_with_server_farewell():
    """Simulate Telugu 'అంతే అంతే థ్యాంక్ యూ' turn:
    - Classifier returns close
    - Live speech replaces model text with server farewell
    - Held deltas cleared, replace_speech=True
    """
    model_speech = "సరే ధన్యవాదాలు వీడ్కోలు"  # Model might output goodbye text
    classifier_result = {
        "decision": "close",
        "reason": "goal_complete",
        "evidence": "అంతే అంతే థ్యాంక్ యూ",
        "close_verified": True,
        "contact_verified": True,
    }

    async def fake_stream_llm(**_kwargs):
        # Plain speech LLM streaming text
        yield {"delta": model_speech}
        yield {"done": True, "text": model_speech}

    async def fake_classify(*_args, **_kwargs):
        return classifier_result

    ctx = SimpleNamespace(
        pipeline="composed_voice",
        status="active",
        agent_hangup_armed=False,
        barge_in_flight=False,
        last_stt_partial_at=None,
        call_end_policy=None,
        resolved_stack=SimpleNamespace(
            llm=SimpleNamespace(provider="sarvam", model="sarvam-2b")
        ),
    )

    with (
        patch("server.call.live_turn_orchestrator.call_context.get", return_value=ctx),
        patch.object(live_turn_orchestrator, "_stream_llm", fake_stream_llm),
        patch.object(live_turn_orchestrator, "_maybe_build_live_input", return_value=[{"role": "user", "content": "test"}]),
        patch.object(live_turn_orchestrator, "_memory_blocks", AsyncMock(return_value=(None, None))),
        patch("server.call.close_classifier.classifier_available", return_value=True),
        patch("server.call.close_classifier.classify_close_turn", fake_classify),
    ):
        chunks = [
            chunk
            async for chunk in live_turn_orchestrator.handle_user_turn_stream(
                transcript="అంతే అంతే థ్యాంక్ యూ",
                language_code="te-IN",
                session_id="test-sim-te",
                call_id="call-te-1",
            )
        ]

    done_chunk = next(c for c in chunks if c.get("done"))
    assert done_chunk["end_call"]["should_end"] is True
    assert done_chunk["end_call"]["reason"] == "goal_complete"
    # Speech MUST be replaced with server farewell
    assert done_chunk["replace_speech"] is True
    assert done_chunk["text"] == CALL_END_FAREWELLS["te-IN"]
    assert model_speech not in done_chunk["text"]


@pytest.mark.asyncio
async def test_live_turn_simulation_english_ending_replaces_speech_with_server_farewell():
    """Simulate English 'that's all I needed' turn."""
    model_speech = "Okay, have a good day."
    classifier_result = {
        "decision": "close",
        "reason": "goal_complete",
        "evidence": "that's all I needed",
        "close_verified": True,
        "contact_verified": True,
    }

    async def fake_stream_llm(**_kwargs):
        yield {"delta": model_speech}
        yield {"done": True, "text": model_speech}

    async def fake_classify(*_args, **_kwargs):
        return classifier_result

    ctx = SimpleNamespace(
        pipeline="composed_voice",
        status="active",
        agent_hangup_armed=False,
        barge_in_flight=False,
        last_stt_partial_at=None,
        call_end_policy=None,
        resolved_stack=SimpleNamespace(
            llm=SimpleNamespace(provider="sarvam", model="sarvam-2b")
        ),
    )

    with (
        patch("server.call.live_turn_orchestrator.call_context.get", return_value=ctx),
        patch.object(live_turn_orchestrator, "_stream_llm", fake_stream_llm),
        patch.object(live_turn_orchestrator, "_maybe_build_live_input", return_value=[{"role": "user", "content": "test"}]),
        patch.object(live_turn_orchestrator, "_memory_blocks", AsyncMock(return_value=(None, None))),
        patch("server.call.close_classifier.classifier_available", return_value=True),
        patch("server.call.close_classifier.classify_close_turn", fake_classify),
    ):
        chunks = [
            chunk
            async for chunk in live_turn_orchestrator.handle_user_turn_stream(
                transcript="that's all I needed",
                language_code="en-IN",
                session_id="test-sim-en",
                call_id="call-en-1",
            )
        ]

    done_chunk = next(c for c in chunks if c.get("done"))
    assert done_chunk["end_call"]["should_end"] is True
    assert done_chunk["replace_speech"] is True
    assert done_chunk["text"] == CALL_END_FAREWELLS["en-IN"]


@pytest.mark.asyncio
async def test_live_turn_simulation_mid_call_thanks_keeps_call_open():
    """Simulate 'thanks' in the middle of a call:
    - Classifier returns None (continue)
    - Speech is NOT replaced by farewell
    - should_end is False, call continues
    """
    model_speech = "You are welcome. Is there anything else I can help you with?"

    async def fake_stream_llm(**_kwargs):
        yield {"delta": model_speech}
        yield {"done": True, "text": model_speech}

    async def fake_classify(*_args, **_kwargs):
        # Classifier returns None for continue
        return None

    ctx = SimpleNamespace(
        pipeline="composed_voice",
        status="active",
        agent_hangup_armed=False,
        barge_in_flight=False,
        last_stt_partial_at=None,
        call_end_policy=None,
        resolved_stack=SimpleNamespace(
            llm=SimpleNamespace(provider="sarvam", model="sarvam-2b")
        ),
    )

    with (
        patch("server.call.live_turn_orchestrator.call_context.get", return_value=ctx),
        patch.object(live_turn_orchestrator, "_stream_llm", fake_stream_llm),
        patch.object(live_turn_orchestrator, "_maybe_build_live_input", return_value=[{"role": "user", "content": "test"}]),
        patch.object(live_turn_orchestrator, "_memory_blocks", AsyncMock(return_value=(None, None))),
        patch("server.call.close_classifier.classifier_available", return_value=True),
        patch("server.call.close_classifier.classify_close_turn", fake_classify),
    ):
        chunks = [
            chunk
            async for chunk in live_turn_orchestrator.handle_user_turn_stream(
                transcript="thanks",
                language_code="en-IN",
                session_id="test-sim-thanks",
                call_id="call-en-2",
            )
        ]

    done_chunk = next(c for c in chunks if c.get("done"))
    assert done_chunk["end_call"]["should_end"] is False
    assert done_chunk["text"] == model_speech
    assert "Goodbye" not in done_chunk["text"]


# ---------------------------------------------------------------------------
# 4. Carrier Hangup Execution & Logging Verification
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_carrier_hangup_logs_agent_ended_not_ws_disconnect(monkeypatch):
    """When a real ending occurs:
    1. execute_agent_close waits for playback to finish
    2. Quiet-time pause is observed
    3. Recheck confirms caller has not resumed
    4. Provider hangup is invoked with reason='agent_ended', NOT 'ws_disconnect'
    """
    events = []
    playing = {"on": True}
    provider_hangup = AsyncMock()
    monkeypatch.setattr("server.utils.logger.log_pstn", lambda phase, **fields: events.append((phase, fields)))
    monkeypatch.setattr("server.call.call_lifecycle_service.call_lifecycle_service.end", AsyncMock())

    def is_playing():
        return playing["on"]

    async def drain_audio():
        await asyncio.sleep(0.02)
        playing["on"] = False

    monkeypatch.setattr("server.call.natural_hangup.HANGUP_TRAIL_SILENCE_SEC", 0.02)

    asyncio.create_task(drain_audio())

    result = await execute_agent_close(
        call_id="call-vobiz-test",
        reason="goal_complete",
        spoke_farewell=True,
        is_playing=is_playing,
        on_provider_hangup=provider_hangup,
    )
    if result.background_task:
        await result.background_task

    assert result.cancelled is False
    assert result.reason == "goal_complete"
    provider_hangup.assert_awaited_once()
    disconnect = next(fields for phase, fields in events if phase == "hangup.disconnect")
    assert disconnect["initiator"] == "agent"
    assert disconnect["outcome"] == "agent_ended"
    assert disconnect["reason"] == "goal_complete"
