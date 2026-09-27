"""Protocol and call-state regressions; no provider network calls."""
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

from server.realtime.providers.gemini_voice import GeminiLiveVoiceAdapter
from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop, record_realtime_voice_usage


def message(**changes):
    return NS(setup_complete=None, session_resumption_update=None, voice_activity=None,
              tool_call=None, **{"server_content": None, "usage_metadata": None, **changes})


def content(**changes):
    return NS(**{"interrupted": False, "input_transcription": None, "output_transcription": None,
                 "model_turn": None, "turn_complete": False, "generation_complete": False, **changes})


def test_usage_does_not_complete_active_response():
    adapter = GeminiLiveVoiceAdapter()
    adapter._active_response_id = "active"
    adapter._accepting = True
    adapter._response_idle.clear()
    events = adapter._normalize(message(usage_metadata=NS(model_dump=lambda: {
        "prompt_token_count": 100, "response_token_count": 5})))
    assert events[0]["usage_only"]
    assert adapter._active_response_id == "active"
    assert adapter._accepting and not adapter._response_idle.is_set()


def test_generation_complete_waits_for_turn_complete():
    adapter = GeminiLiveVoiceAdapter()
    adapter._active_response_id = "active"
    adapter._accepting = True
    assert not adapter._normalize(message(server_content=content(generation_complete=True)))
    assert adapter._active_response_id == "active"
    events = adapter._normalize(message(server_content=content(turn_complete=True)))
    assert events[-1]["type"] == "response_done"


def test_transcript_starts_response_before_first_delta():
    adapter = GeminiLiveVoiceAdapter()
    events = adapter._normalize(message(server_content=content(output_transcription=NS(text="Hello "))))
    assert [e["type"] for e in events] == ["response_created", "assistant_transcript_delta"]
    events = adapter._normalize(message(server_content=content(output_transcription=NS(text="there"))))
    assert [e["type"] for e in events] == ["assistant_transcript_delta"]


def test_real_sdk_activity_and_fragmented_caller_transcription():
    from google.genai import types
    adapter = GeminiLiveVoiceAdapter()
    events = adapter._normalize(types.LiveServerMessage(
        voice_activity=types.VoiceActivity(voice_activity_type="ACTIVITY_START")))
    assert events == [{"type": "speech_started"}]
    events = adapter._normalize(message(server_content=content(
        input_transcription=NS(text="Do not ", finished=False))))
    assert not events[0]["final"]
    events = adapter._normalize(message(server_content=content(
        input_transcription=NS(text="hang up", finished=True))))
    assert events[0] == {"type": "user_transcript", "text": "Do not hang up", "final": True}


@pytest.mark.asyncio
async def test_same_length_changed_opening_is_resynthesized(monkeypatch):
    import server.services.pstn_realtime_voice_core as core
    import server.services.pstn_realtime_greeting_prewarm as prewarm
    loop = PstnRealtimeVoiceLoop(session_id="regression", call_id=None, on_agent_wire=AsyncMock())
    monkeypatch.setattr(core, "extract_prewarm_greeting", lambda *a, **kw: "Hello, I am Maya from Newco.")
    synth = AsyncMock(return_value=([b"new"], "Hello, I am Maya from Newco.", None))
    monkeypatch.setattr(prewarm, "synthesize_gemini_greeting_on_side_session", synth)
    text, frames = await loop._maybe_refresh_gemini_deferred_greeting(
        brain="new brain", language="en-IN", greeting_text="Hello, I am Tara from Oldco.",
        greeting_wire_frames=[b"old"], model="gemini-3.8-live", cfg={}, max_output_tokens=None)
    assert "Maya" in text and frames == [b"new"]
    synth.assert_awaited_once()


def test_large_opening_policy_cannot_starve_flow():
    from server.realtime.gemini_audio_session import build_gemini_audio_session_instructions
    brain = "--- OPENING ---\n" + "opening policy " * 6000
    brain += "\n--- CONVERSATION FLOW ---\nAsk which course they want.\nOffer an appointment."
    prompt = build_gemini_audio_session_instructions(brain, token_budget=2500)
    assert "PINNED CONVERSATION FLOW" in prompt
    assert "Ask which course they want" in prompt


@pytest.mark.asyncio
async def test_cancel_drops_remaining_audio_until_turn_boundary():
    adapter = GeminiLiveVoiceAdapter()
    adapter._active_response_id = "old"
    await adapter.cancel_response()
    audio = content(model_turn=NS(parts=[NS(inline_data=NS(data=b"12"))]))
    assert not adapter._normalize(message(server_content=audio))
    adapter._normalize(message(server_content=content(turn_complete=True)))
    assert any(e["type"] == "audio_delta" for e in adapter._normalize(message(server_content=audio)))


@pytest.mark.asyncio
async def test_usage_trailer_cannot_finish_new_turn_or_hang_up():
    loop = PstnRealtimeVoiceLoop(session_id="regression", call_id=None, on_agent_wire=AsyncMock())
    loop._response_open = True
    loop._openai_response_id = "new"
    loop._pending_end_call = {"reason": "goal_complete"}
    loop._begin_close_listen = lambda: pytest.fail("usage triggered hangup")
    await loop._handle_event({"type": "response_done", "usage_only": True, "response_id": "old"})
    assert loop._response_open


@pytest.mark.asyncio
async def test_active_caller_not_disconnected_for_stuck_response():
    loop = PstnRealtimeVoiceLoop(session_id="regression", call_id=None, on_agent_wire=AsyncMock())
    loop._response_open = True
    loop._response_activity_at = 1
    loop._caller_speaking = True
    loop._runtime_end = AsyncMock()
    await loop._check_runtime(32)
    loop._runtime_end.assert_not_awaited()
    assert not loop._response_open


@pytest.mark.asyncio
async def test_gemini_response_usage_bills_session_cumulative_not_per_id(monkeypatch, tmp_path):
    from server.call.call_ledger import call_ledger
    from server.config.env import get_settings
    from server.services.pstn_realtime_voice_core import record_realtime_voice_usage

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    call_ledger.reset_for_tests()
    cid = "gemini-cum"
    await call_ledger.init(cid, {"call_id": cid})
    args = {"call_id": cid, "llm_model": "gemini-3.8-live"}
    await record_realtime_voice_usage(
        **args,
        usage={
            "input_tokens": 5000,
            "output_tokens": 80,
            "input_audio_tokens": 400,
            "output_audio_tokens": 80,
            "usage_scope": "response",
            "usage_id": "turn-1",
        },
    )
    await record_realtime_voice_usage(
        **args,
        usage={
            "input_tokens": 10000,
            "output_tokens": 180,
            "input_audio_tokens": 900,
            "output_audio_tokens": 180,
            "usage_scope": "response",
            "usage_id": "turn-2",
        },
    )
    meta = call_ledger.read_meta(cid)["usage"]
    assert meta["input_tokens"] == 10000
    assert meta["output_tokens"] == 180
    assert meta["cost_usd"] > 0
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_gemini_duplicate_trailer_same_fingerprint_different_usage_id(monkeypatch, tmp_path):
    from server.call.call_ledger import call_ledger
    from server.config.env import get_settings

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    call_ledger.reset_for_tests()
    cid = "gemini-dup-trailer"
    await call_ledger.init(cid, {"call_id": cid})
    args = {"call_id": cid, "llm_model": "gemini-3.8-live"}
    usage = {
        "input_tokens": 5000,
        "output_tokens": 80,
        "input_audio_tokens": 400,
        "output_audio_tokens": 80,
        "usage_scope": "response",
        "usage_id": "turn-a",
    }
    first = await record_realtime_voice_usage(**args, usage=usage)
    dup = await record_realtime_voice_usage(
        **args,
        usage={**usage, "usage_id": "turn-a-trailer"},
    )
    assert first is not None
    assert dup is None
    meta = call_ledger.read_meta(cid)["usage"]
    assert meta["turns"] == 1
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_response_usage_counts_identical_distinct_turns_once(monkeypatch, tmp_path):
    from server.call.call_ledger import call_ledger
    from server.config.env import get_settings
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    call_ledger.reset_for_tests()
    try:
        await call_ledger.init("usage-regression", {"call_id": "usage-regression"})
        usage = {"input_tokens": 100, "output_tokens": 20, "output_audio_tokens": 20,
                 "usage_scope": "response", "usage_id": "first"}
        args = {"call_id": "usage-regression", "llm_model": "gemini-3.8-live"}
        import asyncio
        await asyncio.gather(*(record_realtime_voice_usage(**args, usage=usage) for _ in range(3)))
        assert await record_realtime_voice_usage(**args, usage=usage) is None
        await record_realtime_voice_usage(
            **args,
            usage={
                **usage,
                "usage_id": "second",
                "input_tokens": 200,
                "output_tokens": 40,
                "output_audio_tokens": 40,
            },
        )
        totals = call_ledger.read_meta("usage-regression")["usage"]
        assert totals["input_tokens"] == 200
        assert totals["output_tokens"] == 40
        assert totals["usage_events"] == 2
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_gemini_reconnects_changed_brain_even_with_same_opening(monkeypatch):
    from server.realtime.testing import FakeRealtimeVoiceAdapter
    import server.services.pstn_realtime_voice_core as core
    adapter = FakeRealtimeVoiceAdapter()
    adapter.connected = True
    adapter.instructions = "Hello from Acme. Old flow."
    adapter.close = AsyncMock(side_effect=lambda: setattr(adapter, "closed", True))
    monkeypatch.setattr(core, "build_realtime_voice_instructions", lambda *a, **kw: "Hello from Acme. New flow.")
    loop = PstnRealtimeVoiceLoop(session_id="regression", call_id=None, on_agent_wire=AsyncMock(),
        adapter=adapter, stack_override={"pipeline": "realtime_voice", "direction": "outbound",
        "llm": {"provider": "gemini", "model": "gemini-3.8-live"}})
    try:
        await loop.start_call(play_greeting=False)
        adapter.close.assert_awaited_once()
        assert adapter.instructions == "Hello from Acme. New flow."
        assert adapter.instruction_updates == 0
    finally:
        await loop.close()


@pytest.mark.asyncio
async def test_prewarm_collects_trailing_usage_without_truncating_audio():
    from server.services.pstn_realtime_greeting_prewarm import synthesize_realtime_greeting_frames
    events = iter([
        {"type": "audio_delta", "pcm": b"\0\0" * 480},
        {"type": "response_done", "usage_only": True, "usage": {"input_tokens": 10}},
        {"type": "audio_delta", "pcm": b"\0\0" * 480},
        {"type": "response_done"},
    ])
    adapter = NS(start_response=AsyncMock(), poll_event=AsyncMock(side_effect=lambda **kw: next(events, None)))
    frames, _, usage = await synthesize_realtime_greeting_frames(
        adapter, greeting_text="Hello", sample_rate=16000, tts_output_codec="linear16")
    assert len(frames) == 2
    assert usage == {"input_tokens": 10}


@pytest.mark.asyncio
async def test_prewarm_waits_for_post_completion_usage():
    from server.services.pstn_realtime_greeting_prewarm import synthesize_realtime_greeting_frames
    events = iter([
        {"type": "audio_delta", "pcm": b"\0\0" * 480},
        {"type": "response_done"},
        {"type": "response_done", "usage_only": True, "usage": {"output_tokens": 10}},
    ])
    adapter = NS(opening_history_clean=True, start_response=AsyncMock(),
                 poll_event=AsyncMock(side_effect=lambda **kw: next(events, None)))
    _, _, usage = await synthesize_realtime_greeting_frames(
        adapter, greeting_text="Hello", sample_rate=16000, tts_output_codec="linear16")
    assert usage == {"output_tokens": 10}


@pytest.mark.asyncio
async def test_duplicate_prewarm_start_preserves_owner(monkeypatch):
    import asyncio
    import server.services.pstn_prewarm as prewarm
    gate = asyncio.Event()
    build = AsyncMock(side_effect=lambda *a, **kw: None)

    async def wait_build(*args, **kwargs):
        await gate.wait()

    build.side_effect = wait_build
    monkeypatch.setattr(prewarm, "_build_prewarm_bundle", build)
    monkeypatch.setattr(prewarm, "_destroy_realtime", AsyncMock())
    registry = prewarm.PstnPrewarmRegistry()
    await registry.start("telnyx", "duplicate", {})
    owner = registry._entries["telnyx:duplicate"]
    await asyncio.sleep(0)
    await registry.start("telnyx", "duplicate", {})
    assert registry._entries["telnyx:duplicate"] is owner
    assert not owner.task.cancelled()
    assert build.await_count == 1
    await registry.cancel("telnyx", "duplicate")


@pytest.mark.asyncio
async def test_old_prewarm_expiry_cannot_remove_successor(monkeypatch):
    import asyncio
    import server.services.pstn_prewarm as prewarm
    monkeypatch.setattr(prewarm, "PREWARM_TTL_SEC", 0)
    destroy = AsyncMock()
    monkeypatch.setattr(prewarm, "_destroy_realtime", destroy)
    registry = prewarm.PstnPrewarmRegistry()
    current = NS(task=object())
    registry._entries["telnyx:expiry"] = current
    await registry._expire_if_unclaimed("telnyx:expiry", "old", owner=asyncio.current_task())
    assert registry._entries["telnyx:expiry"] is current
    destroy.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_interrupt_clears_playback_without_cancelling_new_generation():
    from unittest.mock import Mock
    playback = NS(clear=Mock(), invalidate_generation=Mock())
    adapter = NS(cancel_response=AsyncMock())
    loop = PstnRealtimeVoiceLoop(session_id="regression", call_id=None,
        on_agent_wire=AsyncMock(), playback=playback, adapter=adapter)
    loop._adapter = adapter
    loop._response_open = True
    loop._openai_response_id = "old"
    loop._on_barge = AsyncMock()
    await loop._handle_event({"type": "cancelled", "response_id": "old", "provider_interrupted": True})
    playback.clear.assert_called_once()
    loop._on_barge.assert_awaited_once()
    adapter.cancel_response.assert_not_awaited()
    assert not loop._response_open


@pytest.mark.asyncio
async def test_old_response_cancel_cannot_cancel_current_response():
    adapter = GeminiLiveVoiceAdapter()
    adapter._active_response_id = "new"
    adapter._accepting = True
    await adapter.cancel_response(response_id="old")
    assert adapter._active_response_id == "new"
    assert adapter._accepting


@pytest.mark.asyncio
async def test_early_gemini_out_of_scope_does_not_hang_up():
    loop = PstnRealtimeVoiceLoop(session_id="regression", call_id=None, on_agent_wire=AsyncMock())
    loop._live_model = "gemini-3.8-live"
    loop._user_partial = "hello"
    assert await loop._gate_end_call_payload({"should_end": True, "reason": "out_of_scope"}) is None
    assert loop._pending_followup_instruction
