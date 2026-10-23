"""Explicit access boundary for session instruction editing and generation."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Header, HTTPException, Request

from server.auth.dependencies import require_app_session, require_dev_session
from server.auth.rbac import require_role_permission
from server.auth.session import cookie_names, parse_session_token
from server.auth.subscriber_dependencies import require_subscriber_jwt
from server.config.env import get_settings
from server.services.saas.tenant_guard import load_agent_for_tenant, subscriber_workspace_tenant_id


@dataclass(frozen=True)
class InstructionsAccess:
    tenant_id: uuid.UUID
    role: str
    developer: bool = False


async def require_instructions_access(
    request: Request,
    authorization: str | None = Header(None),
    x_csrf_token: str | None = Header(None, alias="X-CSRF-Token"),
) -> InstructionsAccess:
    """Never inherit the anonymous auth-off development stub."""
    if authorization:
        principal = await require_subscriber_jwt(request, authorization)
        return InstructionsAccess(subscriber_workspace_tenant_id(principal), principal.role)
    names = cookie_names()
    if parse_session_token(request.cookies.get(names["dev"], ""), "dev"):
        session = await require_dev_session(request, x_csrf_token)
        require_role_permission(session.role, "dev.platform_brain")
        return InstructionsAccess(
            uuid.UUID(session.tenant_id or get_settings().default_tenant_id), session.role, True
        )
    if parse_session_token(request.cookies.get(names["app"], ""), "app"):
        session = await require_app_session(request, x_csrf_token)
        return InstructionsAccess(uuid.UUID(session.tenant_id or get_settings().default_tenant_id), session.role)
    raise HTTPException(status_code=401, detail={"error": {"code": "auth_error", "message": "Sign in to manage agent instructions"}})


async def authorize_instruction_session(
    session_id: str, access: InstructionsAccess, *, write: bool = False
) -> None:
    if write:
        require_role_permission(access.role, "dev.platform_brain" if access.developer else "app.brain.write")
    from server.services.saved_instruction_store import agent_id_from_session

    agent_id = agent_id_from_session(session_id)
    if agent_id is None:
        # Legacy scratch sessions are a privileged developer workspace, never a
        # tenant addressable namespace. Subscriber/app access always names an agent.
        if access.developer and not session_id.startswith("test-studio:"):
            return
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent session not found"}})
    if access.developer:
        from server.brain.agent_service import agent_service

        try:
            await agent_service.get_agent(str(agent_id), tenant_id=str(access.tenant_id))
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent session not found"}}) from exc
    else:
        await load_agent_for_tenant(str(agent_id), access.tenant_id)
