"""PSTN dial-time prewarm — registry, Realtime adopt, buffered greeting."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from server.services.pstn_prewarm import (
    PstnPrewarmBundle,
    PstnPrewarmRegistry,
    prewarm_realtime_key,
    pstn_prewarm_registry,
    take_prewarm_for_answer,
)


@pytest.mark.asyncio
async def test_realtime_adopt_session_moves_key():
    from server.realtime.manager import RealtimeTextManager
    from server.realtime.testing import FakeRealtimeAdapter

    mgr = RealtimeTextManager(adapter_factory=FakeRealtimeAdapter)
    prewarm_key = prewarm_realtime_key("telnyx", "ctrl-1")
    await mgr.create(prewarm_key, instructions="hello", wait_ready=False)
    adopted = mgr.adopt_session(prewarm_key, "live-call-1")
    assert adopted is not None
    assert mgr.get(prewarm_key) is None
    assert mgr.get("live-call-1") is adopted
    assert adopted.call_id == "live-call-1"
    mgr.reset_for_tests()


@pytest.mark.asyncio
async def test_prewarm_take_returns_bundle_and_clears_entry():
    registry = PstnPrewarmRegistry()
    bundle = PstnPrewarmBundle(
        provider="telnyx",
        external_id="ctrl-2",
        realtime_key=prewarm_realtime_key("telnyx", "ctrl-2"),
        greeting_text="Hello there.",
        greeting_wire_frames=[b"\x00" * 160],
    )
    task = asyncio.create_task(asyncio.sleep(60))
    registry._entries["telnyx:ctrl-2"] = type(
        "E",
        (),
        {
            "provider": "telnyx",
            "external_id": "ctrl-2",
            "task": task,
            "created_at": 0.0,
            "bundle": bundle,
            "error": None,
        },
    )()
    taken = await registry.take("telnyx", "ctrl-2")
    assert taken is bundle
    assert "telnyx:ctrl-2" not in registry._entries
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_prewarm_cancel_removes_entry_and_closes_realtime():
    registry = PstnPrewarmRegistry()
    rt_key = prewarm_realtime_key("exotel", "sid-9")
    done = asyncio.Event()

    async def sleeper():
        await done.wait()

    task = asyncio.create_task(sleeper())
    registry._entries["exotel:sid-9"] = type(
        "E",
        (),
        {
            "provider": "exotel",
            "external_id": "sid-9",
            "task": task,
            "created_at": 0.0,
            "bundle": None,
            "error": None,
        },
    )()
    destroy = AsyncMock()
    with patch("server.services.pstn_prewarm._destroy_realtime", destroy):
        await registry.cancel("exotel", "sid-9")
    destroy.assert_awaited_once_with(rt_key)
    assert "exotel:sid-9" not in registry._entries
    done.set()


@pytest.mark.asyncio
async def test_take_prewarm_for_answer_fallback_id():
    registry = PstnPrewarmRegistry()
    bundle = PstnPrewarmBundle(
        provider="plivo",
        external_id="req-1",
        realtime_key=prewarm_realtime_key("plivo", "req-1"),
        greeting_text="Hi",
        greeting_wire_frames=[],
    )
    task = asyncio.create_task(asyncio.sleep(60))
    registry._entries["plivo:req-1"] = type(
        "E",
        (),
        {
            "provider": "plivo",
            "external_id": "req-1",
            "task": task,
            "created_at": 0.0,
            "bundle": bundle,
            "error": None,
        },
    )()
    with patch.object(pstn_prewarm_registry, "take", registry.take):
        taken = await take_prewarm_for_answer("plivo", "call-uuid-x", fallback_external_id="req-1")
    assert taken is bundle
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_stale_brain_keeps_buffered_greeting():
    bundle = PstnPrewarmBundle(
        provider="telnyx",
        external_id="ctrl-stale",
        realtime_key=prewarm_realtime_key("telnyx", "ctrl-stale"),
        greeting_text="Hi, this is Priya.",
        greeting_wire_frames=[b"\x00" * 640],
        compiled_brain_version="session-v1",
        agent_id="agent-1",
    )
    registry = PstnPrewarmRegistry()
    task = asyncio.create_task(asyncio.sleep(60))
    registry._entries["telnyx:ctrl-stale"] = type(
        "E",
        (),
        {
            "provider": "telnyx",
            "external_id": "ctrl-stale",
            "task": task,
            "created_at": 0.0,
            "bundle": bundle,
            "error": None,
        },
    )()
    destroy = AsyncMock()
    with (
        patch.object(pstn_prewarm_registry, "take", registry.take),
        patch("server.services.pstn_prewarm._destroy_realtime", destroy),
        patch(
            "server.call.call_lifecycle_service.call_lifecycle_service._resolve_agent",
            AsyncMock(return_value={"active_compiled_brain_version": "cb_new"}),
        ),
    ):
        taken = await take_prewarm_for_answer("telnyx", "ctrl-stale")
    assert taken is bundle
    assert taken.greeting_wire_frames
    assert taken.realtime_key is None
    destroy.assert_awaited_once()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_start_call_uses_buffered_greeting_not_speak():
    from server.services.pstn_voice_core import PstnVoiceLoop

    loop = PstnVoiceLoop(
        session_id="test-studio",
        call_id="call-abc",
        on_agent_wire=AsyncMock(),
        sample_rate=8000,
        tts_output_codec="mulaw",
    )
    frames = [b"\xff" * 160, b"\xfe" * 160]
    speak = AsyncMock()
    play_buffered = AsyncMock()
    open_stt = AsyncMock()
    loop.speak = speak
    loop._play_buffered_greeting = play_buffered
    loop.open_stt = open_stt

    await loop.start_call(
        play_greeting=True,
        greeting_wire_frames=frames,
        greeting_text="Namaste!",
    )

    open_stt.assert_awaited_once()
    play_buffered.assert_awaited_once_with(frames, "Namaste!")
    speak.assert_not_called()
