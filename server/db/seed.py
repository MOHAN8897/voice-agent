"""Seed default tenant + agent — uses DEFAULT_TENANT_ID from env when set."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.entities import Agent, Tenant
from server.db.tier_store import load_tier_cache, sync_tier_assignments_from_env


async def ensure_default_tenant() -> str | None:
    """Returns default agent_id when available."""
    settings = get_settings()
    factory = get_session_factory()
    if factory is None:
        from server.brain.agent_service import agent_service

        agent = await agent_service.ensure_default_agent()
        return agent["agent_id"]

    agent_id: str | None = None
    default_tid = uuid.UUID(settings.default_tenant_id)

    async with factory() as session:
        tenant = await session.get(Tenant, default_tid)
        if tenant is None:
            result = await session.execute(select(Tenant).where(Tenant.name == "default"))
            tenant = result.scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(tenant_id=default_tid, name="default")
            session.add(tenant)
            await session.flush()
            session.add(Agent(tenant_id=tenant.tenant_id, name="default", status="active"))
            await session.flush()
        agent_row = await session.execute(
            select(Agent).where(Agent.tenant_id == tenant.tenant_id, Agent.name == "default")
        )
        agent = agent_row.scalar_one_or_none()
        if agent is None:
            session.add(Agent(tenant_id=tenant.tenant_id, name="default", status="active"))
            await session.flush()
            agent_row = await session.execute(
                select(Agent).where(Agent.tenant_id == tenant.tenant_id, Agent.name == "default")
            )
            agent = agent_row.scalar_one()
        agent_id = str(agent.agent_id)
        await session.commit()

    try:
        await sync_tier_assignments_from_env(settings.app_environment)
        await load_tier_cache()
    except Exception:
        pass
    return agent_id
