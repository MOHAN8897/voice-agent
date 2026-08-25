"""Phase 3 orchestrator — user ledger before stream; assistant ledger after stream."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import pytest

from server.call.call_ledger import call_ledger
from server.call.live_turn_orchestrator import live_turn_orchestrator
from server.config.env import get_settings


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
