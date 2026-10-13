"""Carrier teardown, delayed acknowledgements and callback authentication regressions."""
import base64
import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from server.routes import vobiz as routes
from server.services import vobiz_client as client
from server.services import vobiz_pstn_bridge as bridge_module
from server.services.pstn_playback import EstimatedPlaybackTracker


@pytest.fixture
def isolated(monkeypatch):
    registry = client.VobizCallRegistry()
    tokens = client.VobizStreamTokens()
    monkeypatch.setattr(registry, "_redis", lambda: None)
    monkeypatch.setattr(tokens, "_redis", lambda: None)
    monkeypatch.setattr(routes, "vobiz_call_registry", registry)
    monkeypatch.setattr(routes, "vobiz_stream_tokens", tokens)
    monkeypatch.setattr(bridge_module, "vobiz_call_registry", registry)
    monkeypatch.setattr(bridge_module, "active_vobiz_bridges", {})
    monkeypatch.setattr(routes, "get_settings", lambda: SimpleNamespace(
        app_environment="production", vobiz_auth_token="test-secret"))
    from server.services.dev_secrets_store import dev_secrets_store
    monkeypatch.setattr(dev_secrets_store, "effective_secret", lambda key: None)
    monkeypatch.setattr(routes, "public_api_base", lambda: "https://voice.example")
    return registry, tokens


def request(path="/api/vobiz/hangup", query="", headers=None):
    return Request({"type": "http", "scheme": "http", "method": "POST",
                    "server": ("internal", 8000), "path": path,
                    "query_string": query.encode(),
                    "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]})


def test_known_call_id_is_not_authentication(isolated):
    registry, _ = isolated
    registry.upsert("call-a", {"status": "streaming"})
    with pytest.raises(HTTPException) as error:
        routes._verify_vobiz_request(request(), {"CallUUID": "call-a"})
    assert error.value.status_code == 401


@pytest.mark.parametrize("environment,secret", [("development", "configured"), ("production", ""), ("staging", "")])
def test_unsigned_callbacks_fail_closed_for_real_carrier_configuration(isolated, monkeypatch, environment, secret):
    monkeypatch.setattr(routes, "get_settings", lambda: SimpleNamespace(
        app_environment=environment, vobiz_auth_token=secret))
    with pytest.raises(HTTPException) as error:
        routes._verify_vobiz_request(request(), {})
    assert error.value.status_code == 401


def test_unconsumed_token_cannot_authorize_another_carrier_call(isolated):
    _, tokens = isolated
    token = tokens.create(call_uuid="call-a")
    with pytest.raises(HTTPException, match="Call token mismatch"):
        routes._verify_vobiz_request(request(query=f"token={token}"), {"CallUUID": "call-b"})


@pytest.mark.asyncio
async def test_media_start_cannot_override_authorized_call(isolated):
    registry, _ = isolated
    ws = MagicMock(close=AsyncMock())
    bridge = bridge_module.VobizPstnBridge(ws)
    bridge._token_meta = {"call_uuid": "call-a"}
    with pytest.raises(ValueError, match="authorized call"):
        await bridge._on_start({"start": {"callId": "call-b"}})
    assert bridge.call_uuid is None
    assert registry.get("call-b") is None


def test_consumed_media_token_authenticates_bound_hangup_only(isolated):
    registry, tokens = isolated
    token = tokens.create(call_uuid="call-a")
    registry.upsert("call-a", {"webhook_token": token})
    tokens.consume(token)
    routes._verify_vobiz_request(request(query=f"token={token}"), {"CallUUID": "call-a"})
    for path, call in [("/api/vobiz/answer", "call-a"), ("/api/vobiz/hangup", "call-b")]:
        with pytest.raises(HTTPException):
            routes._verify_vobiz_request(request(path, f"token={token}"), {"CallUUID": call, "outbound_id": "call-a"})


@pytest.mark.parametrize("version,joiner", [("v3", "."), ("v2", "")])
def test_signature_uses_public_url_and_survives_consumed_token(isolated, version, joiner):
    nonce = "test-nonce"
    digest = base64.b64encode(hmac.new(b"test-secret",
        f"https://voice.example/api/vobiz/hangup{joiner}{nonce}".encode(), hashlib.sha256).digest()).decode()
    headers = {f"X-Vobiz-Signature-{version}": digest, f"X-Vobiz-Signature-{version}-Nonce": nonce}
    routes._verify_vobiz_request(request(query="token=already-consumed", headers=headers), {})
    headers[f"X-Vobiz-Signature-{version}"] = "forged"
    with pytest.raises(HTTPException):
        routes._verify_vobiz_request(request(headers=headers), {})


@pytest.mark.parametrize("duration", ["bad", "NaN", "Infinity", "-5", ""])
@pytest.mark.asyncio
async def test_bad_duration_does_not_lose_hangup_callback(isolated, monkeypatch, duration):
    registry, tokens = isolated
    token = tokens.create(call_uuid="call-a")
    monkeypatch.setattr(routes, "_parse_vobiz_payload", AsyncMock(return_value={
        "CallUUID": "call-a", "Duration": duration, "token": token}))
    assert (await routes.vobiz_hangup(request()))["ok"]
    assert registry.get("call-a")["duration_sec"] == 0


def make_bridge():
    ws = MagicMock(send_text=AsyncMock(), close=AsyncMock())
    bridge = bridge_module.VobizPstnBridge(ws)
    bridge.call_uuid = "call-a"
    bridge.stream_id = "stream-a"
    bridge._playback = EstimatedPlaybackTracker()
    bridge._voice = MagicMock(current_generation_id="generation-a")
    return bridge


@pytest.mark.asyncio
async def test_failed_rest_hangup_closes_socket_and_is_idempotent(isolated, monkeypatch):
    bridge = make_bridge()
    monkeypatch.setattr(client, "vobiz_enabled", lambda: True)
    hangup = AsyncMock(side_effect=RuntimeError("carrier unavailable"))
    monkeypatch.setattr(client, "VobizClient", lambda: SimpleNamespace(hangup_call=hangup))
    await bridge.hangup()
    await bridge.hangup()
    bridge.ws.close.assert_awaited_once()
    hangup.assert_awaited_once_with("call-a")
    assert bridge._closed


@pytest.mark.asyncio
async def test_total_disconnect_failure_is_retryable(isolated, monkeypatch):
    bridge = make_bridge()
    monkeypatch.setattr(client, "vobiz_enabled", lambda: False)
    bridge.ws.close.side_effect = RuntimeError("socket busy")
    with pytest.raises(RuntimeError, match="disconnect both failed"):
        await bridge.hangup()
    assert not bridge._closed
    bridge.ws.close.side_effect = None
    await bridge.hangup()
    assert bridge._closed


@pytest.mark.asyncio
async def test_stalled_rest_and_socket_disconnect_are_bounded(isolated, monkeypatch):
    import asyncio
    bridge = make_bridge()
    real_wait_for = asyncio.wait_for
    timeouts = []

    async def short_wait(awaitable, timeout):
        timeouts.append(timeout)
        return await real_wait_for(awaitable, timeout=0.01)

    async def stall(*args):
        await asyncio.Event().wait()

    monkeypatch.setattr(client, "vobiz_enabled", lambda: True)
    monkeypatch.setattr(client, "VobizClient", lambda: SimpleNamespace(hangup_call=stall))
    monkeypatch.setattr(bridge_module.asyncio, "wait_for", short_wait)
    bridge.ws.close.side_effect = stall
    with pytest.raises(RuntimeError, match="disconnect both failed"):
        await real_wait_for(bridge.hangup(), timeout=0.5)
    assert timeouts == [5.0, 2.0]
    assert not bridge._closed


@pytest.mark.asyncio
async def test_stale_or_wrong_stream_checkpoint_cannot_drain_new_audio(isolated):
    bridge = make_bridge()
    await bridge._mark_turn_end()
    first = json.loads(bridge.ws.send_text.call_args.args[0])["name"]
    await bridge._send_agent_wire(b"\x00" * 640)
    bridge._on_played_stream({"name": first, "streamId": bridge.stream_id})
    assert bridge._playback.is_active()
    await bridge._mark_turn_end()
    latest = json.loads(bridge.ws.send_text.call_args.args[0])["name"]
    assert latest != first
    bridge._on_played_stream({"name": latest, "streamId": "wrong-stream"})
    assert bridge._playback.is_active()
    bridge._on_played_stream({"name": latest, "streamId": bridge.stream_id})
    assert not bridge._playback.is_active()
    bridge._voice.on_playback_drained.assert_called_once()


@pytest.mark.asyncio
async def test_late_clear_ack_and_malformed_json_do_not_erase_new_playback(isolated):
    bridge = make_bridge()
    bridge._playback.note_sent_frames(100)
    bridge._cleanup = AsyncMock()
    bridge.ws.receive = AsyncMock(side_effect=[
        {"type": "websocket.receive", "text": "[]"},
        {"type": "websocket.receive", "text": '{"event":"clearedAudio"}'},
        {"type": "websocket.disconnect"},
    ])
    await bridge.run(agent_id=None, tier=None, token_meta={})
    assert bridge._playback.is_active()
    bridge._voice.on_playback_drained.assert_not_called()


@pytest.mark.asyncio
async def test_old_cleanup_does_not_remove_replacement_bridge(isolated):
    bridge = make_bridge()
    bridge._voice = None
    bridge._owns_call = True
    replacement = make_bridge()
    bridge_module.active_vobiz_bridges[bridge.call_uuid] = replacement
    await bridge._cleanup("test")
    assert bridge_module.active_vobiz_bridges[bridge.call_uuid] is replacement


def test_xml_hangs_up_after_media_closes():
    import xml.etree.ElementTree as ET
    root = ET.fromstring(routes._build_vobiz_xml_response("wss://voice.example/media?a=1&b=2").body)
    assert [node.tag for node in root] == ["Stream", "Hangup"]
    assert root[0].attrib["audioTrack"] == "inbound"
    assert root[0].attrib["keepCallAlive"] == "true"


@pytest.mark.asyncio
async def test_admission_counts_calls_not_aliases(isolated, monkeypatch):
    import asyncio
    from server.config import env
    from server.services import pstn_prewarm
    monkeypatch.setattr(env, "get_settings", lambda: SimpleNamespace(vobiz_max_concurrent_calls=2))
    monkeypatch.setattr(pstn_prewarm, "take_prewarm_for_answer", AsyncMock(return_value=None))
    monkeypatch.setattr(bridge_module, "pstn_call_options", lambda opts: {})
    monkeypatch.setattr(bridge_module, "create_pstn_voice_loop", lambda **kw: MagicMock())
    first = make_bridge()
    for key in ("call-1", "request-1", "outbound-1", "ws-1"):
        bridge_module.active_vobiz_bridges[key] = first
    second = make_bridge()
    second._start_voice_loop = AsyncMock()
    await second._on_start({"start": {"callId": "call-2", "streamId": "stream-2"}})
    await asyncio.sleep(0)
    assert bridge_module.active_vobiz_bridges["call-2"] is second
    third = make_bridge()
    with pytest.raises(RuntimeError, match="concurrent call limit"):
        await third._on_start({"start": {"callId": "call-3", "streamId": "stream-3"}})


@pytest.mark.parametrize("rate,frame_bytes", [(8000, 320), (16000, 640)])
@pytest.mark.asyncio
async def test_linear16_output_matches_negotiated_rate(isolated, rate, frame_bytes):
    bridge = make_bridge()
    bridge._wire_codec = "linear16"
    bridge._wire_sample_rate = rate
    await bridge._send_agent_wire(b"\x01" * frame_bytes)
    media = json.loads(bridge.ws.send_text.call_args.args[0])["media"]
    assert media["sampleRate"] == rate
    assert len(base64.b64decode(media["payload"])) == frame_bytes
