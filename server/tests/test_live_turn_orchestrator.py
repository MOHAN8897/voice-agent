"""Phase 3 orchestrator — user ledger before stream; assistant ledger after stream."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import pytest

from server.call.call_ledger import call_ledger
from server.call.live_turn_orchestrator import (
    cap_reactive_response,
    correction_memory_operation,
    live_turn_orchestrator,
)
from server.config.env import get_settings


def test_reactive_response_keeps_only_human_recovery_sentence():
    assert cap_reactive_response(
        "You're repeating yourself like a recorded message.",
        "Fair point — I was repeating myself. The library closes at eight PM.",
    ) == "Fair point — I was repeating myself."
    assert cap_reactive_response(
        "What time do you close?",
        "We close at eight PM. We're open daily.",
    ) == "We close at eight PM."
    assert cap_reactive_response(
        "Fees ఎంత?",
        "Monthly fee eight thousand rupees. Inka emaina kavala?",
    ) == "Monthly fee eight thousand rupees."
    assert cap_reactive_response(
        "Please send it on WhatsApp.",
        "I can't send it directly. The fee is eight thousand rupees.",
    ) == "I can't send it directly."


def test_explicit_correction_uses_one_latest_wins_memory_key():
    first = correction_memory_operation("Actually Wednesday, not Tuesday.")
    latest = correction_memory_operation("Move that to Thursday at four.")
    assert first == {
        "op": "set_fact",
        "key": "latest_caller_correction",
        "value": "Actually Wednesday, not Tuesday.",
    }
    assert latest and latest["key"] == first["key"]
    assert latest["value"] == "Move that to Thursday at four."
    assert correction_memory_operation("I'm not interested right now.") is None


@pytest.mark.asyncio
async def test_stream_suppresses_recap_after_frustration(monkeypatch):
    monkeypatch.setenv("ENABLE_CALL_ARCHIVE", "false")
    get_settings.cache_clear()

    async def fake_stream(**_kwargs):
        yield {"delta": "You're right — I'm sorry."}
        yield {"delta": " The failed payment was nine hundred rupees."}
        yield {
            "done": True,
            "text": "You're right — I'm sorry. The failed payment was nine hundred rupees.",
            "end_call": {"should_end": False, "reason": "none", "farewell": ""},
        }

    chunks = []
    with patch("server.call.live_turn_orchestrator.generate_response_stream", fake_stream):
        async for chunk in live_turn_orchestrator.handle_user_turn_stream(
            transcript="I've explained this twice and I'm frustrated.",
            session_id="reactive-cap",
        ):
            chunks.append(chunk)

    assert "".join(str(chunk.get("delta") or "") for chunk in chunks) == "You're right — I'm sorry."
    assert next(chunk for chunk in chunks if chunk.get("done"))["text"] == "You're right — I'm sorry."
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_first_delta_not_blocked_by_ledger(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_CALL_ARCHIVE", "true")
    get_settings.cache_clear()
    call_ledger.reset_for_tests()
    await call_ledger.init("hot-path", {"call_id": "hot-path"})

    async def fast_user(*_a, **_k):
        return {"seq": 1, "role": "user", "text": "x"}

    async def slow_assistant(*_a, **_k):
        await asyncio.sleep(0.25)
        return {"seq": 2, "role": "assistant", "text": "hi"}

    async def fake_stream(**_k):
        yield {"delta": "hi"}
        yield {"done": True, "text": "hi"}

    with (
        patch("server.call.live_turn_orchestrator.call_ledger.append_user_turn", fast_user),
        patch("server.call.live_turn_orchestrator.call_ledger.append_assistant_turn", slow_assistant),
        patch("server.call.live_turn_orchestrator.generate_response_stream", fake_stream),
    ):
        t0 = time.perf_counter()
        first_ms = None
        async for chunk in live_turn_orchestrator.handle_user_turn_stream(
            transcript="hello",
            session_id="s",
            call_id="hot-path",
        ):
            if chunk.get("delta") and first_ms is None:
                first_ms = (time.perf_counter() - t0) * 1000
                break
        assert first_ms is not None
        assert first_ms < 100, f"first delta waited {first_ms:.0f}ms on assistant ledger"

    call_ledger.reset_for_tests()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_realtime_first_delta_skips_memory_projection_io(monkeypatch):
    from server.realtime.manager import realtime_text_manager

    monkeypatch.setenv("ENABLE_CALL_ARCHIVE", "false")
    get_settings.cache_clear()

    class FakeRealtimeSession:
        async def run_turn(self, _transcript, *, language, turn_hint=None):
            yield {"delta": "Hello"}
            yield {
                "done": True,
                "text": "Hello.",
                "end_call": {"should_end": False, "reason": "none", "farewell": ""},
                "memory_update": {"operations": []},
            }

    async def unexpected_memory_io(_call_id):
        raise AssertionError("Realtime response waited for memory projection I/O")

    realtime_text_manager._sessions["realtime-hot"] = FakeRealtimeSession()
    monkeypatch.setattr(live_turn_orchestrator, "_memory_blocks", unexpected_memory_io)
    try:
        chunks = [
            chunk
            async for chunk in live_turn_orchestrator.handle_user_turn_stream(
                transcript="hello",
                session_id="s",
                call_id="realtime-hot",
                language_code="en-IN",
            )
        ]
        assert any(chunk.get("delta") for chunk in chunks)
        assert chunks[-1]["done"]
    finally:
        realtime_text_manager.reset_for_tests()
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_sealed_ledger_does_not_raise_from_orchestrator(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_CALL_ARCHIVE", "true")
    get_settings.cache_clear()
    call_ledger.reset_for_tests()
    await call_ledger.init("sealed-call", {"call_id": "sealed-call"})
    await call_ledger.seal("sealed-call")
    await live_turn_orchestrator._safe_append_user("sealed-call", "late", 50)
    assert call_ledger.read_lines("sealed-call") == []
    call_ledger.reset_for_tests()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_memory_merge_does_not_block_first_delta(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_CALL_ARCHIVE", "true")
    monkeypatch.setenv("ENABLE_WORKING_MEMORY", "true")
    get_settings.cache_clear()
    call_ledger.reset_for_tests()
    from server.call.memory_manager import memory_manager

    memory_manager.reset_for_tests()
    await call_ledger.init("mem-hot", {"call_id": "mem-hot"})
    memory_manager.init("mem-hot")
    applied = {"n": 0}

    async def fake_stream(**_k):
        yield {"delta": "hi"}
        yield {
            "done": True,
            "text": "hi",
            "memory_update": {"operations": [{"op": "set_fact", "key": "name", "value": "Ravi"}]},
        }

    orig_apply = memory_manager.apply_proposals

    def slow_apply(*a, **k):
        time.sleep(0.2)
        applied["n"] += 1
        return orig_apply(*a, **k)

    with (
        patch("server.call.live_turn_orchestrator.generate_response_stream", fake_stream),
        patch.object(memory_manager, "apply_proposals", slow_apply),
    ):
        t0 = time.perf_counter()
        first_ms = None
        async for chunk in live_turn_orchestrator.handle_user_turn_stream(
            transcript="నా పేరు రవి",
            session_id="s",
            call_id="mem-hot",
        ):
            if chunk.get("delta") and first_ms is None:
                first_ms = (time.perf_counter() - t0) * 1000
        assert first_ms is not None
        assert first_ms < 100, f"first delta waited {first_ms:.0f}ms on memory merge"
        await asyncio.sleep(0.35)
        assert applied["n"] >= 1
        assert memory_manager.get_snapshot("mem-hot")["facts"].get("name") == "Ravi"

    call_ledger.reset_for_tests()
    memory_manager.reset_for_tests()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_empty_ops_does_not_trigger_extraction_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_CALL_ARCHIVE", "true")
    monkeypatch.setenv("ENABLE_WORKING_MEMORY", "true")
    monkeypatch.setenv("ENABLE_MEMORY_EXTRACTION_FALLBACK", "true")
    get_settings.cache_clear()
    call_ledger.reset_for_tests()
    from server.call.memory_manager import memory_manager

    memory_manager.reset_for_tests()
    await call_ledger.init("empty-ops", {"call_id": "empty-ops"})
    memory_manager.init("empty-ops")
    called = {"n": 0}

    async def fake_stream(**_k):
        yield {"delta": "ok"}
        yield {"done": True, "text": "ok", "memory_update": {"operations": []}, "memory_parse_failed": False}

    async def fake_extract(*_a, **_k):
        called["n"] += 1
        return None

    with (
        patch("server.call.live_turn_orchestrator.generate_response_stream", fake_stream),
        patch("server.call.memory_extraction.extract_and_apply", fake_extract),
    ):
        async for _ in live_turn_orchestrator.handle_user_turn_stream(
            transcript="hello",
            session_id="s",
            call_id="empty-ops",
        ):
            pass
        await asyncio.sleep(0.15)
    assert called["n"] == 0
    call_ledger.reset_for_tests()
    memory_manager.reset_for_tests()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_parse_failure_triggers_extraction_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_CALL_ARCHIVE", "true")
    monkeypatch.setenv("ENABLE_WORKING_MEMORY", "true")
    monkeypatch.setenv("ENABLE_MEMORY_EXTRACTION_FALLBACK", "true")
    get_settings.cache_clear()
    call_ledger.reset_for_tests()
    from server.call.memory_manager import memory_manager

    memory_manager.reset_for_tests()
    await call_ledger.init("parse-fail", {"call_id": "parse-fail"})
    memory_manager.init("parse-fail")
    called = {"n": 0}

    async def fake_stream(**_k):
        yield {"delta": "ok"}
        yield {"done": True, "text": "ok", "memory_update": {"operations": []}, "memory_parse_failed": True}

    async def fake_extract(*_a, **_k):
        called["n"] += 1
        return None

    with (
        patch("server.call.live_turn_orchestrator.generate_response_stream", fake_stream),
        patch("server.call.memory_extraction.extract_and_apply", fake_extract),
    ):
        async for _ in live_turn_orchestrator.handle_user_turn_stream(
            transcript="hello",
            session_id="s",
            call_id="parse-fail",
        ):
            pass
        await asyncio.sleep(0.15)
    assert called["n"] == 1
    call_ledger.reset_for_tests()
    memory_manager.reset_for_tests()
    get_settings.cache_clear()


def test_maybe_build_live_input_uses_locked_compiled_brain():
    from datetime import datetime, timezone

    from server.call.call_context import CallContext
    from server.providers.base import ResolvedStack, StageSelection

    ctx = CallContext(
        call_id="in-lock",
        tenant_id="t",
        agent_id="a",
        session_id="s",
        channel="browser",
        direction="inbound",
        environment="development",
        tier="medium",
        resolved_stack=ResolvedStack(
            combination_id="c",
            tier="medium",
            mode="frontend",
            stt=StageSelection("sarvam", "saaras:v3-realtime", {}),
            llm=StageSelection("openai", "gpt-5.6-luna", {}),
            tts=StageSelection("sarvam", "bulbul:v3", {}),
            language="te-IN",
        ),
        compiled_brain_version="cb_v1",
        compiled_brain_text="LOCKED COMPILED BRAIN",
        started_at=datetime.now(timezone.utc),
        storage_path="data/calls/in-lock/",
    )
    msgs = live_turn_orchestrator._maybe_build_live_input(
        ctx=ctx,
        transcript="hi",
        session_id="s",
        openai_model="gpt-5.6-luna",
        projection="name: Ravi",
        rolling="",
    )
    assert msgs is not None
    assert msgs[0]["content"][0]["text"] == "LOCKED COMPILED BRAIN"
    assert any("[Memory projection]" in m["content"][0]["text"] for m in msgs)
    assert live_turn_orchestrator._maybe_build_live_input(
        ctx=None,
        transcript="hi",
        session_id="s",
        openai_model=None,
        projection=None,
        rolling=None,
    ) is None


@pytest.mark.asyncio
async def test_direct_stream_path_drops_model_kwarg(monkeypatch):
    captured: dict = {}

    async def fake_stream(**kwargs):
        captured.update(kwargs)
        yield {"done": True, "text": "ok"}

    monkeypatch.setattr(
        "server.call.live_turn_orchestrator.generate_response_stream", fake_stream
    )
    async for _ in live_turn_orchestrator._stream_llm(
        ctx=None,
        transcript="hi",
        model="gpt-5.6-luna",
        openai_model="gpt-5.6-luna",
    ):
        pass
    assert "model" not in captured
    assert captured["openai_model"] == "gpt-5.6-luna"


def test_align_stream_model_rewrites_gemini_id_for_openai():
    class FakeAdapter:
        provider_id = "openai"

    class FakeReg:
        def is_model_allowed(self, pid, stage, model):
            return pid == "openai" and str(model).startswith("gpt-")

        def get_catalog(self):
            return {
                "providers": [
                    {
                        "id": "openai",
                        "models": {"llm": [{"id": "gpt-5.6-luna", "default": True}]},
                    }
                ]
            }

    kw = {"model": "gemini-3.5-flash-lite", "openai_model": "gemini-3.5-flash-lite"}
    live_turn_orchestrator._align_stream_model(kw, FakeAdapter(), FakeReg())
    assert str(kw["model"]).startswith("gpt-")
    assert "gemini" not in str(kw["model"])
    assert str(kw["openai_model"]).startswith("gpt-")


def test_messages_for_model_strips_breakpoint_on_gpt55():
    msgs = [
        {
            "role": "developer",
            "content": [
                {"type": "input_text", "text": "BRAIN", "prompt_cache_breakpoint": {"mode": "explicit"}}
            ],
        }
    ]
    kept = live_turn_orchestrator._messages_for_model(msgs, "gpt-5.6-luna")
    assert kept is msgs
    assert "prompt_cache_breakpoint" in kept[0]["content"][0]
    stripped = live_turn_orchestrator._messages_for_model(msgs, "gpt-5.5")
    assert "prompt_cache_breakpoint" not in stripped[0]["content"][0]
    assert stripped[0]["content"][0]["text"] == "BRAIN"
    assert "prompt_cache_breakpoint" in msgs[0]["content"][0]


def test_maybe_build_live_input_enables_cache_prefix_for_gemini():
    from datetime import datetime, timezone

    from server.call.call_context import CallContext
    from server.providers.base import ResolvedStack, StageSelection

    brain = ("You are a Telugu voice agent. " * 200).strip()
    ctx = CallContext(
        call_id="gem-cache",
        tenant_id="t",
        agent_id="a",
        session_id="s",
        channel="browser",
        direction="inbound",
        environment="development",
        tier="medium",
        resolved_stack=ResolvedStack(
            combination_id="c",
            tier="medium",
            mode="frontend",
            stt=StageSelection("sarvam", "saaras:v3-realtime", {}),
            llm=StageSelection("gemini", "gemini-3.5-flash-lite", {}),
            tts=StageSelection("sarvam", "bulbul:v3", {}),
            language="te-IN",
        ),
        compiled_brain_version="cb_v1",
        compiled_brain_text=brain,
        started_at=datetime.now(timezone.utc),
        storage_path="data/calls/gem-cache/",
    )
    msgs = live_turn_orchestrator._maybe_build_live_input(
        ctx=ctx,
        transcript="hi",
        session_id="s",
        openai_model="gemini-3.5-flash-lite",
        projection="name: Ravi",
        rolling="Caller is Ravi",
    )
    assert msgs is not None
    assert msgs[0]["content"][0]["text"] == brain
    assert "prompt_cache_breakpoint" in msgs[0]["content"][0]
    joined = str(msgs[1:])
    assert "name: Ravi" in joined
    assert brain not in joined
