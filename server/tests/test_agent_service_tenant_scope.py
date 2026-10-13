from __future__ import annotations

import pytest

import server.brain.agent_service as agent_service_module
from server.brain.agent_service import agent_service
from server.call.call_lifecycle_service import call_lifecycle_service


@pytest.mark.asyncio
async def test_in_memory_agent_lookup_enforces_tenant_for_id_and_name(monkeypatch):
    monkeypatch.setattr(agent_service_module, "get_session_factory", lambda: None)
    monkeypatch.setattr(
        agent_service_module,
        "_MEM_AGENTS",
        {
            "agent-a": {
                "agent_id": "agent-a",
                "tenant_id": "tenant-a",
                "name": "Teja",
                "status": "active",
            }
        },
    )

    with pytest.raises(KeyError):
        await agent_service.get_agent("agent-a", tenant_id="tenant-b")
    with pytest.raises(KeyError):
        await agent_service.get_agent("Teja", tenant_id="tenant-b")
    with pytest.raises(KeyError):
        await agent_service.get_agent("default", tenant_id="tenant-b")

    assert (await agent_service.get_agent("Teja", tenant_id="tenant-a"))["agent_id"] == "agent-a"


@pytest.mark.asyncio
async def test_lifecycle_resolves_requested_agent_inside_authenticated_tenant(monkeypatch):
    from unittest.mock import AsyncMock

    lookup = AsyncMock(return_value={"agent_id": "agent-a", "tenant_id": "tenant-a"})
    monkeypatch.setattr(agent_service, "get_agent", lookup)

    agent = await call_lifecycle_service._resolve_agent("agent-a", tenant_id="tenant-a")

    assert agent["tenant_id"] == "tenant-a"
    lookup.assert_awaited_once_with("agent-a", tenant_id="tenant-a")
