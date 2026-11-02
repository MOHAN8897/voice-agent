"""A media socket Vobiz opens but never starts is reopened once on the same call, then ended."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlsplit

import pytest
from starlette.requests import Request

from server.routes import vobiz as routes
from server.routes import vobiz_ws as ws_route
from server.services import vobiz_client as client
from server.services import vobiz_pstn_bridge as bridge_module


@pytest.fixture
def isolated(monkeypatch):
    registry = client.VobizCallRegistry()
    tokens = client.VobizStreamTokens()
    monkeypatch.setattr(registry, "_redis", lambda: None)
    monkeypatch.setattr(tokens, "_redis", lambda: None)
    monkeypatch.setattr(tokens, "_shared_required", lambda: False)
    monkeypatch.setattr(client, "get_settings", lambda: SimpleNamespace(app_environment="development"))
    for module in (routes, ws_route, bridge_module):
        monkeypatch.setattr(module, "vobiz_call_registry", registry)
        monkeypatch.setattr(module, "vobiz_stream_tokens", tokens)
    monkeypatch.setattr(bridge_module, "active_vobiz_bridges", {})
    monkeypatch.setattr(bridge_module, "VOBIZ_START_EVENT_WAIT_SEC", 0.05)
    from server.config import urls
    monkeypatch.setattr(urls, "public_api_base", lambda: "https://voice.example")
    carrier = SimpleNamespace(transfer_call=AsyncMock(return_value={}))
    from server.services.saas import voice_kyc_service
    monkeypatch.setattr(voice_kyc_service, "vobiz_client_for_call", AsyncMock(return_value=carrier))
    return registry, tokens, carrier


def silent_socket():
    async def never():
        await asyncio.Event().wait()
    return MagicMock(receive=never, close=AsyncMock(), send_text=AsyncMock())


async def run_silent_bridge(meta):
    bridge = bridge_module.VobizPstnBridge(silent_socket())
    bridge.hangup = AsyncMock()
    await asyncio.wait_for(bridge.run(agent_id="agent", tier="medium", token_meta=meta), timeout=5)
    return bridge


@pytest.mark.asyncio
async def test_silent_stream_is_reopened_on_the_same_call(isolated):
    registry, tokens, carrier = isolated
    registry.upsert("call-a", {"status": "in-progress", "webhook_token": "old"})
    bridge = await run_silent_bridge({"call_uuid": "call-a", "agent_id": "agent", "direction": "outbound",
                                      "webhook_token": "old", "media_stream_claimed": True})

    carrier.transfer_call.assert_awaited_once()
    call_uuid, = carrier.transfer_call.await_args.args
    url = carrier.transfer_call.await_args.kwargs["aleg_url"]
    assert call_uuid == "call-a"
    assert url.startswith("https://voice.example/api/vobiz/stream-reconnect?")
    new_meta = tokens.peek(parse_qs(urlsplit(url).query)["token"][0])
    assert new_meta["stream_attempt"] == 1 and new_meta["call_uuid"] == "call-a"
    assert "webhook_token" not in new_meta and "media_stream_claimed" not in new_meta
    bridge.hangup.assert_not_awaited()
    # The call stays live for the new socket.
    row = registry.get("call-a")
    assert not row.get("ended") and row["stream_state"] == "reconnecting"


@pytest.mark.asyncio
async def test_second_silent_stream_ends_the_call(isolated):
    registry, _, carrier = isolated
    registry.upsert("call-a", {"status": "in-progress"})
    bridge = await run_silent_bridge({"call_uuid": "call-a", "agent_id": "agent", "stream_attempt": 1})
    carrier.transfer_call.assert_not_awaited()
    bridge.hangup.assert_awaited_once_with("stream_never_started")
    assert registry.get("call-a")["exit_reason"] == "start_timeout"


@pytest.mark.asyncio
async def test_failed_reopen_ends_the_call(isolated):
    registry, _, carrier = isolated
    registry.upsert("call-a", {"status": "in-progress"})
    carrier.transfer_call.side_effect = client.VobizApiError("Vobiz API 404", status=404)
    bridge = await run_silent_bridge({"call_uuid": "call-a", "agent_id": "agent"})
    bridge.hangup.assert_awaited_once_with("stream_never_started")


@pytest.mark.asyncio
async def test_call_already_hung_up_is_not_reopened(isolated):
    registry, _, carrier = isolated
    registry.upsert("call-a", {"ended": True})
    bridge = await run_silent_bridge({"call_uuid": "call-a", "agent_id": "agent"})
    carrier.transfer_call.assert_not_awaited()
    bridge.hangup.assert_not_awaited()


def xml_request(query):
    return Request({"type": "http", "scheme": "http", "method": "POST", "server": ("internal", 8000),
                    "path": "/api/vobiz/stream-reconnect", "query_string": query.encode(), "headers": []})


@pytest.mark.asyncio
async def test_reconnect_xml_streams_only_for_a_reconnect_token_on_a_live_call(isolated, monkeypatch):
    registry, tokens, _ = isolated
    monkeypatch.setattr(routes, "ws_public_base", lambda: "wss://voice.example")
    monkeypatch.setattr(routes, "_verify_vobiz_request", AsyncMock())
    registry.upsert("call-a", {"status": "in-progress"})
    good = tokens.create(call_uuid="call-a", stream_attempt=1)
    body = (await routes.vobiz_stream_reconnect(xml_request(f"token={good}"))).body.decode()
    assert f"wss://voice.example/ws/vobiz-stream?token={good}&amp;call_uuid=call-a" in body
    assert "<Record" not in body

    original = tokens.create(call_uuid="call-a")
    body = (await routes.vobiz_stream_reconnect(xml_request(f"token={original}"))).body.decode()
    assert "<Stream" not in body and "<Hangup" in body

    registry.upsert("call-a", {"ended": True})
    body = (await routes.vobiz_stream_reconnect(xml_request(f"token={good}"))).body.decode()
    assert "<Stream" not in body


@pytest.mark.asyncio
async def test_reconnect_socket_gets_its_own_claim_once(isolated, monkeypatch):
    registry, tokens, _ = isolated
    claim_media = AsyncMock(return_value=False)
    from server.services.saas import call_admission
    monkeypatch.setattr(call_admission, "claim_media", claim_media)
    started = []

    class Bridge:
        ws_id = "isolated"

        def __init__(self, ws):
            self.ws = ws

        async def run(self, **kw):
            started.append(kw)

    monkeypatch.setattr(ws_route, "VobizPstnBridge", Bridge)
    await registry.atomic_check_and_set("call-a", "media_stream_claimed")
    meta = {"call_uuid": "call-a", "agent_id": "agent", "admission_key": "k", "admission_tenant_id": "00000000-0000-0000-0000-000000000001"}

    def socket(token):
        return SimpleNamespace(query_params={"token": token, "call_uuid": "call-a"}, accept=AsyncMock(), close=AsyncMock())

    reconnect = socket(tokens.create(**meta, stream_attempt=1))
    await ws_route.vobiz_stream_ws(reconnect)
    reconnect.accept.assert_awaited_once()
    claim_media.assert_not_awaited()
    # A second socket for the same attempt, or a fresh original token, is refused.
    for token in (tokens.create(**meta, stream_attempt=1), tokens.create(**meta)):
        refused = socket(token)
        await ws_route.vobiz_stream_ws(refused)
        refused.accept.assert_not_awaited()
    assert len(started) == 1
