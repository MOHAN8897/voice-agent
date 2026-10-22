"""Behavioral regressions for mute outbound calls and private diagnostics."""
import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from server.services.pstn_diagnostics import PstnDiagnostics


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    from server.config.env import get_settings

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("REDIS_URL", "")
    monkeypatch.setenv("SESSION_SECRET", "pstn-diagnostic-test-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_timeline_merges_ids_redacts_and_paginates():
    store = PstnDiagnostics()
    store.record("dial.initiated", control="external", token="secret", to="+12345678901")
    store.record("lifecycle.started", call_id="internal", text="private transcript")
    store.record("call.started", control="external", call_id="internal", frames=2,
                 error="https://example.test/?token=secret", stream_url="secret")
    first = store.snapshot("internal", limit=2)
    second = store.snapshot("external", after=first["next_cursor"])
    assert len(first["events"]) == 2
    assert len(second["events"]) == 1
    assert second["events"][0]["fields"] == {"frames": 2}
    assert "secret" not in json.dumps(first) + json.dumps(second)
    assert "private transcript" not in json.dumps(first)
    assert store.snapshot("missing") is None


def test_timeline_bounds_calls_events_and_aliases():
    store = PstnDiagnostics(max_calls=2, max_events=2)
    for n in range(4):
        store.record("event", control="one", frames=n)
    assert len(store.snapshot("one")["events"]) == 2
    store.record("event", control="two")
    store.record("event", control="three")
    assert store.snapshot("one") is None
    assert "one" not in store._aliases


def test_diagnostics_still_record_with_console_logging_disabled(monkeypatch):
    from server.services import pstn_debug, pstn_diagnostics

    store = PstnDiagnostics()
    monkeypatch.setattr(pstn_diagnostics, "pstn_diagnostics", store)
    monkeypatch.setattr(pstn_debug, "_enabled", lambda: False)
    pstn_debug.log_pstn("greeting.fallback.requested", call_id="c")
    assert store.snapshot("c")["events"][0]["phase"] == "greeting.fallback.requested"


def test_endpoint_requires_signed_dev_session_and_role(monkeypatch):
    from server.auth.session import create_session_token
    from server.routes.dev_telephony import router
    from server.services import pstn_diagnostics

    store = PstnDiagnostics()
    store.record("dial.initiated", control="call-one")
    monkeypatch.setattr(pstn_diagnostics, "pstn_diagnostics", store)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        path = "/api/dev/telephony/diagnostics?call_id=call-one"
        assert client.get(path).status_code == 401
        client.cookies.set("dev_session", "forged")
        assert client.get(path).status_code == 401
        client.cookies.set("dev_session", create_session_token("app", "u", None, "administrator"))
        assert client.get(path).status_code == 401
        client.cookies.set("dev_session", create_session_token("dev", "u", None, "customer_viewer"))
        assert client.get(path).status_code == 403
        client.cookies.set("dev_session", create_session_token("dev", "u", None, "administrator"))
        result = client.get(path)
        assert result.status_code == 200
        assert result.headers["cache-control"] == "private, no-store"
        assert client.get(path + "&limit=301").status_code == 422
        assert client.get("/api/dev/telephony/diagnostics?call_id=absent").status_code == 404


@pytest.mark.asyncio
async def test_missing_prewarm_requests_opening_and_hello_cannot_be_silently_consumed():
    from server.realtime.testing import FakeRealtimeVoiceAdapter
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    adapter = FakeRealtimeVoiceAdapter()
    loop = PstnRealtimeVoiceLoop(
        session_id="diagnostic-test", call_id=None, on_agent_wire=AsyncMock(), adapter=adapter,
        stack_override={"pipeline": "realtime_voice", "direction": "outbound", "language": "en-IN"},
    )
    try:
        await loop.start_call(greeting_text="Hello, this is the test agent.")
        assert len(adapter.started_responses) == 1
        assert "Hello, this is the test agent." in adapter.started_responses[0]
        await loop._handle_pickup_or_availability("Hello", first_user=True)
        assert len(adapter.started_responses) == 2
        assert "Hello, this is the test agent." in adapter.started_responses[1]
    finally:
        await loop.close()


@pytest.mark.asyncio
async def test_no_opening_when_explicitly_disabled():
    from server.realtime.testing import FakeRealtimeVoiceAdapter
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    adapter = FakeRealtimeVoiceAdapter()
    loop = PstnRealtimeVoiceLoop(
        session_id="disabled-test", call_id=None, on_agent_wire=AsyncMock(), adapter=adapter,
        stack_override={"pipeline": "realtime_voice", "direction": "outbound"},
    )
    try:
        await loop.start_call(play_greeting=False)
        assert not adapter.started_responses
    finally:
        await loop.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["disconnect", "timeout", "unexpected"])
async def test_failed_or_stuck_send_ends_call_and_marks_unhealthy(monkeypatch, failure):
    from server.services import telnyx_pstn_bridge as mod
    from server.services.pstn_media_flow import pstn_media_flow

    ws = AsyncMock()
    if failure == "timeout":
        async def blocked(_message):
            await asyncio.Event().wait()
        ws.send_text.side_effect = blocked
    else:
        ws.send_text.side_effect = WebSocketDisconnect(1006) if failure == "disconnect" else ValueError("bad")
    monkeypatch.setattr(mod, "MEDIA_SEND_TIMEOUT_SEC", 0.01)
    bridge = mod.TelnyxPstnBridge(ws)
    bridge.call_control_id = f"test-{failure}"
    bridge._provider_hangup = AsyncMock()
    pstn_media_flow.start(external_id=bridge.call_control_id, ws_id="test", configured=bridge._configured_media)
    bridge._out_queue.put_nowait(mod.OutboundFrame(
        payload=bytes(640), codec="L16", turn_id=None, generation_id=None,
    ))
    await asyncio.wait_for(bridge._out_worker(), 0.5)
    bridge._provider_hangup.assert_awaited_once()
    assert bridge._closed
    flow = pstn_media_flow.snapshot(bridge.call_control_id)
    assert flow["health"]["checks"]["telnyx_outbound"] is False
    assert flow["health"]["failures"]


@pytest.mark.asyncio
async def test_first_audio_watchdog_records_failure_and_hangs_up(monkeypatch):
    from server.services import telnyx_pstn_bridge as mod
    from server.services.pstn_media_flow import pstn_media_flow

    monkeypatch.setattr(mod, "FIRST_OUTBOUND_AUDIO_GRACE_SEC", 0.001)
    bridge = mod.TelnyxPstnBridge(AsyncMock())
    bridge.call_control_id = "test-silence"
    bridge._provider_hangup = AsyncMock()
    pstn_media_flow.start(external_id=bridge.call_control_id, ws_id="test", configured=bridge._configured_media)
    await bridge._watch_first_outbound_audio()
    bridge._provider_hangup.assert_awaited_once()
    assert "FIRST_OUTBOUND_AUDIO_TIMEOUT" in pstn_media_flow.snapshot(bridge.call_control_id)["health"]["failures"]


def test_failed_send_is_not_reported_as_successful_transport():
    from server.services.pstn_media_flow import CallMediaConfig, PstnMediaFlowStore

    store = PstnMediaFlowStore()
    store.start(external_id="c", ws_id="w", configured=CallMediaConfig())
    store.emit("c", "outbound_sent", "outbound", frames=3)
    store.emit("c", "outbound_sent", "outbound", status="failed", detail="socket_lost")
    assert store.snapshot("c")["health"]["claim"] is None


@pytest.mark.asyncio
async def test_admin_polling_does_not_block_media_loop(monkeypatch):
    import threading

    from server.auth.session import SessionData
    from server.routes import dev_telephony
    from server.services.telnyx_client import telnyx_call_registry

    entered = threading.Event()
    release = threading.Event()

    def slow_registry(_limit):
        entered.set()
        release.wait(1.0)
        return []

    monkeypatch.setattr(dev_telephony, "active_telephony_provider", lambda: "telnyx")
    monkeypatch.setattr(dev_telephony, "_mirror_dev_telephony", AsyncMock())
    monkeypatch.setattr(telnyx_call_registry, "list_recent", slow_registry)
    session = SessionData("dev", "test", None, "administrator", 0)
    task = asyncio.create_task(dev_telephony.dev_telephony_calls(session))
    try:
        for _ in range(100):
            if entered.is_set():
                break
            await asyncio.sleep(0.005)
        assert entered.is_set()
        assert not task.done(), "registry I/O blocked the event loop until it completed"
    finally:
        release.set()
        await task


def test_media_snapshot_cannot_mutate_live_telemetry():
    from server.services.pstn_media_flow import CallMediaConfig, PstnMediaFlowStore

    store = PstnMediaFlowStore()
    store.start(external_id="c", ws_id="w", configured=CallMediaConfig())
    store.emit("c", "outbound_sent", "outbound", frames=1)
    snap = store.snapshot("c")
    snap["stages"]["outbound_sent"]["status"] = "failed"
    assert store.snapshot("c")["health"]["checks"]["telnyx_outbound"]


def test_answer_latency_uses_carrier_clock_with_both_ids(monkeypatch):
    from server.services import pstn_debug, pstn_forensics

    monkeypatch.setattr(pstn_forensics, "_find_registry_row", lambda _: (
        "external", {"internal_call_id": "internal"},
    ))
    monkeypatch.setattr(pstn_forensics, "_voice_loop", lambda *_: None)
    monkeypatch.setitem(pstn_debug._milestones, "external", {
        "answered": 5000, "first_outbound_sent": 6200,
    })
    snap = pstn_forensics.build_forensics_snapshot("internal")
    assert snap["derived_ms"]["answer_to_first_audio_sent"] == 1200
