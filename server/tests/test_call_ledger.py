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


@pytest.mark.asyncio
async def test_user_turn_records_stt_latency(ledger):
    call_id = "ledger-stt"
    await ledger.init(call_id, {"call_id": call_id})
    line = await ledger.append_user_turn(call_id, "hello", stt_latency_ms=120)
    assert line["stt_latency_ms"] == 120
    assert ledger.read_lines(call_id)[0]["stt_latency_ms"] == 120
