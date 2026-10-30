"""Graceful outage message: prepared at setup, played only on a sustained failure.

No network, no carrier: TTS rendering, the model stream and the database are
replaced with local fakes. Covers the product contract:

* the clip is rendered at call setup in the call's language/voice and cached;
* it never plays on a normal call, a slow turn, silence or barge-in;
* it plays and hangs up on a sustained LLM failure (2 transient / 1 hard);
* a retry is queued on the follow-up machinery, and skipped for DND;
* a deterministic opt-out check catches DND phrases in en/hi/te/ta.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.config.constants import constants
from server.providers.llm_protocol import IncompleteTurnError
from server.services import outage_clip_prewarm as prewarm
from server.services import pstn_technical_fallback as fallback
from server.services.outage_opt_out import caller_opted_out, opt_out_in_transcript
from server.services.pstn_technical_fallback import (
    CALL_BACK,
    CALLBACK_PROMISE,
    TenantFallbackConfig,
    classify_reply_failure,
    failure_threshold,
    fallback_text,
    prepare_technical_fallback_plan,
)
from server.services.pstn_voice_core import PstnVoiceLoop
from server.tests.test_durable_followups import NOW, PHONE, enable, queue  # noqa: F401 - fixture
from server.tests.test_pstn_turn_failure_delivery import _install_runtime, _TurnTts

STACK = SimpleNamespace(
    llm=SimpleNamespace(provider="sarvam", model="sarvam-m"),
    tts=SimpleNamespace(provider="sarvam", model="bulbul:v2", config={"speaker": "anushka"}),
)


@pytest.fixture
def clip_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(prewarm, "_cache_dir", lambda: tmp_path / "outage_clips")
    prewarm._failed_at.clear()
    prewarm._inflight.clear()
    yield tmp_path / "outage_clips"
    prewarm._failed_at.clear()
    prewarm._inflight.clear()


def _patch_plan_inputs(monkeypatch, *, config=None, meta=None, transcript=None):
    monkeypatch.setattr(fallback, "_read_meta", lambda call_id: dict(meta or {}))
    monkeypatch.setattr(fallback, "_read_transcript", lambda call_id: list(transcript or []))
    seen: list[dict] = []

    async def loader(**kwargs):
        seen.append(kwargs)
        return config or TenantFallbackConfig(available=False, promise_callback=False)

    monkeypatch.setattr(fallback, "_load_tenant_config", loader)
    return seen


# ---------------------------------------------------------------------------
# 1. The clip is prepared at call setup and cached
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_outage_clip_is_rendered_once_in_call_language_and_voice_then_cached(monkeypatch, clip_cache):
    rendered: list[tuple[str, str]] = []

    async def render(text, *, language, resolved_stack, pipeline):
        rendered.append((language, text))
        return b"\x01\x00" * 4000

    monkeypatch.setattr(prewarm, "_render", render)
    sources = await prewarm.ensure_outage_clips(
        tenant_id="t-1", agent_id="a-1", language="te-IN", resolved_stack=STACK, pipeline="composed_voice",
    )
    assert sources == {CALLBACK_PROMISE: "agent_voice", CALL_BACK: "agent_voice"}
    assert sorted(rendered) == sorted([
        ("te-IN", fallback_text("te-IN", CALLBACK_PROMISE)),
        ("te-IN", fallback_text("te-IN", CALL_BACK)),
    ])
    assert len(list(clip_cache.glob("*.wav"))) == 2

    # Same tenant/agent/language/voice: no new TTS request.
    await prewarm.ensure_outage_clips(
        tenant_id="t-1", agent_id="a-1", language="te-IN", resolved_stack=STACK, pipeline="composed_voice",
    )
    assert len(rendered) == 2
    # A different language is a different clip.
    await prewarm.ensure_outage_clips(
        tenant_id="t-1", agent_id="a-1", language="hi-IN", resolved_stack=STACK, pipeline="composed_voice",
    )
    assert len(rendered) == 4 and {lang for lang, _ in rendered[2:]} == {"hi-IN"}


@pytest.mark.asyncio
async def test_failed_render_falls_back_to_stock_clip_and_is_not_retried_every_call(monkeypatch, clip_cache):
    render = AsyncMock(side_effect=RuntimeError("402 insufficient credits"))
    monkeypatch.setattr(prewarm, "_render", render)
    sources = await prewarm.ensure_outage_clips(
        tenant_id="t-1", agent_id="a-1", language="ta-IN", resolved_stack=STACK, pipeline="composed_voice",
    )
    assert sources == {CALLBACK_PROMISE: "platform", CALL_BACK: "platform"}
    await prewarm.ensure_outage_clips(
        tenant_id="t-1", agent_id="a-1", language="ta-IN", resolved_stack=STACK, pipeline="composed_voice",
    )
    assert render.await_count == 2  # once per variant, then negative-cached


def test_every_platform_language_has_a_static_outage_clip_for_both_variants():
    for language in constants.SUPPORTED_LANGUAGES:
        for variant in (CALLBACK_PROMISE, CALL_BACK):
            clip = fallback._platform_clip(language, variant, "female")
            assert clip.pcm, f"missing {variant} clip for {language}"
            assert clip.language == fallback.resolve_fallback_language(language)


@pytest.mark.asyncio
async def test_start_call_schedules_the_outage_clip_for_the_call_language(monkeypatch):
    scheduled: list[dict] = []
    monkeypatch.setattr(
        "server.services.outage_clip_prewarm.schedule_outage_clip_prewarm",
        lambda **kwargs: scheduled.append(kwargs),
    )
    stack = SimpleNamespace(llm=STACK.llm, tts=STACK.tts, language="hi-IN")
    ctx = SimpleNamespace(
        tenant_id=uuid.UUID(int=1), agent_id=uuid.UUID(int=2), resolved_stack=stack,
        pipeline="composed_voice", compiled_brain_text="",
    )
    monkeypatch.setattr("server.call.call_context.get", lambda _cid: ctx)
    loop = PstnVoiceLoop(
        session_id="setup", call_id="c-setup", on_agent_wire=AsyncMock(),
        stack_override={"pipeline": "composed_voice", "language": "hi-IN"},
    )
    monkeypatch.setattr(loop, "open_stt", AsyncMock())
    monkeypatch.setattr(loop, "_warm_tts_connection", AsyncMock())
    await loop.start_call(play_greeting=False)
    assert len(scheduled) == 1
    assert scheduled[0]["language"] == "hi-IN"
    assert scheduled[0]["resolved_stack"] is stack
    assert scheduled[0]["tenant_id"] == str(uuid.UUID(int=1))
    await loop.close()


@pytest.mark.asyncio
async def test_plan_prefers_the_prepared_agent_voice_clip_in_the_call_language(monkeypatch, clip_cache):
    pcm = b"\x02\x00" * 3000
    monkeypatch.setattr(prewarm, "_render", AsyncMock(return_value=pcm))
    await prewarm.ensure_outage_clips(
        tenant_id="t-1", agent_id="a-1", language="te-IN", resolved_stack=STACK, pipeline="composed_voice",
    )
    _patch_plan_inputs(monkeypatch)
    plan = await prepare_technical_fallback_plan(
        call_id="c-1", tenant_id="t-1", agent_id="a-1", direction="outbound", language="te-IN",
        trigger="llm_failure", resolved_stack=STACK,
    )
    assert plan.source == "agent_voice"
    assert plan.pcm == pcm
    assert plan.language == "te-IN"
    assert plan.text == fallback_text("te-IN", CALL_BACK)

    # Without a prepared render the stock clip still speaks the call language.
    plan = await prepare_technical_fallback_plan(
        call_id="c-2", tenant_id="t-1", agent_id="a-1", direction="outbound", language="ta-IN",
        trigger="llm_failure", resolved_stack=STACK,
    )
    assert plan.source == "platform" and plan.language == "ta-IN" and plan.pcm


# ---------------------------------------------------------------------------
# 2. Trigger threshold: never on normal / slow / silent / barged turns
# ---------------------------------------------------------------------------


def test_failure_classification_and_thresholds():
    assert classify_reply_failure(RuntimeError("HTTP 402: insufficient credits")) == "hard"
    assert classify_reply_failure(RuntimeError("The selected composed text model is unavailable")) == "hard"
    wrapped = RuntimeError("stream failed")
    wrapped.__cause__ = type("E", (Exception,), {"status_code": 401})("bad key")
    assert classify_reply_failure(wrapped) == "hard"
    assert classify_reply_failure(TimeoutError("did not answer in time")) == "transient"
    assert classify_reply_failure(IncompleteTurnError(provider="sarvam", finish_reason="length",
                                                      partial_text="", retry_used=True)) == "transient"
    assert failure_threshold("hard") == 1 and failure_threshold("transient") == 2


def _loop(call_id: str, language: str = "en-IN") -> PstnVoiceLoop:
    loop = PstnVoiceLoop(
        session_id=call_id, call_id=call_id, on_agent_wire=AsyncMock(),
        stack_override={"pipeline": "composed_voice", "language": language},
    )
    loop._cached_resolve_language = language  # the admitted call language
    return loop


def _scripted_stream(script: list):
    """Each turn pops one entry: an exception to raise, or reply text."""

    async def stream(**_kwargs):
        step = script.pop(0)
        if isinstance(step, BaseException):
            raise step
        yield {"delta": step}
        yield {"done": True, "text": step, "finish_reason": "stop"}

    return stream


def _transient() -> IncompleteTurnError:
    return IncompleteTurnError(provider="sarvam", finish_reason="length", partial_text="", retry_used=True)


@pytest.mark.asyncio
async def test_normal_turns_never_play_the_outage_clip(monkeypatch):
    loop = _loop("c-normal")
    session = _TurnTts(loop, emit_audio=True)
    clip, _ = _install_runtime(monkeypatch, loop, session, _scripted_stream(["Hello.", "Sure.", "Bye."]))
    for text in ("hi", "price?", "ok"):
        await loop._run_turn(text)
    clip.assert_not_awaited()
    loop._finish_agent_hangup.assert_not_awaited()
    assert loop._consecutive_reply_failures == 0
    await loop.close()


@pytest.mark.asyncio
async def test_one_failed_turn_recovers_and_a_success_resets_the_count(monkeypatch):
    loop = _loop("c-flaky")
    session = _TurnTts(loop, emit_audio=True)
    clip, _ = _install_runtime(
        monkeypatch, loop, session, _scripted_stream([_transient(), "Here is the price.", _transient()]),
    )
    await loop._run_turn("price?")
    assert loop._consecutive_reply_failures == 1
    await loop._run_turn("price please")
    assert loop._consecutive_reply_failures == 0
    await loop._run_turn("and delivery?")
    # Two failures, but not consecutive: still a recovery, never the outage clip.
    clip.assert_not_awaited()
    loop._finish_agent_hangup.assert_not_awaited()
    await loop.close()


@pytest.mark.asyncio
async def test_slow_turn_reasked_by_the_watchdog_does_not_play_the_clip(monkeypatch):
    from server.services import pstn_voice_core

    monkeypatch.setattr(pstn_voice_core, "PSTN_REPLY_WATCHDOG_S", 0.05)
    monkeypatch.setattr(pstn_voice_core, "PSTN_REPLY_WATCHDOG_TOOL_S", 0.05)
    attempts: list[int] = []

    async def slow_then_ok(**_kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            await asyncio.sleep(5)
        yield {"delta": "Sorry for the wait, it is 499 rupees."}
        yield {"done": True, "text": "Sorry for the wait, it is 499 rupees.", "finish_reason": "stop"}

    loop = _loop("c-slow")
    session = _TurnTts(loop, emit_audio=True)
    clip, _ = _install_runtime(monkeypatch, loop, session, slow_then_ok)
    await loop._run_turn("price?")
    assert len(attempts) == 2
    clip.assert_not_awaited()
    assert loop._consecutive_reply_failures == 0
    await loop.close()


@pytest.mark.asyncio
async def test_barge_in_during_the_recovery_line_is_not_an_outage(monkeypatch):
    loop = _loop("c-barge")
    session = _TurnTts(loop, emit_audio=True)
    clip, _ = _install_runtime(monkeypatch, loop, session, _scripted_stream([_transient()]))

    async def barged_speak(*_args, **_kwargs):
        # Nothing of the "please repeat" line reached the wire because the
        # caller started talking over it.
        loop._awaiting_barge_final = True

    monkeypatch.setattr(loop, "speak", barged_speak)
    await loop._run_turn("price?")
    clip.assert_not_awaited()
    await loop.close()


@pytest.mark.asyncio
async def test_two_consecutive_failures_trigger_the_clip(monkeypatch):
    loop = _loop("c-sustained")
    session = _TurnTts(loop, emit_audio=True)
    clip, _ = _install_runtime(monkeypatch, loop, session, _scripted_stream([_transient(), _transient()]))
    await loop._run_turn("price?")
    clip.assert_not_awaited()
    await loop._run_turn("hello? price?")
    clip.assert_awaited_once_with(trigger="llm_failure")
    await loop.close()


@pytest.mark.asyncio
async def test_hard_provider_failure_triggers_the_clip_on_the_first_turn(monkeypatch):
    loop = _loop("c-credits")
    session = _TurnTts(loop, emit_audio=True)
    clip, _ = _install_runtime(
        monkeypatch, loop, session, _scripted_stream([RuntimeError("sarvam HTTP 402: insufficient credits")]),
    )
    await loop._run_turn("price?")
    clip.assert_awaited_once_with(trigger="llm_failure")
    await loop.close()


@pytest.mark.asyncio
async def test_sustained_llm_failure_plays_clip_in_call_language_then_hangs_up(monkeypatch):
    """End to end through the real playback: wire frames, then a technical_fallback close."""
    wires: list[bytes] = []

    async def on_wire(wire: bytes) -> None:
        wires.append(wire)

    loop = PstnVoiceLoop(
        session_id="c-e2e", call_id="c-e2e", on_agent_wire=on_wire,
        stack_override={"pipeline": "composed_voice", "language": "hi-IN"},
    )
    loop._cached_resolve_language = "hi-IN"
    monkeypatch.setattr("server.call.call_ledger.call_ledger.append_assistant_turn", AsyncMock())
    seen = _patch_plan_inputs(monkeypatch)
    close = AsyncMock(return_value=SimpleNamespace(background_task=None, cancelled=False))
    monkeypatch.setattr("server.call.close_call_executor.execute_agent_close", close)
    stamped: list = []
    monkeypatch.setattr(fallback, "stamp_fallback_meta", lambda *a, **k: stamped.append((a, k)))

    await loop._play_technical_fallback_and_hangup(trigger="llm_failure")

    expected = fallback.pcm_wire_frames(
        fallback._platform_clip("hi-IN", CALL_BACK, "male").pcm, output_codec="mulaw", sample_rate=8000,
    )
    assert len(wires) == len(expected)  # the whole Hindi clip, nothing else
    plan = stamped[0][0][1]
    assert plan.language == "hi-IN" and plan.text == fallback_text("hi-IN", CALL_BACK)
    assert close.await_args.kwargs["reason"] == "technical_fallback"
    assert close.await_args.kwargs["spoke_farewell"] is True
    assert seen and seen[0]["promise_allowed"] is True
    assert stamped[0][1]["trigger"] == "llm_failure"
    await loop.close()


# ---------------------------------------------------------------------------
# 3. Retry scheduling and DND
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_promise_variant_only_when_an_automatic_retry_is_queued(monkeypatch):
    _patch_plan_inputs(
        monkeypatch,
        meta={"callee_e164": "918897908470"},
        config=TenantFallbackConfig(available=True, promise_callback=True, callback_created=True,
                                    callback_task_id="job-1", retry_status="scheduled"),
    )
    plan = await prepare_technical_fallback_plan(
        call_id="c-1", tenant_id="t", agent_id="a", direction="outbound", language="en-IN", trigger="llm_failure",
    )
    assert plan.variant == CALLBACK_PROMISE
    assert plan.retry_status == "scheduled" and plan.callback_task_id == "job-1"


@pytest.mark.asyncio
async def test_opt_out_earlier_in_the_call_is_recorded_and_blocks_the_retry(monkeypatch):
    seen = _patch_plan_inputs(
        monkeypatch,
        transcript=[
            {"role": "assistant", "text": "Are you interested in solar panels?"},
            {"role": "user", "text": "मुझे दोबारा कॉल मत करना"},
            {"role": "assistant", "text": "..."},
            {"role": "user", "text": "hello?"},
        ],
    )
    recorded: list[tuple] = []

    async def record(call_id, evidence):
        recorded.append((call_id, evidence))
        return True

    monkeypatch.setattr("server.services.outage_opt_out.record_outage_opt_out", record)
    plan = await prepare_technical_fallback_plan(
        call_id="c-dnd", tenant_id="t", agent_id="a", direction="outbound", language="hi-IN", trigger="llm_failure",
    )
    assert recorded == [("c-dnd", "मुझे दोबारा कॉल मत करना")]
    assert seen[0]["promise_allowed"] is False
    assert plan.variant == CALL_BACK
    assert plan.retry_status == "skipped:do_not_call" and plan.opted_out is True


@pytest.mark.asyncio
async def test_opt_out_in_the_unanswered_turn_is_recorded_and_acknowledged(monkeypatch):
    loop = _loop("c-outage-dnd", "te-IN")
    session = _TurnTts(loop, emit_audio=True)
    spoken: list[str] = []
    original = _TurnTts.send_text

    async def capture(self, text):
        spoken.append(text)
        await original(self, text)

    monkeypatch.setattr(_TurnTts, "send_text", capture)
    clip, _ = _install_runtime(
        monkeypatch, loop, session, _scripted_stream([RuntimeError("HTTP 402 insufficient credits")]),
    )
    recorded: list[str] = []

    async def record(call_id, evidence):
        recorded.append(evidence)
        return True

    monkeypatch.setattr("server.services.outage_opt_out.record_outage_opt_out", record)
    await loop._run_turn("నాకు మళ్ళీ కాల్ చేయకండి")
    from server.call.call_end_policy import do_not_call_acknowledgement_for

    assert recorded == ["నాకు మళ్ళీ కాల్ చేయకండి"]
    assert spoken == [do_not_call_acknowledgement_for("te-IN")]
    loop._finish_agent_hangup.assert_awaited_once_with(reason="opt_out", revocable=False)
    clip.assert_not_awaited()
    await loop.close()


async def _retry(queue, call_id: str):  # noqa: F811 - fixture object
    async with queue.factory() as session:
        result = await fallback._schedule_outage_retry(
            session, tenant_uuid=queue.principal.tenant_id, agent_uuid=queue.aid, call_id=call_id, target=PHONE,
        )
        await session.commit()
    return result


@pytest.mark.asyncio
async def test_outage_retry_goes_through_the_follow_up_queue(queue):  # noqa: F811
    from sqlalchemy import select

    from server.db.models.followup_models import FollowUpJob
    from server.services.saas import followup_service as svc
    from server.services.saas.followup_policy import FollowUpConfig

    assert await _retry(queue, str(uuid.uuid4())) == (None, "skipped:followups_not_authorized")
    await enable(queue)
    call_id = str(uuid.uuid4())
    job_id, status = await _retry(queue, call_id)
    assert status == "scheduled" and job_id
    async with queue.factory() as session:
        row = await session.scalar(select(FollowUpJob).where(FollowUpJob.id == uuid.UUID(job_id)))
        assert row.kind == "callback" and row.phone == PHONE and row.source_id == call_id
        assert row.payload["origin"] == "technical_failure"
        assert row.due_at is not None and row.status == "scheduled"
        # Dispatch rules still apply to it: nothing blocks it now...
        policy = await svc.read_policy(queue.principal.tenant_id, queue.aid)
        cfg = FollowUpConfig.model_validate(policy["config"])
        assert await svc._block_reason(session, row, None, cfg) is None
    # Idempotent per call, and one outage retry per number per day.
    assert await _retry(queue, call_id) == (job_id, "existing")


@pytest.mark.asyncio
async def test_outage_retry_is_skipped_for_dnd_and_after_the_daily_limit(queue):  # noqa: F811
    from server.db.models.followup_models import FollowUpJob
    from server.db.models.phase5_models import DncEntry

    await enable(queue)
    first, status = await _retry(queue, str(uuid.uuid4()))
    assert status == "scheduled"
    async with queue.factory() as session:
        row = await session.get(FollowUpJob, uuid.UUID(first))
        row.status = "completed"  # the retry call happened and also failed
        await session.commit()
    assert await _retry(queue, str(uuid.uuid4())) == (None, "skipped:retry_limit")

    async with queue.factory() as session:
        session.add(DncEntry(tenant_id=queue.principal.tenant_id, phone_e164=PHONE, active=True,
                             source="test", reason="test"))
        await session.commit()
    assert await _retry(queue, str(uuid.uuid4())) == (None, "skipped:do_not_call")


@pytest.mark.asyncio
async def test_review_mode_queues_for_approval_without_a_spoken_promise(queue):  # noqa: F811
    from server.services.saas import followup_service as svc
    from server.services.saas.followup_policy import FollowUpConfig

    cfg = FollowUpConfig(enabled=True, timezone="UTC", callbackMode="review")
    await svc.save_policy(queue.principal, queue.aid, cfg, 0, True)
    job_id, status = await _retry(queue, str(uuid.uuid4()))
    assert job_id and status == "needs_review"


# ---------------------------------------------------------------------------
# 4. Deterministic opt-out check (brain unavailable)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        # en
        "Please don't call me again", "Put me on DND", "remove my number from your list",
        "stop calling me", "I don't want any more calls", "unsubscribe me",
        # hi
        "मुझे दोबारा कॉल मत करना", "मेरा नंबर हटा दीजिए", "dobara call mat karna",
        # te
        "నాకు మళ్ళీ కాల్ చేయకండి", "నాకు కాల్స్ వద్దు", "నా నంబర్ తీసేయండి", "malli call cheyyakandi",
        # ta
        "என்னை மீண்டும் அழைக்க வேண்டாம்", "இனிமேல் கால் பண்ணாதீங்க", "என் நம்பரை நீக்குங்க", "call pannatheenga",
    ],
)
def test_opt_out_keywords_catch_dnd_in_four_languages(text):
    assert caller_opted_out(text)


@pytest.mark.parametrize(
    "text",
    [
        "Call me tomorrow", "can you call me later", "how much does it cost", "don't cut the call",
        "मुझे कल कॉल करना", "kal call karna", "రేపు కాల్ చేయండి", "నాకు ధర చెప్పండి",
        "நாளை அழைக்கவும்", "சொல்லுங்க", "",
    ],
)
def test_opt_out_keywords_ignore_scheduling_and_ordinary_speech(text):
    assert not caller_opted_out(text)


def test_opt_out_scan_reads_caller_lines_only():
    rows = [{"role": "assistant", "text": "Reply STOP or say don't call me again to opt out."},
            {"role": "user", "text": "tell me the price"}]
    assert opt_out_in_transcript(rows) is None
    assert opt_out_in_transcript(rows, "stop calling me") == "stop calling me"
