"""Call ledger A — append-only, never truncated."""
from __future__ import annotations

import pytest

from server.call.call_ledger import call_ledger
from server.config.env import get_settings


@pytest.fixture
def ledger(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    call_ledger.reset_for_tests()
    yield call_ledger
    call_ledger.reset_for_tests()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_append_order_and_no_truncation(ledger):
    call_id = "ledger-1"
    await ledger.init(call_id, {"call_id": call_id, "combination_id": "abc"})
    for i in range(12):
        await ledger.append_user_turn(call_id, f"user-{i}")
        await ledger.append_assistant_turn(call_id, f"agent-{i}")
    lines = ledger.read_lines(call_id)
    assert len(lines) == 24
    assert lines[0]["seq"] == 1
    assert lines[-1]["seq"] == 24
    assert lines[0]["role"] == "user"
    assert lines[1]["role"] == "assistant"
    assert lines[0]["text"] == "user-0"


@pytest.mark.asyncio
async def test_seal_rejects_further_appends(ledger):
    call_id = "ledger-seal"
    await ledger.init(call_id, {"call_id": call_id})
    await ledger.append_user_turn(call_id, "hello")
    await ledger.seal(call_id)
    with pytest.raises(RuntimeError, match="sealed"):
        await ledger.append_assistant_turn(call_id, "nope")
    assert len(ledger.read_lines(call_id)) == 1


def test_stamp_ended_usage_refreshes_post_call_transcript_cost(ledger):
    call_id = "stamp-post-call-tx"
    ledger.write_meta(
        call_id,
        {
            "call_id": call_id,
            "channel": "pstn",
            "pipeline": "realtime_voice",
            "callee_e164": "+919876543210",
            "direction": "outbound",
            "usage": {
                "llm_model": "gemini-3.8-live",
                "model_cost_usd": 0.05,
                "model_cost_inr": 4.78,
                "post_call_transcript_usd": 0.0045,
                "post_call_transcript_model": "gemini-3.5-transcribe",
            },
            "post_call_transcript": {"status": "complete", "lines": 4},
        },
    )
    ledger.stamp_ended_usage(call_id, reason="pstn_hangup", duration_sec=120)
    usage = ledger.read_meta(call_id)["usage"]
    expected_tx = 120 / 60.0 * 0.009
    assert abs(float(usage["post_call_transcript_usd"]) - expected_tx) < 1e-9
    total = float(usage["model_cost_usd"]) + float(usage["telnyx_usd"]) + expected_tx
    assert abs(float(usage["cost_usd"]) - total) < 1e-9


@pytest.mark.asyncio
async def test_user_turn_records_stt_latency(ledger):
    call_id = "ledger-stt"
    await ledger.init(call_id, {"call_id": call_id})
    line = await ledger.append_user_turn(call_id, "hello", stt_latency_ms=120)
    assert line["stt_latency_ms"] == 120
    assert ledger.read_lines(call_id)[0]["stt_latency_ms"] == 120
