"""Admin team API for the Roles & access page.

Every management endpoint is guarded server-side by `dev.admin.admins`, which only
the super-admin role holds. The UI hides controls for other roles, but the 403
here is what actually stops them. The roles catalogue is readable by any signed-in
admin so everyone can see what their own role allows.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from server.auth.admin_roles import describe_roles, permissions_for_role, ROLE_LABELS
from server.auth.dependencies import require_dev_session, require_permission
from server.auth.rbac import PERMISSION_MANAGE_ADMINS, role_has_permission
from server.auth.session import SessionData
from server.services.saas import admin_accounts
from server.services.saas.admin_accounts import Actor, AdminAccountError
from server.utils.rate_limiter import RateLimiter

router = APIRouter()
_link_limiter = RateLimiter(max_requests=20, window_s=300)


def _fail(exc: AdminAccountError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"error": {"code": exc.code, "message": exc.message}})


async def _run(fn: Callable[[], Awaitable[dict[str, Any]]]) -> dict[str, Any]:
    try:
        return await fn()
    except AdminAccountError as exc:
        raise _fail(exc)


def _manager(session: SessionData) -> Actor:
    require_permission(session, PERMISSION_MANAGE_ADMINS)
    return Actor.from_session(session)


class ReasonBody(BaseModel):
    reason: str = Field("", max_length=500)


class ConfirmBody(ReasonBody):
    confirm: str = Field("", max_length=64)


class LinkBody(ReasonBody):
    confirm: str = Field("", max_length=64)
    portalOrigin: str | None = Field(None, max_length=200)


class InviteBody(BaseModel):
    email: str = Field(..., max_length=320)
    fullName: str | None = Field(None, max_length=255)
    username: str | None = Field(None, max_length=64)
    role: str = Field(..., max_length=40)
    reason: str = Field("", max_length=500)
    portalOrigin: str | None = Field(None, max_length=200)


class RoleBody(ConfirmBody):
    role: str = Field(..., max_length=40)


class TokenBody(BaseModel):
    token: str = Field(..., min_length=10, max_length=200)


class AcceptBody(TokenBody):
    password: str = Field(..., min_length=1, max_length=200)


@router.get("/api/dev/admin/team/roles")
async def team_roles(session: SessionData = Depends(require_dev_session)) -> dict[str, Any]:
    """Roles and permissions in plain language, plus what this session may do."""
    catalogue = describe_roles()
    return {
        **catalogue,
        "me": {
            "subject": session.subject,
            "role": session.role,
            "roleLabel": ROLE_LABELS.get(session.role, session.role),
            "builtin": session.account_ref is None,
            "permissions": permissions_for_role(session.role),
            "canManageAdmins": role_has_permission(session.role, PERMISSION_MANAGE_ADMINS),
        },
    }


@router.get("/api/dev/admin/team")
async def team_list(session: SessionData = Depends(require_dev_session)) -> dict[str, Any]:
    actor = _manager(session)
    store = await admin_accounts.store_status()
    admins: list[dict[str, Any]] = []
    if store["ready"]:
        try:
            admins = await admin_accounts.list_accounts(actor)
        except AdminAccountError as exc:
            raise _fail(exc)
    builtin = admin_accounts.builtin_username()
    return {
        "store": store,
        "admins": admins,
        "builtin": {
            "configured": bool(builtin),
            "username": builtin,
            "role": "super_admin",
            "isSelf": session.account_ref is None and bool(builtin) and builtin.casefold() == session.subject.casefold(),
        },
        "consoleAdmins": await admin_accounts.console_platform_admins(),
        "policy": {
            "inviteTtlHours": int(admin_accounts.INVITE_TTL.total_seconds() // 3600),
            "resetTtlHours": int(admin_accounts.RESET_TTL.total_seconds() // 3600),
            "minPasswordLength": admin_accounts.MIN_PASSWORD_LENGTH,
            "minReasonLength": admin_accounts.MIN_REASON_LENGTH,
            "mfaSupported": False,
        },
    }


@router.get("/api/dev/admin/team/activity")
async def team_activity(
    limit: int = Query(30, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: SessionData = Depends(require_dev_session),
) -> dict[str, Any]:
    _manager(session)
    from server.services.saas.activity_log import list_events

    return await list_events(resource_type=admin_accounts.RESOURCE_TYPE, limit=limit, offset=offset)


@router.post("/api/dev/admin/team/invite")
async def team_invite(body: InviteBody, request: Request, session: SessionData = Depends(require_dev_session)):
    actor = _manager(session)
    return await _run(
        lambda: admin_accounts.invite(
            actor,
            email=body.email,
            full_name=body.fullName,
            username=body.username,
            role=body.role,
            reason=body.reason,
            portal_origin=body.portalOrigin,
            request=request,
        )
    )


@router.post("/api/dev/admin/team/{account_id}/resend-invite")
async def team_resend(account_id: str, body: LinkBody, request: Request, session: SessionData = Depends(require_dev_session)):
    actor = _manager(session)
    return await _run(
        lambda: admin_accounts.resend_invite(
            actor, account_id, reason=body.reason, portal_origin=body.portalOrigin, request=request
        )
    )


@router.post("/api/dev/admin/team/{account_id}/role")
async def team_role(account_id: str, body: RoleBody, request: Request, session: SessionData = Depends(require_dev_session)):
    actor = _manager(session)
    return await _run(
        lambda: admin_accounts.change_role(
            actor, account_id, role=body.role, reason=body.reason, confirm=body.confirm, request=request
        )
    )


@router.post("/api/dev/admin/team/{account_id}/suspend")
async def team_suspend(account_id: str, body: ConfirmBody, request: Request, session: SessionData = Depends(require_dev_session)):
    actor = _manager(session)
    return await _run(
        lambda: admin_accounts.suspend(actor, account_id, reason=body.reason, confirm=body.confirm, request=request)
    )


@router.post("/api/dev/admin/team/{account_id}/reactivate")
async def team_reactivate(account_id: str, body: ReasonBody, request: Request, session: SessionData = Depends(require_dev_session)):
    actor = _manager(session)
    return await _run(lambda: admin_accounts.reactivate(actor, account_id, reason=body.reason, request=request))


@router.post("/api/dev/admin/team/{account_id}/remove")
async def team_remove(account_id: str, body: ConfirmBody, request: Request, session: SessionData = Depends(require_dev_session)):
    actor = _manager(session)
    return await _run(
        lambda: admin_accounts.remove(actor, account_id, reason=body.reason, confirm=body.confirm, request=request)
    )


@router.post("/api/dev/admin/team/{account_id}/sign-out")
async def team_sign_out(account_id: str, body: ReasonBody, request: Request, session: SessionData = Depends(require_dev_session)):
    actor = _manager(session)
    return await _run(
        lambda: admin_accounts.sign_out_everywhere(actor, account_id, reason=body.reason, request=request)
    )


@router.post("/api/dev/admin/team/{account_id}/reset-password")
async def team_reset_password(account_id: str, body: LinkBody, request: Request, session: SessionData = Depends(require_dev_session)):
    actor = _manager(session)
    return await _run(
        lambda: admin_accounts.reset_password(
            actor,
            account_id,
            reason=body.reason,
            confirm=body.confirm,
            portal_origin=body.portalOrigin,
            request=request,
        )
    )


# --------------------------------------------------------------------------- public link endpoints


def _limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    allowed, retry = _link_limiter.allow(f"admin-link:{ip}")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={"error": {"code": "rate_limit", "message": "Too many attempts. Try again shortly.", "retry_after": retry}},
        )


@router.post("/api/dev/admin-invite/inspect")
async def invite_inspect(body: TokenBody, request: Request) -> dict[str, Any]:
    """What a one-time invite/reset link is for. No session: the token is the credential."""
    _limit(request)
    return await _run(lambda: admin_accounts.inspect_link(body.token))


@router.post("/api/dev/admin-invite/accept")
async def invite_accept(body: AcceptBody, request: Request) -> dict[str, Any]:
    _limit(request)
    return await _run(lambda: admin_accounts.accept_link(body.token, body.password, request=request))
