"""Natural hangup waits for farewell playback, then a short human pause."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from server.call.natural_hangup import (
    HANGUP_TRAIL_SILENCE_SEC,
    pause_before_disconnect,
    wait_for_farewell_playback,
)


@pytest.mark.asyncio
async def test_wait_returns_immediately_when_idle():
    heard = await wait_for_farewell_playback(lambda: False, timeout_sec=1.0)
    assert heard is False


@pytest.mark.asyncio
async def test_wait_can_grace_for_playback_to_start():
    state = {"playing": False}

    async def start_later():
        await asyncio.sleep(0.08)
        state["playing"] = True
        await asyncio.sleep(0.08)
        state["playing"] = False

    asyncio.create_task(start_later())
    heard = await wait_for_farewell_playback(
        lambda: state["playing"],
        timeout_sec=1.0,
        poll_sec=0.02,
        wait_for_start_sec=0.2,
    )
    assert heard is True


@pytest.mark.asyncio
async def test_wait_until_playback_drains():
    state = {"playing": True}

    async def stop_later():
        await asyncio.sleep(0.12)
        state["playing"] = False

    asyncio.create_task(stop_later())
    t0 = time.monotonic()
    heard = await wait_for_farewell_playback(lambda: state["playing"], timeout_sec=1.0, poll_sec=0.02)
    elapsed = time.monotonic() - t0
    assert heard is True
    assert elapsed >= 0.1
    assert elapsed < 0.8


@pytest.mark.asyncio
async def test_pause_before_disconnect_holds_the_line():
    t0 = time.monotonic()
    await pause_before_disconnect(should_pause=True, trail_sec=0.08)
    assert time.monotonic() - t0 >= 0.07
    t1 = time.monotonic()
    await pause_before_disconnect(should_pause=False, trail_sec=HANGUP_TRAIL_SILENCE_SEC)
    assert time.monotonic() - t1 < 0.05


@pytest.mark.asyncio
async def test_classic_hangup_waits_for_playback_then_disconnects(monkeypatch):
    from server.call.call_lifecycle_service import call_lifecycle_service as lifecycle
    from server.services.pstn_voice_core import PstnVoiceLoop

    monkeypatch.setattr("server.call.natural_hangup.HANGUP_TRAIL_SILENCE_SEC", 0.04)
    ended: dict[str, object] = {}
    hung_up_at: dict[str, float] = {}
    playing = {"on": True}

    class Playback:
        def is_active(self):
            return playing["on"]

    async def fake_end(call_id, reason="user_stop"):
        ended["call_id"] = call_id
        ended["reason"] = reason

    async def on_hangup():
        hung_up_at["at"] = time.monotonic()

    loop = PstnVoiceLoop(session_id="s", call_id="c-natural", on_agent_wire=AsyncMock())
    loop.playback = Playback()
    loop.set_hangup_handler(on_hangup)
    monkeypatch.setattr(lifecycle, "end", fake_end)

    async def drain():
        await asyncio.sleep(0.12)
        playing["on"] = False

    t0 = time.monotonic()
    asyncio.create_task(drain())
    await loop._finish_agent_hangup(reason="agent_hangup", spoke_farewell=True)
    assert hung_up_at.get("at") is not None
    assert hung_up_at["at"] - t0 >= 0.12
    assert ended == {"call_id": "c-natural", "reason": "agent_hangup"}
    assert playing["on"] is False
