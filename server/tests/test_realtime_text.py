"""OpenAI Realtime text-only live path — unit tests (no live WebSocket)."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from server.call.end_call_validate import caller_requested_hangup
from server.realtime.end_call_tool import parse_end_call_tool
from server.realtime.language_guard import filter_unrelated_scripts
from server.realtime.manager import RealtimeTextManager, realtime_text_manager
from server.realtime.models import (
    DEFAULT_REALTIME_MODEL,
    coerce_live_llm_selection,
    http_openai_model,
    is_realtime_llm_model,
)
from server.realtime.usage import extract_realtime_usage
from server.realtime.providers.openai import OpenAIRealtimeTextAdapter
from server.realtime.testing import ZERO_USAGE, FakeRealtimeAdapter
from server.services.pstn_text_chunker import drain_complete_sentences


def test_language_guard_drops_tamil_and_korean():
    mixed = "Parking 8k. தமிழ் 안녕하세요"
    cleaned = filter_unrelated_scripts(mixed, "te-IN")
    assert "தமிழ்" not in cleaned
    assert "안녕" not in cleaned
    assert "Parking" in cleaned


def test_language_guard_does_not_reinject_contaminant_only():
    assert filter_unrelated_scripts("தமிழ்") == ""
    assert filter_unrelated_scripts("안녕하세요", streaming=True) == ""


def test_language_guard_streaming_keeps_token_spaces():
    a = filter_unrelated_scripts("Hello ", "en-IN", streaming=True)
    b = filter_unrelated_scripts("there.", "en-IN", streaming=True)
    assert (a + b).strip() == "Hello there."


def test_end_call_tool_rejects_invalid_reason():
    assert parse_end_call_tool('{"should_end": true, "reason": "maybe", "farewell": "bye"}') is None
    parsed = parse_end_call_tool(
        '{"should_end": true, "reason": "goodbye", "farewell": "Thank you. Goodbye."}'
    )
    assert parsed is not None
    assert parsed["reason"] == "goodbye"


def test_caller_hangup_is_deterministic():
    assert caller_requested_hangup("please stop calling me") is True
    assert caller_requested_hangup("I'm busy, maybe later") is False


def test_realtime_usage_zero_audio():
    usage = extract_realtime_usage(
        {
            "usage": {
                "input_tokens": 100,
                "output_tokens": 20,
                "input_token_details": {"audio_tokens": 0, "cached_tokens": 80, "text_tokens": 100},
                "output_token_details": {"audio_tokens": 0, "text_tokens": 20},
            }
        }
    )
    assert usage["audio_tokens"] == 0
    assert usage["cached_tokens"] == 80


def test_gemini_is_not_a_live_llm():
    provider, model = coerce_live_llm_selection("gemini", "gemini-3.5-flash-lite")
    assert provider == "openai"
    assert is_realtime_llm_model(model)


@pytest.mark.asyncio
async def test_manager_rejects_duplicate_call_id():
    mgr = RealtimeTextManager(adapter_factory=FakeRealtimeAdapter)
    await mgr.create("c1", compiled_brain="You are a test agent.")
    with pytest.raises(RuntimeError, match="already owns"):
        await mgr.create("c1", compiled_brain="dup")
    await mgr.destroy("c1")


@pytest.mark.asyncio
async def test_sessions_are_isolated_by_call_id():
    mgr = RealtimeTextManager(adapter_factory=FakeRealtimeAdapter)
    a = await mgr.create("alpha", compiled_brain="A")
    b = await mgr.create("beta", compiled_brain="B")
    assert mgr.get("alpha") is a
    assert mgr.get("beta") is b
    assert a is not b
    await mgr.destroy("alpha")
    assert mgr.get("alpha") is None
    assert mgr.get("beta") is b
    await mgr.destroy("beta")


@pytest.mark.asyncio
async def test_cancel_marks_adapter():
    adapter = FakeRealtimeAdapter()
    mgr = RealtimeTextManager()
    session = await mgr.create("cancel-me", compiled_brain="brain", adapter=adapter)
    session._state = "streaming"
    await mgr.cancel("cancel-me")
    assert adapter.cancelled >= 1
    await mgr.destroy("cancel-me")


@pytest.mark.asyncio
async def test_hangup_without_model_success():
    adapter = FakeRealtimeAdapter(
        events=[
            {"type": "response_done", "status": "failed", "usage": dict(ZERO_USAGE), "failed": True},
        ]
    )
    session = await realtime_text_manager.create(
        "hangup-fail",
        compiled_brain="brain",
        adapter=adapter,
    )
    chunks = []
    async for chunk in session.run_turn("ok bye hang up", language="en-IN"):
        chunks.append(chunk)
    done = next(c for c in chunks if c.get("done"))
    assert done["end_call"]["should_end"] is True
    assert done["end_call"]["reason"] == "goodbye"
    await realtime_text_manager.destroy("hangup-fail")


@pytest.mark.asyncio
async def test_firm_refusal_infers_hangup_signal():
    adapter = FakeRealtimeAdapter(
        events=[
            {"type": "text_delta", "delta": "Thank you for your time. Goodbye."},
            {"type": "response_done", "status": "completed", "usage": dict(ZERO_USAGE), "failed": False},
        ]
    )
    session = await realtime_text_manager.create(
        "hangup-refuse",
        compiled_brain="brain",
        adapter=adapter,
        language="en-IN",
    )
    chunks = []
    async for chunk in session.run_turn("I'm not interested", language="en-IN"):
        chunks.append(chunk)
    done = next(c for c in chunks if c.get("done"))
    assert done["end_call"]["should_end"] is True
    assert done["end_call"]["reason"] == "firm_refusal"
    assert "Goodbye" in (done.get("text") or done["end_call"].get("farewell") or "")
    await realtime_text_manager.destroy("hangup-refuse")


@pytest.mark.asyncio
async def test_end_call_tool_emits_hangup_signal():
    adapter = FakeRealtimeAdapter(
        events=[
            {"type": "text_delta", "delta": "Noted — our team will contact you. Goodbye."},
            {
                "type": "function_call",
                "name": "end_call",
                "arguments": (
                    '{"should_end": true, "reason": "goal_complete", '
                    '"farewell": "Noted — our team will contact you. Goodbye."}'
                ),
            },
            {"type": "response_done", "status": "completed", "usage": dict(ZERO_USAGE), "failed": False},
        ]
    )
    session = await realtime_text_manager.create(
        "hangup-tool",
        compiled_brain="brain",
        adapter=adapter,
        language="en-IN",
    )
    chunks = []
    async for chunk in session.run_turn(
        "Yes, please have the team call me back",
        language="en-IN",
    ):
        chunks.append(chunk)
    done = next(c for c in chunks if c.get("done"))
    assert done["end_call"]["should_end"] is True
    assert done["end_call"]["reason"] == "goal_complete"
    await realtime_text_manager.destroy("hangup-tool")


@pytest.mark.asyncio
async def test_post_call_never_sends_realtime_model(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("POST_CALL_LLM_MODEL", "gpt-5.6-luna")
    from server.call.call_ledger import call_ledger
    from server.call.memory_manager import memory_manager
    from server.call.post_call_pipeline import call_summary_path, process_now, read_outcome
    from server.config.env import get_settings

    get_settings.cache_clear()
    call_ledger.reset_for_tests()
    memory_manager.reset_for_tests()
    call_id = "rt-outcome"
    await call_ledger.init(
        call_id,
        {
            "call_id": call_id,
            "resolved_stack": {"llm": {"provider": "openai", "model": DEFAULT_REALTIME_MODEL}},
        },
    )
    await call_ledger.append_user_turn(call_id, "hello")
    await call_ledger.append_assistant_turn(call_id, "hi")
    memory_manager.init(call_id)
    captured = {}

    async def fake_completion(*_a, **kwargs):
        captured["config"] = kwargs.get("config") or (_a[2] if len(_a) > 2 else None)
        return {
            "disposition": "interested",
            "disposition_confidence": 0.8,
            "summary_te": "సారాంశం",
            "summary_en": "summary",
            "next_action": None,
            "extracted_fields": [],
            "objections": [],
            "notes": "",
        }

    with patch("server.providers.get_provider_registry") as reg:
        adapter = type("A", (), {"structured_completion": AsyncMock(side_effect=fake_completion)})()
        reg.return_value.get_llm.return_value = adapter
        outcome = await process_now(call_id)
    model = getattr(captured.get("config"), "model", None)
    assert model == "gpt-5.6-luna"
    assert not is_realtime_llm_model(model)
    assert outcome["disposition"] == "interested"
    disk = read_outcome(call_id)
    assert disk is not None
    assert call_summary_path(call_id).exists()
    call_ledger.reset_for_tests()
    memory_manager.reset_for_tests()
    get_settings.cache_clear()


def test_http_model_never_realtime():
    assert not is_realtime_llm_model(http_openai_model())
    assert http_openai_model() == "gpt-5.6-luna"


def test_stale_realtime_deltas_are_dropped():
    adapter = OpenAIRealtimeTextAdapter(api_key="sk-test")
    adapter._accepting = True
    adapter._active_response_id = "resp_new"
    stale = {"type": "response.output_text.delta", "delta": "old", "response_id": "resp_old"}
    assert adapter._normalize(stale) is None
    live = {"type": "response.output_text.delta", "delta": "Hi", "response_id": "resp_new"}
    assert adapter._normalize(live) == {"type": "text_delta", "delta": "Hi"}
    adapter._accepting = False
    assert adapter._normalize(live) is None


def test_session_ready_is_not_a_queued_event():
    adapter = OpenAIRealtimeTextAdapter(api_key="sk-test")
    assert adapter._normalize({"type": "session.created"}) is None
    assert adapter._normalize({"type": "session.updated"}) is None


class _SlowConnectAdapter(FakeRealtimeAdapter):
    async def connect(self, *, model: str, instructions: str, **_kwargs):
        await asyncio.sleep(1.5)
        await super().connect(model=model, instructions=instructions)


@pytest.mark.asyncio
async def test_background_boot_does_not_block_create():
    mgr = RealtimeTextManager(adapter_factory=_SlowConnectAdapter)
    t0 = time.perf_counter()
    session = await mgr.create("slow-boot", compiled_brain="You are a test agent.", wait_ready=False)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 400, f"create blocked on websocket: {elapsed_ms:.0f}ms"
    assert mgr.get("slow-boot") is session
    await mgr.destroy("slow-boot")


@pytest.mark.asyncio
async def test_pstn_shared_path_first_audio_from_realtime_deltas():
    adapter = FakeRealtimeAdapter(
        events=[
            {"type": "text_delta", "delta": "Sure I can help you with that "},
            {"type": "text_delta", "delta": "property today in Gachibowli."},
            {
                "type": "response_done",
                "status": "completed",
                "usage": dict(ZERO_USAGE),
                "failed": False,
            },
        ]
    )
    mgr = RealtimeTextManager()
    session = await mgr.create("pstn-shared", compiled_brain="You are a test agent.", adapter=adapter)
    pending = ""
    first_spoken = None
    async for chunk in session.run_turn("parking unda?", language="te-IN"):
        if chunk.get("delta"):
            pending += chunk["delta"]
            sentences, pending = drain_complete_sentences(pending, allow_first_fast=True)
            if sentences and first_spoken is None:
                first_spoken = sentences[0]
    assert first_spoken
    assert len(first_spoken) >= 18
    await mgr.destroy("pstn-shared")


@pytest.mark.asyncio
async def test_reconnects_after_adapter_close():
    mgr = RealtimeTextManager(adapter_factory=FakeRealtimeAdapter)
    session = await mgr.create("reopen", compiled_brain="You are a test agent.")
    await session._adapter.close()
    assert not session._adapter.is_open()
    chunks = []
    async for chunk in session.run_turn("hello"):
        chunks.append(chunk)
    done = next(c for c in chunks if c.get("done"))
    assert "Hello" in (done.get("text") or "")
    await mgr.destroy("reopen")


@pytest.mark.asyncio
async def test_note_spoken_records_assistant_item():
    adapter = FakeRealtimeAdapter()
    mgr = RealtimeTextManager()
    session = await mgr.create("greet-note", compiled_brain="You are a test agent.", adapter=adapter)
    await mgr.note_spoken("greet-note", "Namaste! Nenu Priya.")
    assert any(str(item).startswith("__assistant__:Namaste") for item in adapter.sent)
    await mgr.destroy("greet-note")
