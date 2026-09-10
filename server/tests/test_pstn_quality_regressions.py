"""Deterministic PSTN regressions; no live calls or upstream provider traffic."""
import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.routes import telnyx
from server.services.telnyx_client import TelnyxCallRegistry, TelnyxStreamTokens
from server.services.telnyx_pstn_bridge import TelnyxPstnBridge, OutboundFrame
from server.services.pstn_playback import TelnyxQueuePlayback
from server.services.pstn_voice_core import PstnVoiceLoop, pstn_call_options


@pytest.fixture
def registry(monkeypatch):
    registry = TelnyxCallRegistry()
    monkeypatch.setattr(registry, "_redis", lambda: None)
    monkeypatch.setattr(telnyx, "telnyx_call_registry", registry)
    telnyx._stream_op_locks.clear()
    return registry


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["connected", "hangup"])
async def test_start_http_response_cannot_overwrite_newer_event(monkeypatch, registry, terminal):
    registry.upsert("race", {"stream_url": "wss://example/media"})
    async def start(*args, **kwargs):
        registry.upsert("race", {"stream_connected": terminal == "connected", "ended": terminal == "hangup"})
    monkeypatch.setattr(telnyx, "TelnyxClient", lambda: SimpleNamespace(start_streaming=start))
    await telnyx._ensure_telnyx_streaming("race")
    assert registry.get("race")["stream_connected"] == (terminal == "connected")
    assert not registry.get("race").get("stream_api_ok")


@pytest.mark.asyncio
async def test_missing_ws_start_retries_and_becomes_terminal(monkeypatch, registry):
    registry.upsert("missing", {"stream_url": "wss://example/media"})
    client = SimpleNamespace(start_streaming=AsyncMock(return_value={}), hangup=AsyncMock())
    monkeypatch.setattr(telnyx, "TelnyxClient", lambda: client)
    monkeypatch.setattr(telnyx, "_STREAM_CONNECT_TIMEOUT_S", 0.001)
    await telnyx._ensure_telnyx_streaming("missing")
    await asyncio.wait_for(telnyx._stream_watchdogs["missing"], 1)
    assert client.start_streaming.await_count == 3
    assert registry.get("missing")["stream_state"] == "terminal_failed"
    client.hangup.assert_awaited_once_with("missing")


@pytest.mark.asyncio
async def test_watchdog_stops_once_ws_connects(monkeypatch, registry):
    registry.upsert("connected", {"stream_url": "wss://example/media"})
    client = SimpleNamespace(start_streaming=AsyncMock(return_value={}))
    monkeypatch.setattr(telnyx, "TelnyxClient", lambda: client)
    monkeypatch.setattr(telnyx, "_STREAM_CONNECT_TIMEOUT_S", 0.001)
    await telnyx._ensure_telnyx_streaming("connected")
    registry.upsert("connected", {"stream_connected": True})
    await telnyx._stream_watchdogs["connected"]
    assert client.start_streaming.await_count == 1


@pytest.mark.asyncio
async def test_irregular_l16_callbacks_preserve_samples_without_padding():
    bridge = TelnyxPstnBridge(SimpleNamespace())
    bridge._voice = SimpleNamespace(current_output_codec="L16", current_generation_id="g", current_turn_id="t")
    audio = bytes(range(256)) * 5
    for part in (audio[:199], audio[199:643], audio[643:]):
        await bridge._send_agent_wire(part)
    frames = [bridge._out_queue.get_nowait().payload for _ in range(bridge._out_queue.qsize())]
    assert list(map(len, frames)) == [640, 640]
    assert b"".join(frames) == audio


@pytest.mark.asyncio
async def test_drain_tracks_frame_in_flight_and_barge_clears_finished_generation():
    entered, release = asyncio.Event(), asyncio.Event()
    async def send(message):
        if json.loads(message)["event"] == "media":
            entered.set()
            await release.wait()
    bridge = TelnyxPstnBridge(SimpleNamespace(send_text=send))
    bridge._playback = TelnyxQueuePlayback(queue_size=bridge._out_queue.qsize, drain=lambda: 0,
                                          sending=lambda: bridge._out_sending)
    bridge._playback.set_current_generation("finished")
    bridge._out_queue.put_nowait(OutboundFrame(b"\0" * 640, "L16", "t", "finished"))
    worker = asyncio.create_task(bridge._out_worker())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        assert bridge._out_queue.empty()
        assert bridge._playback.is_active()
        assert not await bridge.drain_outbound(timeout_s=0.2)
        release.set()
        await bridge._barge_in()
        assert not bridge._playback.is_generation_valid("finished")
    finally:
        worker.cancel()
        await worker


@pytest.mark.asyncio
async def test_saved_config_survives_reload_and_inherits_without_explicit_stack(monkeypatch, tmp_path):
    from server.services.session_persist import SessionPersist
    from server.routes import test_studio
    from server.services import test_studio_config
    from server.routes.dev_telephony import OutboundTestBody, _resolve_outbound_source_session, _outbound_pstn_context
    monkeypatch.setattr(SessionPersist, "_path", lambda self: tmp_path / "overrides.json")
    store = SessionPersist()
    monkeypatch.setattr(test_studio, "session_persist", store)
    result = await test_studio.save_test_studio_prefs(test_studio.TestStudioUiPrefs(
        sessionId="test-studio:agent", tier="medium", language="en-IN", saveConfig=True,
        stackOverride={"pipeline": "realtime_text", "tts": {"provider": "sarvam", "model": "bulbul:v3", "config": {"speaker": "shubh"}}},
    ))
    assert result["ok"]
    # An unrelated UI autosave must not replace the committed call configuration.
    await test_studio.save_test_studio_prefs(test_studio.TestStudioUiPrefs(sessionId="test-studio:agent", tier="low"))
    monkeypatch.setattr(test_studio_config, "session_persist", SessionPersist())
    body = OutboundTestBody(toE164="+15555550123", agentId="agent", inheritTestStudioConfig=True)
    assert _resolve_outbound_source_session(body) == ("test-studio:agent", True)
    tier, language, override, _ = _outbound_pstn_context(body)
    assert (tier, language) == ("medium", "en-IN")
    assert override["tts"]["config"]["speaker"] == "shubh"
    inbound = pstn_call_options({"agent_id": "agent", "inherit_test_studio_config": True})
    assert inbound["config_session_id"] == "test-studio:agent"
    assert inbound["language"] == "en-IN"
    assert inbound["stack_override"]["pipeline"] == "realtime_text"
    assert pstn_call_options({"agent_id": "other", "inherit_test_studio_config": True})["stack_override"] is None


def test_runtime_fine_tune_values_are_not_replaced_by_preset(monkeypatch, tmp_path):
    from server.services import runtime_settings as runtime_module
    from server.services.session_persist import SessionPersist
    from server.services.runtime_settings import RuntimeSettingsStore
    monkeypatch.setattr(SessionPersist, "_path", lambda self: tmp_path / "runtime.json")
    monkeypatch.setattr(runtime_module, "session_persist", SessionPersist())
    store = RuntimeSettingsStore()
    result = store.update("test-studio:agent", {"sttSilenceMs": 250, "bargeMinWords": 1, "bargeRequireVad": False, "ttsPace": 1.1})
    assert result["sttSilenceMs"] == 250
    assert result["bargeMinWords"] == 1
    assert result["bargeRequireVad"] is False
    assert result["ttsPace"] == 1.1
    monkeypatch.setattr(runtime_module, "session_persist", SessionPersist())
    assert RuntimeSettingsStore().get("test-studio:agent") == result


def test_playback_drain_releases_pending_caller_turn():
    voice = PstnVoiceLoop(session_id="isolated", call_id=None, on_agent_wire=AsyncMock())
    voice._pending_transcript = "please change the delivery date"
    voice._arm_listen_coalesce = lambda text: setattr(voice, "result", text)
    voice.on_playback_drained()
    assert voice.result == "please change the delivery date"
    assert voice._pending_transcript is None


@pytest.mark.asyncio
async def test_lone_partial_timeout_uses_latest_caller_text(monkeypatch):
    from server.services import pstn_voice_core as core
    monkeypatch.setattr(core, "PSTN_BARGE_FINAL_TIMEOUT_S", 0.001)
    voice = PstnVoiceLoop(session_id="isolated", call_id=None, on_agent_wire=AsyncMock())
    voice._awaiting_barge_final = True
    voice._barge_epoch = time.monotonic()
    voice._last_barge_partial = "actually change my delivery address"
    voice._arm_listen_coalesce = lambda text, **kwargs: setattr(voice, "result", text)
    await voice._barge_final_timeout(voice._barge_epoch)
    assert voice.result == "actually change my delivery address"
    assert not voice._awaiting_barge_final


@pytest.mark.asyncio
async def test_prewarm_timeout_cancels_orphan_task(monkeypatch):
    from server.services import pstn_prewarm as prewarm
    cancelled = asyncio.Event()
    async def build(*args):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    monkeypatch.setattr(prewarm, "_build_prewarm_bundle", build)
    monkeypatch.setattr(prewarm, "_destroy_realtime", AsyncMock())
    registry = prewarm.PstnPrewarmRegistry()
    await registry.start("telnyx", "cold", {})
    assert await registry.take("telnyx", "cold", wait_sec=0.001) is None
    assert cancelled.is_set()
    assert not registry._entries


def test_latency_includes_coalesce_and_telnyx_buffering():
    from server.services.pstn_media_flow import PstnMediaFlowStore
    stages = [("stt_final", 1), ("llm_started", 1.15), ("llm_first_token", 1.35),
              ("tts_audio", 1.65), ("outbound_sent", 1.69)]
    metrics = PstnMediaFlowStore._latencies([{"stage": stage, "timestamp": t} for stage, t in stages])
    assert metrics["stt_final_to_llm_ms"] == 150
    assert metrics["stt_final_to_first_audio_ms"] == 690
    assert metrics["tts_generation_lag_ms"] == 300
    assert metrics["tts_first_audio_ms"] == 300


@pytest.mark.asyncio
async def test_duplicate_socket_cleanup_does_not_complete_owner_call(monkeypatch):
    from server.services import telnyx_pstn_bridge as bridge_module
    registry = TelnyxCallRegistry()
    monkeypatch.setattr(registry, "_redis", lambda: None)
    monkeypatch.setattr("server.services.telnyx_client.telnyx_call_registry", registry)
    registry.upsert("owned", {"stream_connected": True, "status": "streaming"})
    owner = object()
    monkeypatch.setitem(bridge_module.active_telnyx_bridges, "owned", owner)
    duplicate = TelnyxPstnBridge(SimpleNamespace())
    duplicate.call_control_id = "owned"
    await duplicate._cleanup("duplicate")
    assert bridge_module.active_telnyx_bridges["owned"] is owner
    assert registry.get("owned")["stream_connected"] is True
    assert registry.get("owned")["status"] == "streaming"
