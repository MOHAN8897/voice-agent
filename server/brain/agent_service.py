"""
Agent CRUD service — Phase 2 workspace entity.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.entities import Agent, ConfigVersion, Tenant

_MEM_AGENTS: dict[str, dict[str, Any]] = {}
_DEFAULT_AGENT_ID: str | None = None
_MEM_BUILD_REQUESTS: dict[str, dict[str, Any]] = {}


class AgentBuildRequestConflict(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class AgentVoiceRevisionConflict(ValueError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "voice_revision_conflict",
        status_code: int = 409,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class AgentService:
    async def claim_build_request(
        self, *, request_id: str, fingerprint: str, tenant_id: str,
        name: str, language: str,
    ) -> dict[str, Any]:
        """One durable agent claim per workspace request, before generation starts."""
        aid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"agent-build:{tenant_id}:{uuid.UUID(request_id)}"))
        payload = {"fingerprint": fingerprint, "state": "building", "tenant_id": tenant_id}

        def existing_result(agent: dict[str, Any], saved: dict[str, Any]) -> dict[str, Any]:
            if saved.get("fingerprint") != fingerprint:
                raise AgentBuildRequestConflict("request_input_changed", "This creation request was already used with different inputs. Start a new request.")
            return {"agent": agent, **saved, "created": False}

        factory = get_session_factory()
        if factory is None:
            if aid in _MEM_AGENTS:
                agent = await self.get_agent(aid, tenant_id=tenant_id)
                return existing_result(agent, _MEM_BUILD_REQUESTS.get(aid) or {})
            if aid in _MEM_BUILD_REQUESTS:
                raise AgentBuildRequestConflict("creation_removed", "The agent for this creation request was removed. Start a new request.")
            agent = self._default_agent_dict(aid, name=name)
            agent.update(tenant_id=tenant_id, languages=[language], status="draft")
            _MEM_AGENTS[aid] = agent
            _MEM_BUILD_REQUESTS[aid] = payload
            return {"agent": dict(agent), **payload, "created": True}

        # A concurrent insert can win the primary-key claim while this request
        # was waiting. Re-read that committed claim instead of generating twice.
        for attempt in range(2):
            async with factory() as session:
                row = (await session.execute(select(Agent).where(
                    Agent.agent_id == uuid.UUID(aid), Agent.tenant_id == uuid.UUID(tenant_id),
                ).with_for_update())).scalar_one_or_none()
                if row is not None:
                    record = (await session.execute(select(ConfigVersion).join(
                        Agent, Agent.agent_id == uuid.UUID(aid),
                    ).where(
                        Agent.tenant_id == uuid.UUID(tenant_id),
                        ConfigVersion.resource_type == "agent_build_request", ConfigVersion.resource_id == aid,
                    ))).scalar_one_or_none()
                    return existing_result(self._row_to_dict(row), dict(record.payload or {}) if record else {})
                prior = (await session.execute(select(ConfigVersion).where(
                    ConfigVersion.resource_type == "agent_build_request", ConfigVersion.resource_id == aid,
                    ConfigVersion.payload["tenant_id"].as_string() == tenant_id,
                ))).scalar_one_or_none()
                if prior is not None:
                    raise AgentBuildRequestConflict("creation_removed", "The agent for this creation request was removed. Start a new request.")
                row = Agent(agent_id=uuid.UUID(aid), tenant_id=uuid.UUID(tenant_id), name=name, status="draft", languages=[language])
                session.add(row)
                session.add(ConfigVersion(resource_type="agent_build_request", resource_id=aid, version=1, payload=payload))
                try:
                    await session.commit()
                except IntegrityError as exc:
                    await session.rollback()
                    sqlstate = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
                    if attempt or sqlstate != "23505":
                        raise
                else:
                    return {"agent": self._row_to_dict(row), **payload, "created": True}
        raise AgentBuildRequestConflict("creation_in_progress", "This agent creation is already in progress.")

    async def finish_build_request(
        self, agent_id: str, *, tenant_id: str, response: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None, status_code: int = 502,
    ) -> dict[str, Any] | None:
        """Keep the request outcome beside its owned agent; never delete on retry."""
        import copy

        def outcome(agent: dict[str, Any], saved: dict[str, Any]) -> dict[str, Any] | None:
            if saved.get("state") == "completed":
                return copy.deepcopy(saved.get("response"))
            if response is not None:
                agent["status"] = "active"
                reply = {**copy.deepcopy(response), "agent": copy.deepcopy(agent)}
                saved.update(state="completed", response=reply)
                return reply
            saved.update(state="failed", error=copy.deepcopy(error), status_code=status_code)
            return None

        factory = get_session_factory()
        if factory is None:
            agent = await self.get_agent(agent_id, tenant_id=tenant_id)
            saved = _MEM_BUILD_REQUESTS.get(agent_id)
            if saved is None:
                raise KeyError(agent_id)
            return outcome(agent, saved)
        async with factory() as session:
            row = (await session.execute(select(Agent).where(
                Agent.agent_id == uuid.UUID(agent_id), Agent.tenant_id == uuid.UUID(tenant_id),
            ).with_for_update())).scalar_one()
            record = (await session.execute(select(ConfigVersion).join(
                Agent, Agent.agent_id == uuid.UUID(agent_id),
            ).where(
                Agent.tenant_id == uuid.UUID(tenant_id),
                ConfigVersion.resource_type == "agent_build_request", ConfigVersion.resource_id == agent_id,
            ))).scalar_one()
            saved = copy.deepcopy(record.payload or {})
            result = outcome(self._row_to_dict(row), saved)
            if response is not None:
                row.status = "active"
            record.payload = saved
            await session.commit()
            return result

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

    async def list_agents(self, tenant_id: str | None = None) -> list[dict[str, Any]]:
        factory = get_session_factory()
        if factory is None:
            if not _MEM_AGENTS:
                await self.ensure_default_agent()
            agents = [a for a in _MEM_AGENTS.values() if a.get("status") != "archived"]
            if tenant_id:
                agents = [a for a in agents if a.get("tenant_id") == tenant_id]
            return agents

        async with factory() as session:
            q = select(Agent).where(Agent.status != "archived")
            if tenant_id:
                q = q.where(Agent.tenant_id == uuid.UUID(tenant_id))
            result = await session.execute(q.order_by(Agent.created_at))
            return [self._row_to_dict(r) for r in result.scalars()]

    async def get_agent(self, agent_id: str, tenant_id: str | None = None) -> dict[str, Any]:
        factory = get_session_factory()
        if factory is None:
            if agent_id in _MEM_AGENTS:
                agent = _MEM_AGENTS[agent_id]
                if tenant_id and str(agent.get("tenant_id") or "") != tenant_id:
                    raise KeyError(agent_id)
                return agent
            for agent in _MEM_AGENTS.values():
                if agent.get("name") == agent_id and (
                    not tenant_id or str(agent.get("tenant_id") or "") == tenant_id
                ):
                    return agent
            if agent_id == "default" and not tenant_id:
                return await self.ensure_default_agent()
            raise KeyError(agent_id)

        try:
            agent_uuid = uuid.UUID(agent_id)
        except ValueError:
            async with factory() as session:
                query = select(Agent).where(Agent.name == agent_id)
                if tenant_id:
                    query = query.where(Agent.tenant_id == uuid.UUID(tenant_id))
                result = await session.execute(query)
                row = result.scalar_one_or_none()
                if not row:
                    if agent_id == "default" and not tenant_id:
                        return await self.ensure_default_agent()
                    raise KeyError(agent_id)
                return self._row_to_dict(row)

        async with factory() as session:
            result = await session.execute(select(Agent).where(Agent.agent_id == agent_uuid))
            row = result.scalar_one_or_none()
            if not row:
                raise KeyError(agent_id)
            if tenant_id and str(row.tenant_id) != tenant_id:
                raise KeyError(agent_id)
            return self._row_to_dict(row)

    async def create_agent(
        self,
        *,
        name: str,
        tenant_id: str | None = None,
        languages: list[str] | None = None,
        recording_disclosure_enabled: bool = False,
        recording_disclosure_text: str | None = None,
    ) -> dict[str, Any]:
        from server.prompts.agent_voice_rules import normalize_compile_language

        lang_list = [normalize_compile_language((languages or ["te-IN"])[0] if languages else "te-IN")]
        factory = get_session_factory()
        aid = str(uuid.uuid4())
        if factory is None:
            row = self._default_agent_dict(aid, name=name)
            if tenant_id:
                row["tenant_id"] = tenant_id
            row["languages"] = lang_list
            row["recording_disclosure_enabled"] = bool(recording_disclosure_enabled)
            row["recording_disclosure_text"] = recording_disclosure_text
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
                recording_disclosure_enabled=bool(recording_disclosure_enabled),
                recording_disclosure_text=recording_disclosure_text,
            )
            session.add(agent)
            await session.commit()
            return self._row_to_dict(agent)

    async def patch_agent(
        self,
        agent_id: str,
        patch: dict[str, Any],
        tenant_id: str | None = None,
        *,
        expected_voice_revision: int | None = None,
    ) -> dict[str, Any]:
        from server.prompts.agent_voice_rules import normalize_compile_language

        factory = get_session_factory()
        if "languages" in patch and patch["languages"] is not None:
            cleaned = [str(x).strip() for x in patch["languages"] if str(x).strip()]
            patch["languages"] = [normalize_compile_language(cleaned[0])] if cleaned else ["te-IN"]
        if factory is None:
            incoming_voice = patch.get("voice_settings")
            if expected_voice_revision is not None or (
                isinstance(incoming_voice, dict) and incoming_voice.get("stackSelectionVersion") == 1
            ):
                raise AgentVoiceRevisionConflict(
                    "Voice-stack settings require durable database storage.",
                    code="durable_store_unavailable",
                    status_code=503,
                )
            agent = await self.get_agent(agent_id, tenant_id=tenant_id)
            agent.update({k: v for k, v in patch.items() if v is not None})
            _MEM_AGENTS[agent_id] = agent
            return agent

        async with factory() as session:
            statement = select(Agent).where(Agent.agent_id == uuid.UUID(agent_id))
            if expected_voice_revision is not None:
                statement = statement.with_for_update()
            result = await session.execute(statement)
            row = result.scalar_one_or_none()
            if not row:
                raise KeyError(agent_id)
            if tenant_id and str(row.tenant_id) != tenant_id:
                raise KeyError(agent_id)
            current_voice = dict(row.voice_settings or {})
            try:
                current_revision = max(0, int(current_voice.get("_voice_revision") or 0))
            except (TypeError, ValueError):
                current_revision = 0
            incoming_voice = patch.get("voice_settings")
            effective_voice = dict(current_voice)
            if isinstance(incoming_voice, dict):
                if "tier" in incoming_voice or "_voice_revision" in incoming_voice or "voiceRevision" in incoming_voice:
                    raise AgentVoiceRevisionConflict(
                        "Voice tier and revision are server-owned fields.",
                        code="server_owned_voice_field",
                        status_code=422,
                    )
                effective_voice.update(incoming_voice)
            voice_selection_changed = isinstance(incoming_voice, dict) or "default_tier" in patch
            opted_in = effective_voice.get("stackSelectionVersion") == 1
            has_versioned_voice = opted_in or current_voice.get("stackSelectionVersion") == 1
            if has_versioned_voice and voice_selection_changed and expected_voice_revision is None:
                raise AgentVoiceRevisionConflict(
                    "expectedVoiceRevision is required when changing a composed voice selection.",
                    code="voice_revision_required",
                    status_code=428,
                )
            if expected_voice_revision is not None and expected_voice_revision != current_revision:
                raise AgentVoiceRevisionConflict(
                    "Voice settings changed in another session. Reload before saving.",
                    details={"currentRevision": current_revision},
                )
            if opted_in and voice_selection_changed:
                effective_tier = str(patch.get("default_tier") or row.default_tier or "medium")
                from server.services.saas.voice_stack_profiles import load_profile_records

                premium_profile = ((await load_profile_records(str(row.environment or "development"), ("premium",))).get("premium")
                    if effective_tier == "premium" else None)
                if effective_tier == "premium" and premium_profile is None:
                    composed_keys = ("engineId", "modelId", "voiceId", "profileRevision")
                    if isinstance(incoming_voice, dict) and any(key in incoming_voice for key in composed_keys):
                        raise AgentVoiceRevisionConflict(
                            "Flagship Live uses the existing voice configuration and does not accept composed voice settings.",
                            code="premium_composed_settings_forbidden",
                            status_code=409,
                        )
                    for key in composed_keys:
                        effective_voice.pop(key, None)
                else:
                    effective_voice.pop("realtimeVoice", None)
                    required = ("profileRevision", "engineId", "modelId", "voiceId")
                    if any(not str(effective_voice.get(key) or "").strip() for key in required):
                        raise AgentVoiceRevisionConflict(
                            "Select a current profile, engine, model, and voice before saving.",
                            code="voice_selection_incomplete",
                            status_code=422,
                        )
                language_values = patch.get("languages") if patch.get("languages") is not None else row.languages
                language = str((language_values or ["en-US"])[0])
                from server.services.saas.voice_stack_profiles import (
                    VoiceProfileError,
                    validate_agent_voice_selection_async,
                )

                try:
                    await validate_agent_voice_selection_async(
                        effective_tier,
                        effective_voice,
                        environment=str(row.environment or "development"),
                        language=language,
                    )
                except VoiceProfileError as exc:
                    raise AgentVoiceRevisionConflict(
                        str(exc), code=exc.code, status_code=exc.status_code
                    ) from exc
            for key in (
                "name",
                "status",
                "default_tier",
                "memory_schema",
                "active_compiled_brain_version",
                "recording_disclosure_enabled",
                "recording_disclosure_text",
            ):
                if key in patch and patch[key] is not None:
                    setattr(row, key, patch[key])
            if "languages" in patch and patch["languages"] is not None:
                row.languages = list(patch["languages"])
                flag_modified(row, "languages")
            if "voice_settings" in patch and patch["voice_settings"] is not None:
                updated_voice = dict(effective_voice)
                if expected_voice_revision is not None:
                    updated_voice["_voice_revision"] = current_revision + 1
                row.voice_settings = updated_voice
                flag_modified(row, "voice_settings")
            elif expected_voice_revision is not None and "default_tier" in patch:
                effective_voice["_voice_revision"] = current_revision + 1
                row.voice_settings = effective_voice
                flag_modified(row, "voice_settings")
            await session.commit()
            await session.refresh(row)
            return self._row_to_dict(row)

    async def delete_agent(self, agent_id: str, tenant_id: str | None = None) -> dict[str, Any]:
        from server.agent.instruction_store import instruction_store
        from server.services.runtime_settings import runtime_settings
        from server.services.session_persist import session_persist

        await self.get_agent(agent_id, tenant_id=tenant_id)
        archived = False
        released_numbers = 0
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
                if tenant_id and str(row.tenant_id) != tenant_id:
                    raise KeyError(agent_id)
                # Release the number before touching the agent row, in its own
                # transaction. On the archive path the agent row survives, so nothing
                # else would ever clear this — the number would keep its owner id and
                # the pool would keep refusing it as "(assigned elsewhere)" for an
                # agent the user can no longer see.
                released_numbers = await self._release_agent_numbers(session, agent_id)
                try:
                    await session.delete(row)
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    # The release was committed separately, so this rollback cannot
                    # undo it. Sharing one transaction here silently restored the
                    # orphaned assignment on every archived agent.
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
        return {
            "ok": True,
            "agent_id": agent_id,
            "archived": archived,
            "released_numbers": released_numbers,
        }

    @staticmethod
    async def _release_agent_numbers(session, agent_id: str) -> int:
        """Return every number this agent held to the unassigned pool.

        Commits on its own, deliberately. `delete_agent` falls back to archiving
        the agent when call history blocks the hard delete, and that fallback
        rolls the session back — which would otherwise discard this release along
        with the failed delete, leaving the number assigned to an agent the user
        can no longer see.

        Releases are not tenant-scoped: a phone number is already a per-tenant row
        keyed by its own agent_id, and scoping by tenant here would strand a
        cross-tenant row on a deleted agent.
        """
        from sqlalchemy import update

        from server.db.models.phase5_models import PhoneNumber

        result = await session.execute(
            update(PhoneNumber)
            .where(PhoneNumber.agent_id == uuid.UUID(agent_id))
            .values(agent_id=None)
        )
        released = int(result.rowcount or 0)
        await session.commit()
        return released

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
            "recording_disclosure_enabled": False,
            "recording_disclosure_text": None,
            "voice_settings": {},
        }

    @staticmethod
    def _row_to_dict(row: Agent) -> dict[str, Any]:
        raw_voice_settings = getattr(row, "voice_settings", None) or {}
        voice_settings = {
            key: value
            for key, value in raw_voice_settings.items()
            if key not in {"_voice_revision", "voiceRevision"}
        }
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
            "recording_disclosure_enabled": bool(getattr(row, "recording_disclosure_enabled", False)),
            "recording_disclosure_text": getattr(row, "recording_disclosure_text", None),
            "voice_settings": voice_settings,
            "voice_revision": int(raw_voice_settings.get("_voice_revision") or 0),
            "voiceRevision": int(raw_voice_settings.get("_voice_revision") or 0),
        }


agent_service = AgentService()
