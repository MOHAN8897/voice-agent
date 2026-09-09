"""
Agent CRUD service — Phase 2 workspace entity.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from sqlalchemy.orm.attributes import flag_modified

from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.entities import Agent, Tenant

_MEM_AGENTS: dict[str, dict[str, Any]] = {}
_DEFAULT_AGENT_ID: str | None = None


class AgentService:
    async def ensure_default_agent(self) -> dict[str, Any]:
        factory = get_session_factory()
        if factory is None:
            global _DEFAULT_AGENT_ID
            if _DEFAULT_AGENT_ID and _DEFAULT_AGENT_ID in _MEM_AGENTS:
                return _MEM_AGENTS[_DEFAULT_AGENT_ID]
            aid = str(uuid.uuid4())
            _DEFAULT_AGENT_ID = aid
            _MEM_AGENTS[aid] = self._default_agent_dict(aid)
            return _MEM_AGENTS[aid]

        async with factory() as session:
            result = await session.execute(select(Agent).where(Agent.name == "default"))
            agent = result.scalar_one_or_none()
            if agent:
                return self._row_to_dict(agent)
            settings = get_settings()
            default_tid = uuid.UUID(settings.default_tenant_id)
            tenant = await session.get(Tenant, default_tid)
            if tenant is None:
                tenant_result = await session.execute(select(Tenant).where(Tenant.name == "default"))
                tenant = tenant_result.scalar_one_or_none()
            if tenant is None:
                tenant = Tenant(tenant_id=default_tid, name="default")
                session.add(tenant)
                await session.flush()
            agent = Agent(tenant_id=tenant.tenant_id, name="default", status="active")
            session.add(agent)
            await session.commit()
            await session.refresh(agent)
            return self._row_to_dict(agent)

    async def list_agents(self) -> list[dict[str, Any]]:
        factory = get_session_factory()
        if factory is None:
            if not _MEM_AGENTS:
                await self.ensure_default_agent()
            return [a for a in _MEM_AGENTS.values() if a.get("status") != "archived"]

        async with factory() as session:
            result = await session.execute(
                select(Agent).where(Agent.status != "archived").order_by(Agent.created_at)
            )
            return [self._row_to_dict(r) for r in result.scalars()]

    async def get_agent(self, agent_id: str) -> dict[str, Any]:
        factory = get_session_factory()
        if factory is None:
            if agent_id in _MEM_AGENTS:
                return _MEM_AGENTS[agent_id]
            for agent in _MEM_AGENTS.values():
                if agent.get("name") == agent_id:
                    return agent
            if agent_id == "default":
                return await self.ensure_default_agent()
            raise KeyError(agent_id)

        try:
            agent_uuid = uuid.UUID(agent_id)
        except ValueError:
            async with factory() as session:
                result = await session.execute(select(Agent).where(Agent.name == agent_id))
                row = result.scalar_one_or_none()
                if not row:
                    if agent_id == "default":
                        return await self.ensure_default_agent()
                    raise KeyError(agent_id)
                return self._row_to_dict(row)

        async with factory() as session:
            result = await session.execute(select(Agent).where(Agent.agent_id == agent_uuid))
            row = result.scalar_one_or_none()
            if not row:
                raise KeyError(agent_id)
            return self._row_to_dict(row)

    async def create_agent(
        self,
        *,
        name: str,
        tenant_id: str | None = None,
        languages: list[str] | None = None,
    ) -> dict[str, Any]:
        from server.prompts.agent_voice_rules import normalize_compile_language

        lang_list = [normalize_compile_language((languages or ["te-IN"])[0] if languages else "te-IN")]
        factory = get_session_factory()
        aid = str(uuid.uuid4())
        if factory is None:
            row = self._default_agent_dict(aid, name=name)
            row["languages"] = lang_list
            _MEM_AGENTS[aid] = row
            return row

        async with factory() as session:
            tid = uuid.UUID(tenant_id) if tenant_id else (await self.ensure_default_agent())["tenant_id"]
            if isinstance(tid, str):
                tid = uuid.UUID(tid)
            agent = Agent(
                agent_id=uuid.UUID(aid),
                tenant_id=tid,
                name=name,
                status="active",
                languages=lang_list,
            )
            session.add(agent)
            await session.commit()
            return self._row_to_dict(agent)

    async def patch_agent(self, agent_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        from server.prompts.agent_voice_rules import normalize_compile_language

        factory = get_session_factory()
        if "languages" in patch and patch["languages"] is not None:
            cleaned = [str(x).strip() for x in patch["languages"] if str(x).strip()]
            patch["languages"] = [normalize_compile_language(cleaned[0])] if cleaned else ["te-IN"]
        if factory is None:
            agent = await self.get_agent(agent_id)
            agent.update({k: v for k, v in patch.items() if v is not None})
            _MEM_AGENTS[agent_id] = agent
            return agent

        async with factory() as session:
            result = await session.execute(select(Agent).where(Agent.agent_id == uuid.UUID(agent_id)))
            row = result.scalar_one_or_none()
            if not row:
                raise KeyError(agent_id)
            for key in ("name", "status", "default_tier", "memory_schema", "active_compiled_brain_version"):
                if key in patch and patch[key] is not None:
                    setattr(row, key, patch[key])
            if "languages" in patch and patch["languages"] is not None:
                row.languages = list(patch["languages"])
                flag_modified(row, "languages")
            await session.commit()
            await session.refresh(row)
            return self._row_to_dict(row)

    async def delete_agent(self, agent_id: str) -> dict[str, Any]:
        from server.agent.instruction_store import instruction_store
        from server.services.runtime_settings import runtime_settings
        from server.services.session_persist import session_persist

        await self.get_agent(agent_id)
        archived = False
        factory = get_session_factory()
        if factory is None:
            _MEM_AGENTS.pop(agent_id, None)
        else:
            from sqlalchemy.exc import IntegrityError

            async with factory() as session:
                result = await session.execute(select(Agent).where(Agent.agent_id == uuid.UUID(agent_id)))
                row = result.scalar_one_or_none()
                if not row:
                    raise KeyError(agent_id)
                try:
                    await session.delete(row)
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    row = await session.get(Agent, uuid.UUID(agent_id))
                    if row is None:
                        raise KeyError(agent_id)
                    row.status = "archived"
                    await session.commit()
                    archived = True

        session_id = f"test-studio:{agent_id}"
        instruction_store.clear(session_id)
        runtime_settings.clear(session_id)
        session_persist.delete_ui(session_id)
        return {"ok": True, "agent_id": agent_id, "archived": archived}

    async def resolve_default_agent_id(self) -> str:
        agent = await self.ensure_default_agent()
        return agent["agent_id"]

    @staticmethod
    def _default_agent_dict(agent_id: str, *, name: str = "default") -> dict[str, Any]:
        settings = get_settings()
        return {
            "agent_id": agent_id,
            "tenant_id": settings.default_tenant_id,
            "name": name,
            "status": "active",
            "active_compiled_brain_version": None,
            "default_tier": "medium",
            "languages": ["te-IN"],
            "memory_schema": "compact_v1",
            "environment": "development",
        }

    @staticmethod
    def _row_to_dict(row: Agent) -> dict[str, Any]:
        return {
            "agent_id": str(row.agent_id),
            "tenant_id": str(row.tenant_id),
            "name": row.name,
            "status": row.status,
            "active_compiled_brain_version": row.active_compiled_brain_version,
            "default_tier": row.default_tier,
            "languages": list(row.languages or ["te-IN"]),
            "memory_schema": row.memory_schema,
            "environment": getattr(row, "environment", None) or "development",
        }


agent_service = AgentService()
