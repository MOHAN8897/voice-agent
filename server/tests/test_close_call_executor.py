"""Shared hangup executor: wait → pause → provider hangup → lifecycle reason."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from server.call.close_call_executor import canonical_lifecycle_reason, execute_agent_close


def test_canonical_reason_keeps_judgment_reasons():
    assert canonical_lifecycle_reason("goodbye") == "goodbye"
    assert canonical_lifecycle_reason("firm_refusal") == "firm_refusal"
    assert canonical_lifecycle_reason("goal_complete") == "goal_complete"
    assert canonical_lifecycle_reason("agent_hangup") == "agent_hangup"
    assert canonical_lifecycle_reason("nope") == "agent_hangup"


@pytest.mark.asyncio
async def test_execute_agent_close_order_and_lifecycle_reason(monkeypatch):
    monkeypatch.setattr("server.call.natural_hangup.HANGUP_TRAIL_SILENCE_SEC", 0.04)
    order: list[str] = []
    playing = {"on": True}
    ended: dict[str, str] = {}
    events: list[str] = []

    async def flush():
        order.append("flush")

    async def closing():
        order.append("closing")

    async def drain():
        order.append("drain")

    async def provider():
        order.append("provider")

    async def ended_phase():
        order.append("ended")

    async def fake_end(call_id, reason="user_stop"):
        ended["call_id"] = call_id
        ended["reason"] = reason
        order.append("lifecycle")

    def is_playing():
        return playing["on"]

    from server.call.call_lifecycle_service import call_lifecycle_service
    from server.services.pstn_media_flow import pstn_media_flow

    monkeypatch.setattr(call_lifecycle_service, "end", fake_end)

    orig_emit = pstn_media_flow.emit

    def capture_emit(identifier, stage, direction, **kwargs):
        events.append(stage)
        return orig_emit(identifier, stage, direction, **kwargs)

    monkeypatch.setattr(pstn_media_flow, "emit", capture_emit)

    async def drain_play():
        await asyncio.sleep(0.08)
        playing["on"] = False

    t0 = time.monotonic()
    asyncio.create_task(drain_play())
    result = await execute_agent_close(
        call_id="c-close",
        reason="goodbye",
        spoke_farewell=True,
        flush_audio=flush,
        is_playing=is_playing,
        on_closing=closing,
        drain_archive=drain,
        on_provider_hangup=provider,
        on_ended=ended_phase,
    )
    elapsed = time.monotonic() - t0
    assert order == ["closing", "flush", "drain", "provider", "ended", "lifecycle"]
    assert result.reason == "goodbye"
    assert result.heard_playback is True
    assert elapsed >= 0.08
    assert ended == {"call_id": "c-close", "reason": "goodbye"}
    assert "hangup_closing" in events
    assert "hangup_complete" in events
    assert events.index("hangup_closing") < events.index("hangup_complete")
