"""Regression coverage for the September 27 watchdog/farewell failure."""
import asyncio
import json
import time
from unittest.mock import AsyncMock

import pytest

from server.realtime.testing import FakeRealtimeVoiceAdapter
from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop
from server.services.telnyx_pstn_bridge import TelnyxPstnBridge


def voice(language="en-IN"):
    loop = PstnRealtimeVoiceLoop(
        session_id="hangup-test", call_id=None, on_agent_wire=AsyncMock(),
        adapter=FakeRealtimeVoiceAdapter(),
        stack_override={"pipeline": "realtime_voice", "language": language},
    )
    loop._on_remote_hangup = AsyncMock()
    return loop


@pytest.mark.asyncio
async def test_watchdog_does_not_cancel_itself_before_provider_await(monkeypatch):
    monkeypatch.setattr("server.services.pstn_realtime_voice_core.HANGUP_RESPONSE_TIMEOUT_SEC", 0.01)
    loop = voice()
    loop._pending_end_call = {"reason": "firm_refusal"}
    loop._response_had_audio = True
    loop._response_activity_at = time.monotonic() - 2

    async def provider():
        # Reproduces the first suspension where the old watchdog self-cancelled.
        await asyncio.sleep(0)

    loop._on_remote_hangup.side_effect = provider
    loop._schedule_hangup_force_finish()
    task = loop._hangup_force_task
    await asyncio.wait_for(task, 1)
    assert not task.cancelled()
    loop._on_remote_hangup.assert_awaited_once()
    await loop._background_hangup_task


@pytest.mark.asyncio
async def test_streaming_gap_is_not_farewell_completion(monkeypatch):
    monkeypatch.setattr("server.services.pstn_realtime_voice_core.HANGUP_RESPONSE_TIMEOUT_SEC", 0.3)
    loop = voice()
    loop._pending_end_call = {"reason": "goodbye"}
    loop._response_had_audio = True
    loop._response_open = True
    loop._response_activity_at = time.monotonic() - 2
    loop._schedule_hangup_force_finish()
    await asyncio.sleep(0.07)
    loop._on_remote_hangup.assert_not_awaited()
    await loop._handle_event({"type": "response_done"})
    loop._on_remote_hangup.assert_awaited_once()
    await loop._background_hangup_task


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["en-IN", "te-IN", "hi-IN", "ta-IN", "ar", "ja"])
async def test_farewell_completion_is_language_independent(language):
    loop = voice(language)
    loop._pending_end_call = {"reason": "goodbye"}
    loop._response_had_audio = True
    loop._assistant_text = ""
    playing = True
    loop.is_agent_audio_active = lambda: playing
    done = asyncio.create_task(loop._finalize_hangup_after_farewell())
    await asyncio.sleep(0)
    loop._on_remote_hangup.assert_not_awaited()
    playing = False
    await asyncio.wait_for(done, 0.3)
    loop._on_remote_hangup.assert_awaited_once()
    assert loop._close_listen_until == 0
    await loop._background_hangup_task


@pytest.mark.asyncio
async def test_tool_acceptance_preserves_current_gemini_farewell():
    from server.realtime.providers.gemini_voice import GeminiLiveVoiceAdapter

    loop = voice()
    adapter = GeminiLiveVoiceAdapter()
    adapter._active_response_id = "farewell"
    adapter._accepting = True
    loop._adapter = adapter
    await loop._arm_accepted_hangup(
        {"should_end": True, "reason": "goodbye", "farewell": "Bye"}, tool_sourced=True,
    )
    assert adapter._active_response_id == "farewell"
    assert adapter._accepting
    assert "farewell" not in adapter._cancelled_response_ids
    loop._cancel_hangup_force_task()


@pytest.mark.asyncio
async def test_provider_failure_leaves_voice_retryable():
    loop = voice()
    loop._on_remote_hangup.side_effect = [RuntimeError("network"), None]
    with pytest.raises(RuntimeError):
        await loop._finish_hangup()
    assert not loop._hangup_started
    assert not loop._closed
    await loop._finish_hangup()
    assert loop._on_remote_hangup.await_count == 2
    await loop._background_hangup_task


@pytest.mark.asyncio
async def test_slow_archive_and_notice_do_not_delay_disconnect():
    loop = voice()
    blocked = asyncio.Event()
    loop._drain_agent_archive = AsyncMock(side_effect=blocked.wait)
    loop._on_hangup_notice = lambda *_: blocked.wait()
    await asyncio.wait_for(loop._finish_hangup(), 0.3)
    loop._on_remote_hangup.assert_awaited_once()
    assert not loop._background_hangup_task.done()
    blocked.set()
    await loop._background_hangup_task


@pytest.mark.asyncio
async def test_telnyx_mark_ack_is_required_before_provider_command(monkeypatch):
    ws = AsyncMock()
    bridge = TelnyxPstnBridge(ws)
    bridge.call_control_id = "test-control"
    bridge.drain_outbound = AsyncMock(return_value=True)
    provider = AsyncMock()
    monkeypatch.setattr("server.services.telnyx_client.TelnyxClient.hangup", provider)
    task = asyncio.create_task(bridge._provider_hangup())
    await asyncio.sleep(0)
    mark = json.loads(ws.send_text.call_args.args[0])["mark"]["name"]
    provider.assert_not_awaited()
    bridge._ack_playback_mark("unrelated")
    provider.assert_not_awaited()
    bridge._ack_playback_mark(mark)
    await task
    provider.assert_awaited_once()
    assert bridge._hangup_sent
    assert not bridge._playback_marks


@pytest.mark.asyncio
async def test_telnyx_failure_does_not_latch_sent_and_concurrent_retry_is_once(monkeypatch):
    bridge = TelnyxPstnBridge(AsyncMock())
    bridge.call_control_id = "test-control"
    bridge.drain_outbound = AsyncMock(return_value=True)
    bridge._wait_provider_playback = AsyncMock(return_value=True)
    provider = AsyncMock(side_effect=[RuntimeError("network"), {}])
    monkeypatch.setattr("server.services.telnyx_client.TelnyxClient.hangup", provider)
    with pytest.raises(RuntimeError):
        await bridge._provider_hangup()
    assert not bridge._hangup_sent
    await asyncio.gather(bridge._provider_hangup(), bridge._provider_hangup())
    assert provider.await_count == 2


@pytest.mark.asyncio
async def test_lost_mark_has_bounded_fallback():
    bridge = TelnyxPstnBridge(AsyncMock())
    assert not await bridge._wait_provider_playback(timeout_s=0.01)
    assert not bridge._playback_marks


@pytest.mark.asyncio
async def test_telnyx_retry_reuses_command_id():
    from server.services.telnyx_client import TelnyxApiError, TelnyxClient

    client = TelnyxClient(cfg={})
    client._request = AsyncMock(side_effect=[
        TelnyxApiError("unavailable", status=503), {"data": {"result": "ok"}},
    ])
    assert await client.hangup("test-control") == {"result": "ok"}
    first, second = client._request.await_args_list
    assert first.kwargs["json"]["command_id"] == second.kwargs["json"]["command_id"]


@pytest.mark.asyncio
async def test_telnyx_validation_error_is_not_success():
    from server.services.telnyx_client import TelnyxApiError, TelnyxClient

    client = TelnyxClient(cfg={})
    client._request = AsyncMock(side_effect=TelnyxApiError(
        "invalid parameter", status=422, body='{"errors":[{"code":"10015"}]}',
    ))
    with pytest.raises(TelnyxApiError):
        await client.hangup("test-control")
    client._request.side_effect = TelnyxApiError(
        "ended", status=422, body='{"errors":[{"code":"90018"}]}',
    )
    assert await client.hangup("test-control") == {}


@pytest.mark.asyncio
async def test_classic_close_returns_before_archive_work():
    from server.call.close_call_executor import execute_agent_close

    release = asyncio.Event()
    provider = AsyncMock()
    result = await asyncio.wait_for(execute_agent_close(
        call_id=None, reason="goodbye", on_provider_hangup=provider,
        drain_archive=release.wait,
    ), 0.3)
    provider.assert_awaited_once()
    release.set()
    await result.background_task
