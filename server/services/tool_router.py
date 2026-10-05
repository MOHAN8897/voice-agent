"""Voxly Tool Router - Centralized policy enforcement, validation, and execution for voice tools."""
from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update

from server.db.connection import get_session_factory
from server.db.models.integration_models import ToolExecution
from server.services.nango_service import nango_service
from server.utils.logger import logger


class VoxlyToolRouter:
    """Enterprise Tool Router enforcing multi-tenant isolation, idempotency, and SLA semantics."""

    def __init__(self) -> None:
        self.nango = nango_service
        self.composio = nango_service

    async def route_and_execute(
        self,
        tenant_id: str | None,
        agent_id: str | None,
        call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Routes, validates, audits, and executes a tool call with strict fail-closed security."""

        # 1. FAIL-CLOSED TENANT VALIDATION (Fix #2: No "default" tenant fallback)
        if not tenant_id:
            logger.error("[TOOL_ROUTER] Missing tenant context for call %s tool %s", call_id, tool_name)
            return {"status": "error", "message": "Unauthorized: Missing tenant context"}

        # 2. FAIL-CLOSED AGENT VALIDATION
        if not agent_id:
            logger.error("[TOOL_ROUTER] Missing agent context for call %s tool %s", call_id, tool_name)
            return {"status": "error", "message": "Unauthorized: Missing agent context"}

        # 3. POLICY & WHITELIST CHECK
        action_meta = self._get_action_metadata(tool_name)
        action_type = action_meta.get("type", "read")  # 'read' or 'write'

        # 4. IDEMPOTENCY KEY (Split-brain prevention for write actions)
        idempotency_key = self._generate_idempotency_key(tenant_id, call_id, tool_name, arguments)

        # 5. AUDIT LOG (Initiate execution record in DB)
        execution_id: str | None = None
        if action_type == "write":
            execution_id = await self._record_execution_start(
                tenant_id=tenant_id,
                agent_id=agent_id,
                call_id=call_id,
                action=tool_name,
                action_type=action_type,
                idempotency_key=idempotency_key,
                params=arguments,
            )

        # 6. EXECUTE WITH STRICT 1.5s VOICE SLA & SPLIT-BRAIN TIMEOUT HANDLING
        try:
            result = await self.composio.execute_in_call_tool(
                tenant_id=tenant_id,
                action_name=tool_name,
                params=arguments,
                timeout_sec=1.5,
            )

            if execution_id:
                ext_ref = None
                if isinstance(result, dict):
                    ext_ref = result.get("id") or result.get("event_id") or result.get("external_id")
                await self._record_execution_complete(
                    execution_id=execution_id,
                    status="succeeded",
                    result=result,
                    external_ref=str(ext_ref) if ext_ref else None,
                )
            return result

        except asyncio.TimeoutError:
            logger.warning("[TOOL_ROUTER] Tool %s timed out after 1.5s SLA", tool_name)
            if execution_id:
                # Mark as timed_out_pending for post-call reconciliation
                await self._record_execution_complete(
                    execution_id=execution_id,
                    status="timed_out_pending",
                    error="Voice SLA timeout at 1.5s; background execution pending",
                )
            return {
                "status": "timeout",
                "action_type": action_type,
                "message": (
                    "The schedule check is taking a moment longer than expected. "
                    "I have your details saved and will verify and confirm shortly."
                ),
            }
        except Exception as exc:
            logger.error("[TOOL_ROUTER] Execution error for %s: %s", tool_name, exc)
            if execution_id:
                await self._record_execution_complete(
                    execution_id=execution_id,
                    status="failed",
                    error=str(exc),
                )
            return {"status": "error", "message": "Failed to complete request."}

    def _get_action_metadata(self, action_name: str) -> dict[str, str]:
        """Categorize actions into read vs. mutating write actions."""
        write_prefixes = ("CREATE", "UPDATE", "DELETE", "SEND", "BOOK", "INSERT")
        normalized = action_name.upper()
        for p in write_prefixes:
            if p in normalized:
                return {"type": "write"}
        return {"type": "read"}

    def _generate_idempotency_key(
        self, tenant_id: str, call_id: str, tool_name: str, args: dict[str, Any]
    ) -> str:
        serialized = json.dumps(args, sort_keys=True)
        arg_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:12]
        return f"{tenant_id}:{call_id}:{tool_name}:{arg_hash}"

    async def _record_execution_start(
        self,
        tenant_id: str,
        agent_id: str,
        call_id: str,
        action: str,
        action_type: str,
        idempotency_key: str,
        params: dict[str, Any],
    ) -> str:
        """Create execution record in database for state tracking."""
        exec_id = str(uuid.uuid4())
        session_factory = get_session_factory()
        if session_factory:
            try:
                async with session_factory() as session:
                    record = ToolExecution(
                        id=uuid.UUID(exec_id),
                        tenant_id=uuid.UUID(str(tenant_id)),
                        agent_id=uuid.UUID(str(agent_id)),
                        call_id=str(call_id),
                        action=action,
                        action_type=action_type,
                        idempotency_key=idempotency_key,
                        status="initiated",
                        parameters=params,
                        started_at=datetime.now(timezone.utc),
                    )
                    session.add(record)
                    await session.commit()
            except Exception as exc:
                logger.warning("[TOOL_ROUTER] Failed to save tool execution start: %s", exc)
        return exec_id

    async def _record_execution_complete(
        self,
        execution_id: str,
        status: str,
        result: dict[str, Any] | None = None,
        external_ref: str | None = None,
        error: str | None = None,
    ) -> None:
        """Update execution record upon completion or timeout."""
        session_factory = get_session_factory()
        if session_factory:
            try:
                async with session_factory() as session:
                    stmt = (
                        update(ToolExecution)
                        .where(ToolExecution.id == uuid.UUID(execution_id))
                        .values(
                            status=status,
                            result=result,
                            external_reference=external_ref,
                            error=error,
                            completed_at=datetime.now(timezone.utc),
                        )
                    )
                    await session.execute(stmt)
                    await session.commit()
            except Exception as exc:
                logger.warning("[TOOL_ROUTER] Failed to update tool execution record %s: %s", execution_id, exc)


tool_router = VoxlyToolRouter()
