"""Exercise semantic close decisions through the real server handoff."""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.call import close_classifier
from server.call.call_end_policy import server_farewell_for
from server.call.close_decision import evidence_matches
from server.call.end_call_validate import validate_end_call
from server.call.live_turn_orchestrator import live_turn_orchestrator

CLOSE_CASES = [
    ("te-IN", "అంతే అంతే థ్యాంక్ యూ", True),
    ("te-IN", "సరే ఓకే థాంక్స్", True),
    ("te-IN", "థాంక్స్", False),
    ("te-IN", "థాంక్స్ కానీ ఇంకో ప్రశ్న ఉంది", False),
    ("en-IN", "that's all I needed", True),
    ("en-IN", "thanks", False),
    ("en-IN", "thanks, but one more question", False),
    ("hi-IN", "बस इतना ही धन्यवाद", True),
    ("hi-IN", "धन्यवाद", False),
    ("hi-IN", "धन्यवाद, लेकिन एक और सवाल है", False),
    ("ta-IN", "அவ்வளவுதான் நன்றி", True),
    ("ta-IN", "நன்றி", False),
    ("ta-IN", "நன்றி, ஆனால் இன்னொரு கேள்வி இருக்கு", False),
    ("kn-IN", "ಇಷ್ಟೇ ಸಾಕು ಧನ್ಯವಾದಗಳು", True),
    ("kn-IN", "ಧನ್ಯವಾದಗಳು", False),
    ("kn-IN", "ಧನ್ಯವಾದಗಳು, ಆದರೆ ಇನ್ನೊಂದು ಪ್ರಶ್ನೆ ಇದೆ", False),
]


@pytest.mark.parametrize("raw", [
    {"decision": "close", "reason": "done"},
    {"decision": "close", "reason": "unrecognized", "evidence": "that's all"},
    {"decision": "close", "reason": "done", "evidence": "that's all please stop calling forever"},
])
def test_classifier_rejects_missing_or_invented_evidence(raw):
    assert close_classifier.parse_classifier_output(raw, "that's all") is None


def test_quote_cannot_add_words_to_the_callers_turn():
    assert not evidence_matches("no I want to end the call", "no")


@pytest.mark.parametrize("speech", [
    "Is there anything else I can help you with?",
    "Please tell me your name and phone number.",
])
def test_unspoken_model_followup_cannot_veto_semantic_completion(speech):
    user = "అంతే అంతే థ్యాంక్ యూ"
    result = validate_end_call(
        {"decision": "close", "reason": "goal_complete", "evidence": user},
        user_text=user, spoken_text=speech, language="te-IN", classifier_sourced=True,
    )
    assert result.accepted, result.reject_code


def test_current_semantic_end_supersedes_stale_callback_evidence(monkeypatch):
    ctx = SimpleNamespace(
        session_id="stale-callback", status="active", agent_hangup_armed=False,
        callback_request_text="Take my details and call me tomorrow", callback_close_phase="collecting_name",
        callback_name="", callback_phone="", callback_when="",
        call_end_policy=None,
    )
    monkeypatch.setattr("server.call.live_turn_orchestrator.call_context.get", lambda _: ctx)
    user = "అంతే అంతే థ్యాంక్ యూ"
    result = live_turn_orchestrator._gate_end_call(
        {"decision": "close", "reason": "goal_complete", "evidence": user},
        transcript=user, language_code="te-IN", call_id="stale-callback",
        classifier_sourced=True,
    )
    assert result["should_end"], result
    assert ctx.callback_request_text == ""


def test_rejected_semantic_close_preserves_callback_state(monkeypatch):
    ctx = SimpleNamespace(
        session_id="pending-callback", status="active", agent_hangup_armed=False,
        callback_request_text="Take my details and call me tomorrow",
        callback_close_phase="collecting_name", pending_tool_result=True,
    )
    monkeypatch.setattr("server.call.live_turn_orchestrator.call_context.get", lambda _: ctx)
    user = "అంతే అంతే థ్యాంక్ యూ"
    result = live_turn_orchestrator._gate_end_call(
        {"decision": "close", "reason": "goal_complete", "evidence": user},
        transcript=user, language_code="te-IN", call_id="pending-callback", classifier_sourced=True,
    )
    assert result["reject_code"] == "tool_result_pending"
    assert ctx.callback_request_text == "Take my details and call me tomorrow"
    assert ctx.callback_close_phase == "collecting_name"


@pytest.mark.asyncio
async def test_classifier_is_cancelled_when_its_turn_is_cancelled(monkeypatch):
    started, stopped = asyncio.Event(), asyncio.Event()
    tasks = []

    async def classify(**_kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    def start(**kwargs):
        task = asyncio.create_task(classify(**kwargs))
        tasks.append(task)
        return task

    async def stream(**_kwargs):
        await started.wait()
        raise asyncio.CancelledError
        yield  # pragma: no cover -- async generator surface

    ctx = SimpleNamespace(
        pipeline="composed_voice", agent_hangup_armed=False,
        resolved_stack=SimpleNamespace(llm=SimpleNamespace(provider="sarvam", model="test")),
    )
    monkeypatch.setattr("server.call.live_turn_orchestrator.call_context.get", lambda _: ctx)
    monkeypatch.setattr(close_classifier, "start_close_classification", start)
    monkeypatch.setattr(live_turn_orchestrator, "_stream_llm", stream)
    monkeypatch.setattr(live_turn_orchestrator, "_memory_blocks", AsyncMock(return_value=(None, None)))
    monkeypatch.setattr(live_turn_orchestrator, "_maybe_build_live_input", lambda **_: [])
    monkeypatch.setattr(live_turn_orchestrator, "_maybe_callback_close_hint", lambda *_, **__: None)
    monkeypatch.setenv("ENABLE_CALL_ARCHIVE", "false")
    from server.config.env import get_settings
    get_settings.cache_clear()
    try:
        with pytest.raises(asyncio.CancelledError):
            async for _ in live_turn_orchestrator.handle_user_turn_stream(
                transcript="అంతే అంతే థ్యాంక్ యూ", call_id="cancel-classifier", session_id="cancel",
            ):
                pass
        await asyncio.sleep(0)
        assert stopped.is_set(), "cancelled turn left a live model request behind"
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        get_settings.cache_clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_external_tool_sets_and_clears_pending_state(monkeypatch, cancel):
    ctx = SimpleNamespace(call_id="pending-tool", tenant_id="tenant", agent_id="agent", pending_tool_result=False)
    observed = []

    async def execute(**_kwargs):
        observed.append(ctx.pending_tool_result)
        if cancel:
            raise asyncio.CancelledError
        return {"status": "error"}

    monkeypatch.setattr("server.services.tool_router.tool_router.route_and_execute", execute)
    kwargs = {
        "ctx": ctx, "messages": [], "allowed_tools": {"HUBSPOT_CREATE_CONTACT"},
        "tool_calls": [{"id": "request-1", "function": {"name": "HUBSPOT_CREATE_CONTACT", "arguments": "{}"}}],
    }
    if cancel:
        with pytest.raises(asyncio.CancelledError):
            await live_turn_orchestrator._execute_composed_tools(**kwargs)
    else:
        await live_turn_orchestrator._execute_composed_tools(**kwargs)
    assert observed == [True], "close gate cannot see the running tool"
    assert ctx.pending_tool_result is False


@pytest.mark.asyncio
async def test_incomplete_address_waits_without_speaking_or_hanging_up(monkeypatch):
    class FragmentAdapter:
        uses_plain_live_speech = True

        async def stream_live_turn(self, **_kwargs):
            yield {"done": True, "text": json.dumps({"decision": "continue", "wait_for_caller": True, "memory_operations": []})}

    result = await run_voice_simulation(monkeypatch, "te-IN", "మాది", False, adapter=FragmentAdapter())
    assert result["spoken"] == []
    assert result["hangup_commands"] == 0


async def run_voice_simulation(monkeypatch, language, user, closing, *, adapter=None, retry_attempt=False, empty_speech=False, recovered_text=""):
    """Real gate, voice loop, executor and lifecycle; substitute speech and carrier."""
    from server.call import call_context
    from server.call.call_ledger import call_ledger
    from server.call.call_lifecycle_service import call_lifecycle_service
    from server.call.call_store import call_store
    from server.config.env import get_settings
    from server.providers.base import StageSelection
    from server.services.pstn_voice_core import PHASE_ENDED, PstnVoiceLoop
    from server.tests.test_pstn_critical_loop import FakeTtsSession

    cid = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    ctx = SimpleNamespace(
        call_id=cid, session_id=cid, tenant_id=None, agent_id="simulation-agent",
        started_at=now, components={}, status="active", end_reason=None,
        pipeline="composed_voice", agent_hangup_armed=False, call_end_policy=None,
        barge_in_flight=False, last_stt_partial_at=None, contact_preference="none",
        resolved_stack=SimpleNamespace(
            language=language,
            llm=StageSelection(provider="sarvam", model="sarvam-105b-conversations", config={}),
        ),
    )
    await call_store.insert({"call_id": cid, "started_at": now, "is_test": True})
    await call_ledger.init(cid, {"call_id": cid, "pipeline": "composed_voice"})

    class DecisionAdapter:
        uses_plain_live_speech = True

        async def stream_live_turn(self, **_kwargs):
            await asyncio.sleep(0)
            yield {"done": True, "text": json.dumps({
                "decision": "close" if closing else "continue",
                "reason": "done" if closing else "none", "evidence": user,
            }), "usage": {}}

    registry = SimpleNamespace(
        is_provider_enabled=lambda *_: True, is_model_allowed=lambda *_: True,
        get_llm=lambda *_: adapter or DecisionAdapter(),
    )
    monkeypatch.setattr("server.providers.get_provider_registry", lambda: registry)
    monkeypatch.setattr(call_context, "get", lambda identifier: ctx if identifier == cid else None)
    monkeypatch.setattr(live_turn_orchestrator, "_memory_blocks", AsyncMock(return_value=(None, None)))
    monkeypatch.setattr(live_turn_orchestrator, "_maybe_build_live_input", lambda **_: [])
    monkeypatch.setattr(live_turn_orchestrator, "_after_assistant", AsyncMock())
    monkeypatch.setattr("server.call.speech_recovery.recover_empty_speech", AsyncMock(return_value=recovered_text))
    previous = {
        "te-IN": ("మీ ప్రశ్నలన్నిటికీ సమాధానం ఇచ్చాను. ఇంకేమైనా వివరాలు కావాలా అండి?", "ఒక్కో సందర్శనకు ధర ఐదు వందల రూపాయలు."),
        "en-IN": ("All your questions have been answered. Is there anything else you need?", "The service costs 500 rupees per visit."),
        "hi-IN": ("आपके सभी सवालों का जवाब मिल गया। क्या और कोई जानकारी चाहिए?", "हर विज़िट की कीमत पाँच सौ रुपये है।"),
        "ta-IN": ("உங்கள் கேள்விகளுக்கு பதில் சொல்லிவிட்டேன். வேறு ஏதாவது தகவல் வேண்டுமா?", "ஒவ்வொரு வருகைக்கும் ஐநூறு ரூபாய் ஆகும்."),
        "kn-IN": ("ನಿಮ್ಮ ಎಲ್ಲ ಪ್ರಶ್ನೆಗಳಿಗೆ ಉತ್ತರ ಕೊಟ್ಟಿದ್ದೇನೆ. ಇನ್ನೇನಾದರೂ ಮಾಹಿತಿ ಬೇಕೇ?", "ಪ್ರತಿ ಭೇಟಿಗೆ ಐದು ನೂರು ರೂಪಾಯಿ ಆಗುತ್ತದೆ."),
    }[language][0 if closing else 1]
    monkeypatch.setattr(close_classifier, "previous_agent_line", lambda _: previous)

    async def speech(**_kwargs):
        if empty_speech:
            yield {"done": True, "text": "", "empty_provider_response": True, "response_contract": "speech_text", "finish_reason": "empty_provider_response"}
            return
        text = "Is there anything else I can help you with?"
        yield {"delta": text}
        yield {"done": True, "text": text, "finish_reason": "stop"}

    monkeypatch.setattr(live_turn_orchestrator, "_stream_llm", speech)
    monkeypatch.setattr(call_lifecycle_service, "_finalize_async", AsyncMock())
    monkeypatch.setattr("server.services.pstn_voice_core.pstn_turn_runtime", lambda *_: {})
    monkeypatch.setattr("server.call.natural_hangup.HANGUP_TRAIL_SILENCE_SEC", 0.01)
    monkeypatch.setenv("ENABLE_CALL_ARCHIVE", "false")
    get_settings.cache_clear()

    class Playback:
        until = 0.0

        def is_active(self):
            return time.monotonic() < self.until

    playback = Playback()
    tts_sessions = []

    class Tts(FakeTtsSession):
        async def finish(self):
            self.finished = True
            playback.until = time.monotonic() + 0.02

    def make_tts(voice):
        tts = Tts(voice)
        tts_sessions.append(tts)
        return tts

    monkeypatch.setattr("server.services.pstn_turn_tts.PstnTurnTtsSession", make_tts)
    voice = PstnVoiceLoop(
        session_id=cid, call_id=cid, on_agent_wire=AsyncMock(), playback=playback,
        stack_override={"language": language},
    )
    if retry_attempt:
        monkeypatch.setattr(voice, "_watched_turn_stream", lambda kwargs: (
            live_turn_orchestrator.handle_user_turn_stream(**kwargs, retry_attempt=True)
        ))
    commands = []

    async def provider_hangup():
        assert not playback.is_active(), "carrier called before farewell playback drained"
        commands.append("hangup")
        # Real carriers can report media disconnect before command acknowledgement.
        await call_lifecycle_service.end(cid, reason="ws_disconnect")

    voice.set_hangup_handler(provider_hangup)
    try:
        await voice._run_turn(user)
        if voice._background_hangup_task:
            await voice._background_hangup_task
        stored = await call_store.get(cid)
        meta = call_ledger.read_meta(cid)
        texts = [text for session in tts_sessions for text in session.texts]
        if closing:
            assert commands == ["hangup"]
            assert texts == [server_farewell_for(language)]
            assert voice._phase == PHASE_ENDED
            assert ctx.agent_hangup_reason in {"goal_complete", "goodbye"}
            assert stored["end_reason"] == ctx.agent_hangup_reason, stored
            assert meta["hangup_outcome"] == "agent_ended"
            assert meta["hangup_initiator"] == "agent"
        else:
            assert commands == []
            assert ctx.status == "active"
            assert not meta.get("hangup_outcome")
        return {
            "language": language, "caller": user, "expected_close": closing,
            "hangup_commands": len(commands), "spoken": texts,
            "end_reason": stored.get("end_reason"),
            "hangup_outcome": meta.get("hangup_outcome"), "passed": True,
            "classifier_usage": (meta.get("stage_usage") or {}).get("llm", {}),
        }
    finally:
        await voice.close()
        get_settings.cache_clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("language,user,closing", CLOSE_CASES)
async def test_semantic_decision_reaches_carrier_and_persisted_lifecycle(monkeypatch, language, user, closing):
    await run_voice_simulation(monkeypatch, language, user, closing)


@pytest.mark.asyncio
async def test_failed_provider_command_clears_issued_reason(monkeypatch):
    from server.call.call_ledger import call_ledger
    from server.call.close_call_executor import execute_agent_close

    cid = str(uuid.uuid4())
    await call_ledger.init(cid, {"call_id": cid})
    ctx = SimpleNamespace(agent_hangup_reason=None)
    monkeypatch.setattr("server.call.call_context.get", lambda _: ctx)
    with pytest.raises(TimeoutError):
        await execute_agent_close(
            call_id=cid, reason="goodbye", spoke_farewell=False,
            on_provider_hangup=AsyncMock(side_effect=TimeoutError),
        )
    assert ctx.agent_hangup_reason is None
    assert "hangup_outcome" not in call_ledger.read_meta(cid)


@pytest.mark.asyncio
async def test_successful_speech_retry_keeps_the_close_decision(monkeypatch):
    await run_voice_simulation(
        monkeypatch, "te-IN", "అంతే అంతే థ్యాంక్ యూ", True, retry_attempt=True,
    )


def test_legacy_unsectioned_brain_refresh_removes_conflicting_close_rule():
    from server.brain.compiled_brain_artifact import refresh_platform_sections

    prompt = refresh_platform_sections("Offer visiting cards. Say a farewell and call end_call.", "te-IN")
    assert "Say a farewell and call end_call" not in prompt
    assert "server plays the approved farewell" in prompt


def test_withdrawn_callback_does_not_cancel_an_explicit_stop_contact():
    from server.call.caller_intent import classify_caller_intent

    intent = classify_caller_intent("Don't call me again, I'll call you back.")
    assert intent.stop_contact
    assert intent.callback_revoked
    assert not intent.keeps_call_open


@pytest.mark.asyncio
async def test_new_request_during_default_quiet_pause_cancels_disconnect(monkeypatch):
    from server.call import call_context
    from server.call.natural_hangup import HANGUP_TRAIL_SILENCE_SEC
    from server.services.pstn_voice_core import PHASE_LISTENING
    from server.tests.test_revocable_hangup import Playback, _loop

    assert HANGUP_TRAIL_SILENCE_SEC > 0
    ctx = SimpleNamespace(agent_hangup_armed=True)
    monkeypatch.setattr(call_context, "get", lambda _: ctx)
    voice = _loop()
    voice.playback = Playback(playing_for=0.01)
    provider = AsyncMock()
    voice.set_hangup_handler(provider)

    async def caller():
        await asyncio.sleep(0.1)
        voice._pending_transcript = "Wait, one more question about delivery."

    resumed = asyncio.create_task(caller())
    try:
        await voice._finish_agent_hangup(reason="goodbye")
        await resumed
        provider.assert_not_awaited()
        assert voice._phase == PHASE_LISTENING
        assert not ctx.agent_hangup_armed
    finally:
        await voice.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("text,expected_partial_at", [("అంతే అంతే థ్యాంక్ యూ", 0.0), ("", 100.0)])
async def test_completed_stt_turn_clears_only_its_active_partial(monkeypatch, text, expected_partial_at):
    from server.call import call_context
    from server.services.pstn_voice_core import PHASE_CLOSING
    from server.tests.test_revocable_hangup import SttEvents, _loop

    ctx = SimpleNamespace(last_stt_partial_at=100.0, agent_hangup_armed=True)
    monkeypatch.setattr(call_context, "get", lambda _: ctx)
    voice = _loop()
    voice._phase = PHASE_CLOSING
    voice._turn_busy = True
    voice._stt = SttEvents([{"event": "transcript.final", "text": text}])
    try:
        await voice._stt_reader()
        assert ctx.last_stt_partial_at == expected_partial_at
    finally:
        await voice.close()
