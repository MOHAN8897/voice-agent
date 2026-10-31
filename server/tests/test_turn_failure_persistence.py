"""Failed turns are kept, counted, alerted, and tagged for admin surfaces."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from server.call import call_ledger as ledger_module
from server.call.outcome_schema import derive_status_tags
from server.services import turn_failure_log


@pytest.mark.asyncio
async def test_failed_turn_is_kept_counted_and_survives_for_admin(monkeypatch, tmp_path):
    monkeypatch.setattr(ledger_module, "call_dir", lambda call_id: tmp_path / call_id)
    alerts: list[dict] = []
    monkeypatch.setattr(turn_failure_log, "_schedule_alert", lambda record: alerts.append(record))
    (tmp_path / "call-1").mkdir()
    ledger_module.call_ledger.write_meta("call-1", {"existing": True})

    record = await turn_failure_log.record_turn_failure(
        call_id="call-1",
        tenant_id=None,
        agent_id=None,
        transcript="what is the price",
        partial_text="The price is",
        finish_reason="length",
        error_type="IncompleteTurnError",
        error="sarvam did not complete the turn (length)",
        delivered=False,
        turn_completed=False,
        retry_used=True,
        watchdog_retry=False,
        tool_wait=False,
    )

    assert record["finish_reason"] == "length"
    stored = ledger_module.call_ledger.read_failed_turns("call-1")
    assert len(stored) == 1
    assert stored[0]["partial_text"] == "The price is"
    assert stored[0]["transcript"] == "what is the price"
    assert stored[0]["retry_used"] is True
    assert stored[0]["delivered"] is False

    meta = ledger_module.call_ledger.read_meta("call-1")
    assert meta["existing"] is True
    assert meta["agent_failure_count"] == 1
    assert meta["agent_failure_last"]["finish_reason"] == "length"

    assert alerts and alerts[0]["error_type"] == "IncompleteTurnError"


@pytest.mark.asyncio
async def test_failed_turn_raises_a_platform_error_alert(monkeypatch):
    from server.services.saas import activity_log

    recorded = AsyncMock()
    monkeypatch.setattr(activity_log, "record_event", recorded)

    await turn_failure_log._alert(
        {
            "call_id": "call-1",
            "tenant_id": None,
            "finish_reason": "length",
            "error_type": "IncompleteTurnError",
            "retry_used": True,
            "watchdog_retry": False,
            "tool_wait": False,
            "partial_text": "The price is",
            "delivered": False,
        }
    )

    recorded.assert_awaited_once()
    kwargs = recorded.await_args.kwargs
    assert kwargs["action"] == "call.agent_failure"
    assert kwargs["outcome"] == "error"
    assert kwargs["severity"] == "error"
    assert kwargs["resource_id"] == "call-1"
    assert kwargs["payload"]["finish_reason"] == "length"


def test_agent_failure_is_a_deterministic_quality_tag():
    tags = derive_status_tags("new_lead", {}, agent_failure=True)
    assert "quality:agent_failure" in tags
    assert "quality:agent_failure" not in derive_status_tags("new_lead", {})


def test_every_failed_turn_keeps_the_channel_open_for_review(tmp_path, monkeypatch):
    """A second failure appends; nothing rewrites or drops the first record."""
    monkeypatch.setattr(ledger_module, "call_dir", lambda call_id: tmp_path / call_id)
    monkeypatch.setattr(turn_failure_log, "_schedule_alert", lambda record: None)

    import asyncio

    async def run():
        await turn_failure_log.record_turn_failure(
            call_id="call-2", tenant_id=None, agent_id=None, transcript="a",
            partial_text="", finish_reason="length", error_type="IncompleteTurnError",
            error="length", delivered=False, turn_completed=False,
            retry_used=False, watchdog_retry=False, tool_wait=False,
        )
        await turn_failure_log.record_turn_failure(
            call_id="call-2", tenant_id=None, agent_id=None, transcript="b",
            partial_text="", finish_reason="content_filter", error_type="IncompleteTurnError",
            error="content_filter", delivered=False, turn_completed=False,
            retry_used=False, watchdog_retry=False, tool_wait=False,
        )

    asyncio.run(run())

    stored = ledger_module.call_ledger.read_failed_turns("call-2")
    assert [row["transcript"] for row in stored] == ["a", "b"]
    assert ledger_module.call_ledger.read_meta("call-2")["agent_failure_count"] == 2
