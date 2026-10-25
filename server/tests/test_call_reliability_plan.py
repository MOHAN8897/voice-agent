"""Regression corpus for the 2026-10-25 call-reliability plan.

Reproduces the two archived composed calls that ended without a reply (the
initial tool-offered request bypassed the shared token floor and its single
retry) and the wedding-card call whose alternate-product question was closed
as a refusal. Transcripts are redacted of carrier and phone metadata.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import server.providers
from server.brain.brain_prompt_validate import validate_rendered_brain
from server.call.close_decision import meaningful_remaining_request
from server.call.end_call_validate import validate_end_call
from server.call.order_confirmation import CONFIRM_ORDER_TOOL
from server.providers.base import StageSelection
from server.providers.llm_protocol import IncompleteTurnError
from server.services.pstn_technical_fallback import CALL_BACK, fallback_text
from server.services.pstn_voice_core import PstnVoiceLoop

import server.call.live_turn_orchestrator as orchestrator_module
from server.call.live_turn_orchestrator import LiveTurnOrchestrator

#: Verbatim caller turns from the two 2026-10-25 composed calls that failed
#: with ``finish_reason=length`` and ``retry_used=false`` before delivering a
#: reply. No personal data is carried in the transcript itself.
ARCHIVED_TURNS = (
    ("అవును. ఆ ఉందండి నాకు ఉంది.", "అవును, చెప్పండి."),
    (
        "అదే వెడ్డింగ్ కార్డ్స్ చేస్తారా మీ దగ్గర ఎంత ప్రైసింగ్ ఉన్నాయి చెప్పగలరా?",
        "అవును, వెడ్డింగ్ కార్డ్స్ చేస్తాము. ధర వివరాలు చెప్తాను.",
    ),
)


def _composed_ctx() -> SimpleNamespace:
    return SimpleNamespace(
        pipeline="composed_voice",
        tenant_id="tenant-1",
        agent_id="agent-1",
        call_id=None,
        status="active",
        agent_hangup_armed=False,
        barge_in_flight=False,
        last_stt_partial_at=None,
        call_end_policy=None,
        callback_request_text="",
        callback_close_phase="idle",
        resolved_stack=SimpleNamespace(
            llm=StageSelection(
                "sarvam", "sarvam-105b-conversations", {"api_mode": "chat_completions_v1"}
            )
        ),
    )


def _install_composed_adapter(monkeypatch, adapter) -> None:
    registry = SimpleNamespace(
        get_llm=lambda provider: adapter if provider == "sarvam" else pytest.fail(provider),
        is_provider_enabled=lambda *_: True,
        is_model_allowed=lambda *_: True,
    )
    monkeypatch.setattr(server.providers, "get_provider_registry", lambda: registry)
    monkeypatch.setattr(
        orchestrator_module,
        "get_settings",
        lambda: SimpleNamespace(
            use_provider_registry=True,
            composed_first_attempt_max_tokens=1280,
            composed_retry_max_tokens=2560,
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("transcript,reply", ARCHIVED_TURNS)
async def test_archived_call_recovers_when_the_initial_tool_turn_stops_early(
    monkeypatch, transcript, reply
):
    """Route-level proof: offering CONFIRM_ORDER must not bypass the budget.

    The two archived calls reached the tool-offering request, where no budget
    was set, so Sarvam used its 320-token default, stopped at ``length`` and
    the call closed without a reply. The initial request must use the same
    first-attempt floor and the same single retry as every other composed turn.
    """
    calls: list[int | None] = []

    class Adapter:
        provider_id = "sarvam"

        async def stream_structured_turn(self, *, input_messages, schema, **kwargs):
            calls.append(kwargs.get("max_output_tokens"))
            if len(calls) == 1:
                yield {"delta": '{"spoken_response": "'}
                raise IncompleteTurnError(
                    provider="sarvam",
                    finish_reason="length",
                    partial_text='{"spoken_response": "',
                    usage={"input_tokens": 900, "output_tokens": 320},
                )
            yield {"delta": reply}
            yield {
                "done": True,
                "text": reply,
                "finish_reason": "stop",
                "usage": {"input_tokens": 900, "output_tokens": 40},
            }

    _install_composed_adapter(monkeypatch, Adapter())
    orchestrator = LiveTurnOrchestrator()
    monkeypatch.setattr(
        orchestrator,
        "_load_composed_tenant_tools",
        AsyncMock(return_value=[CONFIRM_ORDER_TOOL]),
    )

    events = [
        event
        async for event in orchestrator._stream_llm(
            ctx=_composed_ctx(),
            transcript=transcript,
            language_code="te-IN",
            call_id=None,
            structured_live_turn=True,
            input_messages=[{"role": "user", "content": transcript}],
            max_output_tokens=None,
        )
    ]

    assert calls == [1280, 2560]
    assert events[-1]["done"] is True
    assert events[-1]["text"] == reply
    assert events[-1]["retry_count"] == 1


@pytest.mark.parametrize(
    "language,reason,user_text",
    [
        ("en-IN", "goodbye", "Tell me the price"),
        ("en-IN", "goodbye", "I want the wedding cards"),
        ("en-IN", "goodbye", "Okay, go ahead with the wedding cards"),
        ("te-IN", "goodbye", "అవును, వెడ్డింగ్ కార్డ్స్ వివరాలు చెప్పండి."),
        ("te-IN", "goodbye", "అవును. ఆ ఉందండి నాకు ఉంది."),
        (
            "en-IN",
            "not_interested",
            "I do not want visiting cards but I want wedding cards, tell me the price",
        ),
    ],
)
def test_affirmative_or_product_request_cannot_authorize_a_close(
    language, reason, user_text
):
    """A tool call or a model quote is not consent when the caller is still asking."""
    decision = validate_end_call(
        {
            "should_end": True,
            "reason": reason,
            "farewell": "Bye.",
            "evidence": user_text,
            "remaining_request": "",
        },
        user_text=user_text,
        language=language,
        completed_turns=2,
        tool_sourced=True,
    )

    assert decision.accepted is False


def test_scoped_refusal_is_not_an_overall_refusal():
    from server.call.end_call_validate import caller_not_interested

    text = "I do not want visiting cards but I want wedding cards, tell me the price"
    assert caller_not_interested(text) is False

    decision = validate_end_call(
        {"should_end": True, "reason": "not_interested", "farewell": "Okay."},
        user_text=text,
        language="en-IN",
    )
    assert decision.accepted is False


@pytest.mark.parametrize(
    "text",
    [
        "Do you make wedding cards",
        "Does your team print wedding cards",
        "Is there a minimum order",
    ],
)
def test_unpunctuated_information_question_cannot_authorize_a_close(text):
    decision = validate_end_call(
        {
            "should_end": True,
            "reason": "not_interested",
            "farewell": "Okay.",
            "evidence": text,
        },
        user_text=text,
        language="en-IN",
    )

    assert decision.accepted is False


@pytest.mark.parametrize("text", ["why", "ధర", "ఎంత", "price"])
def test_short_remaining_request_is_still_a_request(text):
    assert meaningful_remaining_request(text) is True


def test_short_remaining_request_blocks_a_refusal_close():
    decision = validate_end_call(
        {
            "should_end": True,
            "reason": "not_interested",
            "farewell": "Okay.",
            "remaining_request": "ధర",
        },
        user_text="I do not want it",
        language="en-IN",
    )

    assert decision.accepted is False
    assert decision.reject_code == "remaining_request"


class _TurnTts:
    """Minimal TTS session: records text and optionally emits audio frames."""

    def __init__(self, loop: PstnVoiceLoop):
        self._loop = loop
        self._closed = False

    @property
    def has_sent_text(self) -> bool:
        return False

    @property
    def had_error(self) -> bool:
        return False

    @property
    def failure_evidence(self) -> dict | None:
        return None

    @property
    def audio_emitted(self) -> bool:
        return False

    async def prepare_for_turn(self) -> None:
        return None

    async def open(self, **_kwargs) -> None:
        return None

    async def send_text(self, text: str) -> None:
        await self._loop._emit_agent_wire(b"\x00" * 320)

    async def finish(self) -> None:
        return None

    async def end_turn(self) -> None:
        return None

    async def close(self) -> None:
        self._closed = True


@pytest.mark.asyncio
async def test_exhausted_model_failure_speaks_an_honest_technical_line(monkeypatch):
    """An unrecovered stop is a technical failure, not a normal goodbye."""
    spoken: list[str] = []
    loop = PstnVoiceLoop(
        session_id="exhausted",
        call_id="c-exhausted",
        on_agent_wire=AsyncMock(),
        stack_override={"pipeline": "composed_voice", "language": "te-IN"},
    )
    session = _TurnTts(loop)

    async def failed_stream(**_kwargs):
        raise IncompleteTurnError(
            provider="sarvam",
            finish_reason="length",
            partial_text="",
            retry_used=True,
        )
        yield  # pragma: no cover - keeps this an async generator

    monkeypatch.setattr(
        "server.services.pstn_turn_tts.PstnTurnTtsSession", lambda _voice: session
    )
    monkeypatch.setattr(
        "server.call.live_turn_orchestrator.live_turn_orchestrator.handle_user_turn_stream",
        failed_stream,
    )
    monkeypatch.setattr(
        "server.services.pstn_voice_core.pstn_turn_runtime", lambda *_a, **_k: {}
    )
    monkeypatch.setattr(
        "server.services.saas.session_failure_log.record_session_failure",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        "server.services.turn_failure_log.record_turn_failure", AsyncMock()
    )
    monkeypatch.setattr(
        "server.call.call_ledger.call_ledger.append_assistant_turn", AsyncMock()
    )
    monkeypatch.setattr(loop, "_finish_agent_hangup", AsyncMock())
    monkeypatch.setattr(loop, "_play_technical_fallback_and_hangup", AsyncMock())

    original_send = _TurnTts.send_text

    async def capture_send(self, text):
        spoken.append(text)
        await original_send(self, text)

    monkeypatch.setattr(_TurnTts, "send_text", capture_send)

    await loop._run_turn("అదే వెడ్డింగ్ కార్డ్స్ చేస్తారా? ధర ఎంత?")
    await loop.close()

    assert spoken == [fallback_text("te-IN", CALL_BACK)]
    assert spoken[0] != "ధన్యవాదాలు. నమస్కారం."  # not a normal farewell
    loop._finish_agent_hangup.assert_awaited_once()


def test_rendered_brain_flags_a_locale_pack_that_contradicts_the_session():
    brain = (
        "@language: te-IN\n"
        "Language: te-IN\n"
        "Speak only Telugu.\n"
        "Use the selected en-IN language pack.\n"
    )

    issues = validate_rendered_brain(brain, "te-IN")

    assert any("en-IN" in issue for issue in issues)


def test_rendered_brain_flags_duplicate_call_end_policy_sections():
    brain = (
        "@language: te-IN\nLanguage: te-IN\nSpeak only Telugu.\n"
        "--- CALL END POLICY ---\nClose only on an explicit goodbye.\n"
        "--- CALL END POLICY ---\nClose whenever the caller answers a question.\n"
    )

    issues = validate_rendered_brain(brain, "te-IN")

    assert any("CALL END POLICY" in issue and "duplicate" in issue.lower() for issue in issues)


def test_rendered_brain_flags_a_model_owned_farewell():
    brain = (
        "@language: te-IN\nLanguage: te-IN\nSpeak only Telugu.\n"
        "At the end of every call, say goodbye in your own words.\n"
    )

    issues = validate_rendered_brain(brain, "te-IN")

    assert any("farewell" in issue.lower() for issue in issues)
