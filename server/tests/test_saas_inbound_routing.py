"""Tests for SaaS Inbound PSTN routing and telephony profile policies."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from server.db.models.entities import Agent, Tenant
from server.db.models.phase5_models import PhoneNumber
from server.services.saas.inbound_routing import resolve_inbound_route


@pytest.mark.asyncio
async def test_resolve_inbound_route_active_agent():
    tid = uuid.uuid4()
    aid = uuid.uuid4()
    e164 = "+919876543210"

    pn = PhoneNumber(
        id=uuid.uuid4(),
        tenant_id=tid,
        agent_id=aid,
        e164=e164,
        inbound_enabled=True,
        outbound_enabled=True,
        status="active",
        released_at=None,
    )
    tenant = Tenant(
        tenant_id=tid,
        name="Test Org",
        status="active",
        deleted_at=None,
    )
    agent = Agent(
        agent_id=aid,
        tenant_id=tid,
        name="Priya",
        status="active",
        default_tier="medium",
        languages=["te-IN"],
    )

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.first.return_value = (pn, tenant)
    mock_session.execute.return_value = mock_result
    mock_session.get.return_value = agent

    class MockFactory:
        def __call__(self):
            return self
        async def __aenter__(self):
            return mock_session
        async def __aexit__(self, *args):
            pass

    with patch("server.services.saas.inbound_routing.get_session_factory", return_value=MockFactory()):
        route = await resolve_inbound_route(e164)
        assert route is not None
        assert route.tenant_id == tid
        assert route.agent_id == aid
        assert route.tier == "medium"


@pytest.mark.asyncio
async def test_resolve_inbound_route_rejects_paused_agent():
    tid = uuid.uuid4()
    aid = uuid.uuid4()
    e164 = "+919876543210"

    pn = PhoneNumber(
        id=uuid.uuid4(),
        tenant_id=tid,
        agent_id=aid,
        e164=e164,
        inbound_enabled=True,
        outbound_enabled=True,
        status="active",
        released_at=None,
    )
    tenant = Tenant(
        tenant_id=tid,
        name="Test Org",
        status="active",
        deleted_at=None,
    )
    paused_agent = Agent(
        agent_id=aid,
        tenant_id=tid,
        name="Priya",
        status="paused",
        default_tier="medium",
        languages=["te-IN"],
    )

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.first.return_value = (pn, tenant)
    mock_session.execute.return_value = mock_result
    mock_session.get.return_value = paused_agent

    class MockFactory:
        def __call__(self):
            return self
        async def __aenter__(self):
            return mock_session
        async def __aexit__(self, *args):
            pass

    with patch("server.services.saas.inbound_routing.get_session_factory", return_value=MockFactory()):
        route = await resolve_inbound_route(e164)
        assert route is None
