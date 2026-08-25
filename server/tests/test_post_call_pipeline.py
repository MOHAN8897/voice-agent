"""Post-call outcome pipeline — golden dispositions + validation."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from server.call.call_ledger import call_ledger
from server.call.memory_manager import memory_manager
from server.call.outcome_schema import DISPOSITIONS, validate_disposition
from server.call.post_call_pipeline import process_now, read_outcome
from server.config.env import get_settings

FIXTURES = Path(__file__).parent / "fixtures" / "disposition_golden.json"


def test_unknown_disposition_coerced():
    assert validate_disposition("qualified") == "qualified"
    assert validate_disposition("not-a-real-status") == "no_outcome"
    assert "no_outcome" in DISPOSITIONS


@pytest.mark.asyncio
async def test_golden_transcripts_to_disposition(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    call_ledger.reset_for_tests()
    memory_manager.reset_for_tests()

    cases = json.loads(FIXTURES.read_text(encoding="utf-8"))
    assert len(cases) >= 5

    for case in cases:
        call_id = case["id"]
        await call_ledger.init(call_id, {"call_id": call_id, "agent_id": "a1"})
        for row in case["transcript"]:
            if row["role"] == "user":
                await call_ledger.append_user_turn(call_id, row["text"])
            else:
                await call_ledger.append_assistant_turn(call_id, row["text"])
        memory_manager.init(call_id)
        ops = [{"op": "set_fact", "key": k, "value": v} for k, v in (case["memory"].get("facts") or {}).items()]
        if case["memory"].get("summary"):
            ops.append({"op": "update_summary", "value": case["memory"]["summary"]})
        if ops:
            memory_manager.apply_proposals(call_id, ops, turn_seq=1)

        async def fake_completion(*_a, **_k):
            return {
                "disposition": case["expected_disposition"],
                "disposition_confidence": 0.9,
                "summary_te": "సారాంశం",
                "summary_en": "summary",
                "next_action": None,
                "extracted_fields": {},
                "objections": [],
            }

        with patch("server.providers.get_provider_registry") as reg:
            adapter = type("A", (), {"structured_completion": AsyncMock(side_effect=fake_completion)})()
            reg.return_value.get_llm.return_value = adapter
            outcome = await process_now(call_id)
        assert outcome["disposition"] == case["expected_disposition"]
        disk = read_outcome(call_id)
        assert disk is not None
        assert disk["disposition"] == case["expected_disposition"]
        assert disk.get("generation_ok") is True

    call_ledger.reset_for_tests()
    memory_manager.reset_for_tests()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_invalid_disposition_from_llm_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    call_ledger.reset_for_tests()
    memory_manager.reset_for_tests()
    await call_ledger.init("bad-disp", {"call_id": "bad-disp"})
    await call_ledger.append_user_turn("bad-disp", "hello")
    memory_manager.init("bad-disp")

    async def fake_completion(*_a, **_k):
        return {
            "disposition": "totally_invalid",
            "disposition_confidence": 1,
            "summary_te": "",
            "summary_en": "",
            "next_action": None,
            "extracted_fields": {},
            "objections": [],
        }

    with patch("server.providers.get_provider_registry") as reg:
        adapter = type("A", (), {"structured_completion": AsyncMock(side_effect=fake_completion)})()
        reg.return_value.get_llm.return_value = adapter
        outcome = await process_now("bad-disp")
    assert outcome["disposition"] == "no_outcome"
    call_ledger.reset_for_tests()
    memory_manager.reset_for_tests()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_outcome_failure_does_not_fail_overall_call(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    from datetime import datetime, timezone

    from server.call.call_context import CallContext, clear_all, get as get_ctx, put
    from server.call.post_call_pipeline import _mark_outcome
    from server.providers.base import ResolvedStack, StageSelection

    clear_all()
    put(
        CallContext(
            call_id="fail-out",
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
            compiled_brain_version="cb",
            compiled_brain_text="brain",
            started_at=datetime.now(timezone.utc),
            storage_path="data/calls/fail-out/",
            status="finalizing",
            components={"ledger": "complete", "audio": "complete", "outcome": "processing"},
        )
    )
    await _mark_outcome("fail-out", "failed")
    ctx = get_ctx("fail-out")
    assert ctx is not None
    assert ctx.status == "complete"
    assert ctx.components["outcome"] == "failed"
    clear_all()
    get_settings.cache_clear()

