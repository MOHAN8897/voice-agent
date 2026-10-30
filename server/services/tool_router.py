"""Tenant authorization and durable write claims for voice integration actions."""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from server.db.connection import get_session_factory
from server.db.models.entities import Agent, Tenant
from server.db.models.integration_models import AgentIntegration, TenantIntegration, ToolExecution
from server.services.nango_service import nango_service
from server.services.tool_schema_registry import (
    _normalize,
    default_action_timing,
    is_write_action,
    tool_definition,
    validate_tool_arguments,
)
from server.utils.logger import logger

TOOL_TIMEOUT_SECONDS = 8.0


class DialtactToolRouter:
    def __init__(self) -> None:
        self.nango = nango_service

    async def authorized(self, tenant_id: str, agent_id: str, tool_name: str, *, timing: str = "in_call") -> bool:
        definition = tool_definition(tool_name)
        factory = get_session_factory()
        if factory is None or definition is None:
            return False
        try:
            tenant_uuid, agent_uuid = uuid.UUID(tenant_id), uuid.UUID(agent_id)
            async with factory() as session:
                agent = (await session.execute(select(Agent).where(
                    Agent.agent_id == agent_uuid, Agent.tenant_id == tenant_uuid,
                    Agent.status == "active",
                ))).scalar_one_or_none()
                tenant = await session.get(Tenant, tenant_uuid)
                if agent is None or tenant is None or tenant.status != "active":
                    return False
                if definition[0] == "PLATFORM":
                    return timing == "in_call"
                integrations = (await session.execute(select(TenantIntegration).where(
                    TenantIntegration.tenant_id == tenant_uuid, TenantIntegration.status == "ACTIVE",
                ))).scalars().all()
                app = definition[0]
                if not any(_normalize(i.app_name) == app and (i.metadata_ or {}).get("gateway_verified") is True for i in integrations):
                    return False
                rules = (await session.execute(select(AgentIntegration).where(
                    AgentIntegration.tenant_id == tenant_uuid, AgentIntegration.agent_id == agent_uuid,
                ))).scalars().all()
                matching = [r for r in rules if _normalize(r.app_name) == app]
                if matching:
                    return any(r.enabled and r.timing_mode == timing and
                               (not r.action_whitelist or tool_name.upper() in {a.upper() for a in r.action_whitelist})
                               for r in matching)
                # Explicit agent setup is required for automatic after-call writes.
                return timing == "in_call" and default_action_timing(app) == "in_call"
        except Exception as exc:
            logger.warning("[TOOL_ROUTER] Authorization unavailable: %s", type(exc).__name__)
            return False

    async def route_and_execute(
        self, tenant_id: str | None, agent_id: str | None, call_id: str,
        tool_name: str, arguments: dict[str, Any], *, timing: str = "in_call",
    ) -> dict[str, Any]:
        if not tenant_id or not agent_id:
            return {"status": "error", "message": "Unauthorized: Missing tenant or agent context"}
        tool_name = tool_name.upper()
        error = validate_tool_arguments(tool_name, arguments)
        if error:
            return {"status": "error", "message": error}
        if not await self.authorized(tenant_id, agent_id, tool_name, timing=timing):
            return {"status": "error", "message": "This action is not enabled for this agent and workspace."}
        if tool_name in {"SAVE_ENQUIRY", "CONFIRM_ORDER"}:
            from server.call.enquiry import execute_platform_action

            try:
                return await asyncio.wait_for(execute_platform_action(
                    tool_name, call_id=call_id, tenant_id=tenant_id, agent_id=agent_id, arguments=arguments,
                ), timeout=TOOL_TIMEOUT_SECONDS)
            except Exception as exc:  # noqa: BLE001 - tool failures must return an unconfirmed result to the call.
                logger.warning("[TOOL_ROUTER] Platform action unconfirmed: %s", type(exc).__name__)
                return {"status": "unknown", "message": "Saving could not be confirmed. Check the existing request before retrying."}
        action_type = self._get_action_metadata(tool_name)["type"]
        execution_id = None
        if action_type == "write":
            if not call_id:
                return {"status": "error", "message": "A call context is required for this action."}
            if await self._has_uncertain_prior_write(tenant_id, call_id, tool_name):
                # A timed-out write may have reached the provider. Replaying it
                # with different arguments could create a second record, so the
                # result stays unknown until a human or a read reconciles it.
                return {
                    "status": "unknown",
                    "message": "An earlier attempt of this action has an unknown outcome. Do not retry it.",
                }
            claim = await self._record_execution_start(
                tenant_id, agent_id, call_id, tool_name, action_type,
                self._generate_idempotency_key(tenant_id, call_id, tool_name, arguments), arguments,
            )
            if claim is None:
                return {"status": "error", "message": "Action tracking is unavailable. No action was started."}
            if not claim["execute"]:
                return claim.get("result") or {"status": "unknown", "message": "This action was already started. Check its result before trying again."}
            execution_id = claim["execution_id"]
        try:
            result = await asyncio.wait_for(self.nango.execute_in_call_tool(
                tenant_id=tenant_id, action_name=tool_name, params=arguments,
                timeout_sec=TOOL_TIMEOUT_SECONDS,
            ), timeout=TOOL_TIMEOUT_SECONDS)
            if not isinstance(result, dict) or not result.get("status"):
                result = {"status": "unknown", "message": "The action result could not be verified."}
            if execution_id:
                status = str(result.get("status"))
                audit_status = "succeeded" if status in {"success", "succeeded", "confirmed", "created", "booked", "sent", "draft_created", "rescheduled", "cancelled", "subscribed", "accepted"} else (
                    "timed_out_pending" if status in {"unknown", "timeout"} else "failed"
                )
                await self._record_execution_complete(tenant_id, execution_id, audit_status, result=result)
            return result
        except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
            result = ({"status": "unknown", "message": "The result could not be confirmed. Check the existing action before trying again."}
                      if action_type == "write" else
                      {"status": "timeout", "message": "The lookup took too long. Nothing was changed; do not guess the answer, offer to follow up or try once more."})
            if execution_id:
                await asyncio.shield(self._record_execution_complete(
                    tenant_id, execution_id, "timed_out_pending", result=result, error="Outcome unknown after interruption",
                ))
            if isinstance(exc, asyncio.CancelledError):
                raise
            return result
        except Exception as exc:
            logger.warning("[TOOL_ROUTER] Execution interrupted: %s", type(exc).__name__)
            result = {"status": "unknown" if action_type == "write" else "error", "message": "The action result could not be confirmed."}
            if execution_id:
                await self._record_execution_complete(tenant_id, execution_id, "timed_out_pending", result=result)
            return result

    def _get_action_metadata(self, action_name: str) -> dict[str, str]:
        return {"type": "write" if is_write_action(action_name) else "read"}

    def _generate_idempotency_key(self, tenant_id: str, call_id: str, tool_name: str, args: dict[str, Any]) -> str:
        identity = args
        # Creating the same contact twice in one call remains the same action
        # even when optional name/company fields change. Corrections belong to
        # UPDATE, not another CREATE. Other actions retain full argument keys.
        if tool_name.upper().endswith("CREATE_CONTACT"):
            email = str(args.get("email") or "").strip().casefold()
            if not email and "@" in str(args.get("lastname") or ""):
                email = str(args["lastname"]).strip().casefold()
            phone = re.sub(r"[^\d+]", "", str(args.get("phone") or ""))
            if email:
                identity = {"email": email}
            elif phone:
                identity = {"phone": phone}
        elif tool_name.upper().endswith("CREATE_EVENT"):
            identity = {key: args.get(key) for key in ("start", "end")}
            identity["calendar_id"] = args.get("calendar_id") or "primary"
        digest = hashlib.sha256(json.dumps([tenant_id, call_id, tool_name, identity], sort_keys=True).encode()).hexdigest()
        return f"tool:{digest}"

    async def _has_uncertain_prior_write(
        self, tenant_id: str, call_id: str, action: str,
    ) -> bool:
        """True when this call already has an unresolved write for the action."""
        factory = get_session_factory()
        if factory is None:
            return False
        try:
            async with factory() as session:
                row = (await session.execute(
                    select(ToolExecution.id).where(
                        ToolExecution.tenant_id == uuid.UUID(tenant_id),
                        ToolExecution.call_id == call_id,
                        ToolExecution.action == action,
                        ToolExecution.status == "timed_out_pending",
                    ).limit(1)
                )).first()
                return row is not None
        except Exception as exc:
            # Fail closed: an unchecked prior write must not be replayed.
            logger.warning("[TOOL_ROUTER] Prior-write check unavailable: %s", type(exc).__name__)
            return True

    async def _record_execution_start(
        self, tenant_id: str, agent_id: str, call_id: str, action: str,
        action_type: str, idempotency_key: str, params: dict[str, Any],
    ) -> dict[str, Any] | None:
        factory = get_session_factory()
        if factory is None:
            return None
        execution_id = uuid.uuid4()
        try:
            async with factory() as session:
                session.add(ToolExecution(
                    id=execution_id, tenant_id=uuid.UUID(tenant_id), agent_id=uuid.UUID(agent_id),
                    call_id=call_id, action=action, action_type=action_type, idempotency_key=idempotency_key,
                    parameters=params, status="initiated", started_at=datetime.now(timezone.utc),
                ))
                await session.commit()
            return {"execute": True, "execution_id": str(execution_id)}
        except IntegrityError:
            # The unique tenant + key constraint is the claim across processes.
            try:
                async with factory() as session:
                    row = (await session.execute(select(ToolExecution).where(
                        ToolExecution.tenant_id == uuid.UUID(tenant_id), ToolExecution.idempotency_key == idempotency_key,
                    ))).scalar_one_or_none()
                    return {"execute": False, "result": row.result} if row else None
            except Exception as exc:
                logger.warning("[TOOL_ROUTER] Existing claim unavailable: %s", type(exc).__name__)
                return None
        except Exception as exc:
            logger.warning("[TOOL_ROUTER] Write claim unavailable: %s", type(exc).__name__)
            return None

    async def _record_execution_complete(
        self, tenant_id: str, execution_id: str, status: str,
        result: dict[str, Any] | None = None, external_ref: str | None = None, error: str | None = None,
    ) -> None:
        factory = get_session_factory()
        if factory is None:
            return
        try:
            async with factory() as session:
                await session.execute(update(ToolExecution).where(
                    ToolExecution.tenant_id == uuid.UUID(tenant_id), ToolExecution.id == uuid.UUID(execution_id),
                ).values(status=status, result=result, external_reference=external_ref,
                         error=error, completed_at=datetime.now(timezone.utc)))
                await session.commit()
        except Exception as exc:
            # The durable initiated claim remains, so an unknown result cannot
            # accidentally dispatch a second external write on the next attempt.
            logger.warning("[TOOL_ROUTER] Audit update unavailable: %s", type(exc).__name__)


tool_router = DialtactToolRouter()
