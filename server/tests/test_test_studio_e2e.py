"""Test studio E2E — call start/end and agent resolution."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_agent_get_by_name_default():
    import server.app as app_mod

    transport = ASGITransport(app=app_mod.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post("/api/dev/login", json={"username": "dev", "password": "devpass"})
        assert login.status_code == 200

        r = await client.get("/api/agents/default")
        assert r.status_code == 200
        body = r.json()
        assert body["agent"]["name"] == "default"
        assert body["agent"]["agent_id"]


@pytest.mark.asyncio
async def test_test_studio_call_lifecycle():
    import server.app as app_mod

    transport = ASGITransport(app=app_mod.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        agents = await client.get("/api/agents")
        assert agents.status_code == 200
        agent_list = agents.json().get("agents") or []
        assert isinstance(agent_list, list)
        assert len(agent_list) > 0
        agent_id = agent_list[0]["agent_id"]

        start = await client.post(
            "/api/call/start",
            json={"agentId": agent_id, "channel": "browser", "direction": "inbound", "tier": "medium"},
        )
        assert start.status_code == 200
        call_id = start.json()["call_id"]

        end = await client.post("/api/call/end", json={"callId": call_id, "reason": "user_stop"})
        assert end.status_code == 202

        fin = await client.get(f"/api/call/{call_id}/finalization")
        assert fin.status_code == 200
        assert fin.json().get("call_id") == call_id


@pytest.mark.asyncio
async def test_catalog_voice_presets_is_array():
    import server.app as app_mod

    transport = ASGITransport(app=app_mod.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/settings/catalog")
        assert r.status_code == 200
        presets = r.json().get("tts", {}).get("voicePresets")
        assert isinstance(presets, list)
        assert len(presets) > 0
        assert "id" in presets[0]
