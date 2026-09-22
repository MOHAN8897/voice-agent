"""SaaS subscriber auth — JWT (PRD-03)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from server.auth.subscriber_cookies import (
    clear_refresh_cookie,
    refresh_from_request,
    set_refresh_cookie,
)
from server.auth.subscriber_dependencies import require_subscriber_jwt
from server.config.env import get_settings
from server.services.saas import auth_service
from server.services.saas.tenant_guard import SubscriberPrincipal
from server.utils.rate_limiter import RateLimiter

router = APIRouter()
_signup_limiter = RateLimiter(max_requests=20, window_s=3600)
_login_limiter = RateLimiter(max_requests=30, window_s=300)


class SignupBody(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=8, max_length=200)
    fullName: str = Field(..., min_length=1, max_length=255)
    orgName: str = Field(..., min_length=1, max_length=255)


class LoginBody(BaseModel):
    email: str
    password: str


class RefreshBody(BaseModel):
    refreshToken: str | None = Field(None, min_length=10)


class ResendVerificationBody(BaseModel):
    email: str


class LogoutBody(BaseModel):
    refreshToken: str | None = None


class ChangePasswordBody(BaseModel):
    currentPassword: str
    newPassword: str = Field(..., min_length=8)


class ForgotPasswordBody(BaseModel):
    email: str


class ResetPasswordBody(BaseModel):
    token: str
    newPassword: str = Field(..., min_length=8)


class SwitchTenantBody(BaseModel):
    tenantId: str


class DeleteAccountBody(BaseModel):
    password: str
    confirm: str


class PatchMeBody(BaseModel):
    fullName: str | None = None


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _ensure_saas_db() -> None:
    settings = get_settings()
    if not settings.saas_auth_enabled:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "saas_auth_disabled", "message": "Set SAAS_AUTH_ENABLED=true"}},
        )
    if not settings.database_url:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "db_unavailable", "message": "DATABASE_URL required"}},
        )


def _attach_refresh(response: Response, payload: dict) -> dict:
    refresh = payload.get("refreshToken")
    if refresh:
        set_refresh_cookie(response, refresh)
        safe = {k: v for k, v in payload.items() if k != "refreshToken"}
        return safe
    return payload


@router.post("/api/auth/signup")
async def auth_signup(body: SignupBody, request: Request, response: Response):
    _ensure_saas_db()
    ip = _client_ip(request) or "unknown"
    allowed, retry = _signup_limiter.allow(f"signup:{ip}")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={"error": {"code": "rate_limit", "message": "Too many signups", "retry_after": retry}},
        )
    try:
        data = await auth_service.signup(
            email=body.email,
            password=body.password,
            full_name=body.fullName,
            org_name=body.orgName,
            ip=ip,
        )
        return data
    except ValueError as e:
        code = str(e)
        if code == "email_taken":
            raise HTTPException(
                status_code=409,
                detail={"error": {"code": "signup_failed", "message": "Unable to create an account with these details."}},
            )
        raise HTTPException(status_code=400, detail={"error": {"code": code, "message": code}})


@router.post("/api/auth/login")
async def auth_login(body: LoginBody, request: Request, response: Response):
    _ensure_saas_db()
    ip = _client_ip(request) or "unknown"
    allowed, retry = _login_limiter.allow(f"login:{ip}:{body.email}")
    if not allowed:
        raise HTTPException(status_code=429, detail={"error": {"code": "rate_limit", "retry_after": retry}})
    try:
        data = await auth_service.login(email=body.email, password=body.password, ip=ip)
        return _attach_refresh(response, data)
    except ValueError as e:
        code = str(e)
        if code == "email_unverified":
            raise HTTPException(
                status_code=403,
                detail={
                    "error": {
                        "code": "email_unverified",
                        "message": "Verify your email before signing in. Check your inbox or resend below.",
                    }
                },
            )
        if code in ("invalid_credentials", "account_disabled", "tenant_inactive"):
            raise HTTPException(
                status_code=401,
                detail={"error": {"code": "auth_error", "message": "Invalid email or password."}},
            )
        raise HTTPException(status_code=400, detail={"error": {"code": code, "message": code}})


@router.post("/api/auth/refresh")
async def auth_refresh(request: Request, response: Response, body: RefreshBody | None = None):
    _ensure_saas_db()
    token = refresh_from_request(request, body.refreshToken if body else None)
    if not token:
        raise HTTPException(status_code=401, detail={"error": {"code": "invalid_refresh", "message": "Invalid refresh token"}})
    try:
        data = await auth_service.refresh(token)
        return _attach_refresh(response, data)
    except ValueError:
        raise HTTPException(status_code=401, detail={"error": {"code": "invalid_refresh", "message": "Invalid refresh token"}})


@router.post("/api/auth/logout")
async def auth_logout(request: Request, response: Response, body: LogoutBody | None = None):
    token = refresh_from_request(request, body.refreshToken if body else None)
    await auth_service.logout(token)
    clear_refresh_cookie(response)
    return {"ok": True}


@router.post("/api/auth/logout-all")
async def auth_logout_all(principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    await auth_service.logout_all(principal.user_id)
    return {"ok": True}


@router.patch("/api/auth/me")
async def auth_patch_me(body: PatchMeBody, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    from sqlalchemy import update

    from server.db.connection import get_session_factory
    from server.db.models.saas_models import User

    factory = get_session_factory()
    if factory is None or body.fullName is None:
        return {"ok": True}
    async with factory() as session:
        await session.execute(
            update(User).where(User.user_id == principal.user_id).values(full_name=body.fullName.strip())
        )
        await session.commit()
    return {"ok": True}


@router.post("/api/auth/change-password")
async def auth_change_password(body: ChangePasswordBody, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    try:
        await auth_service.change_password(principal.user_id, body.currentPassword, body.newPassword)
        return {"ok": True}
    except ValueError:
        raise HTTPException(status_code=401, detail={"error": {"code": "invalid_credentials", "message": "Invalid password"}})


@router.post("/api/auth/forgot-password")
async def auth_forgot_password(body: ForgotPasswordBody, request: Request):
    _ensure_saas_db()
    ip = _client_ip(request) or "unknown"
    allowed, retry = _login_limiter.allow(f"forgot:{ip}")
    if not allowed:
        raise HTTPException(status_code=429, detail={"error": {"code": "rate_limit", "retry_after": retry}})
    token = await auth_service.forgot_password(body.email)
    settings = get_settings()
    if token:
        reset_url = f"{settings.voxly_frontend_url.rstrip('/')}/#reset-password?token={token}"
        from server.services.saas.email_service import send_password_reset_email

        await send_password_reset_email(body.email.strip().lower(), reset_url)
    return {
        "ok": True,
        "message": "If an account exists for this email, password reset instructions were sent.",
    }


@router.post("/api/auth/reset-password")
async def auth_reset_password(body: ResetPasswordBody):
    _ensure_saas_db()
    try:
        await auth_service.reset_password(body.token, body.newPassword)
        return {"ok": True}
    except ValueError:
        raise HTTPException(status_code=400, detail={"error": {"code": "invalid_token", "message": "Invalid token"}})


class VerifyEmailBody(BaseModel):
    token: str = Field(..., min_length=10)


@router.post("/api/auth/verify-email")
async def auth_verify_email(body: VerifyEmailBody):
    _ensure_saas_db()
    try:
        await auth_service.verify_email_token(body.token)
        return {"ok": True, "message": "Email verified. You can sign in now."}
    except ValueError:
        raise HTTPException(status_code=400, detail={"error": {"code": "invalid_token", "message": "Invalid or expired link"}})


@router.post("/api/auth/resend-verification")
async def auth_resend_verification(body: ResendVerificationBody, request: Request):
    _ensure_saas_db()
    ip = _client_ip(request) or "unknown"
    allowed, retry = _signup_limiter.allow(f"resend:{ip}")
    if not allowed:
        raise HTTPException(status_code=429, detail={"error": {"code": "rate_limit", "retry_after": retry}})
    await auth_service.resend_verification_email(body.email)
    return {"ok": True, "message": "If an unverified account exists, a new email was sent."}


@router.post("/api/auth/switch-tenant")
async def auth_switch_tenant(body: SwitchTenantBody, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    try:
        return await auth_service.switch_tenant(principal.user_id, uuid.UUID(body.tenantId))
    except ValueError as e:
        code = str(e)
        status = 404 if code == "not_found" else 403
        raise HTTPException(status_code=status, detail={"error": {"code": code, "message": code}})


@router.post("/api/auth/delete-account")
async def auth_delete_account(body: DeleteAccountBody, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    try:
        await auth_service.delete_account(principal.user_id, body.password, body.confirm)
        return {"ok": True}
    except ValueError as e:
        code = str(e)
        if code == "sole_admin_with_numbers":
            raise HTTPException(
                status_code=409,
                detail={"error": {"code": code, "message": "Transfer ownership or delete organization first"}},
            )
        raise HTTPException(status_code=400, detail={"error": {"code": code, "message": code}})


class InviteMemberBody(BaseModel):
    email: str
    role: str = "customer_viewer"


@router.post("/api/tenants/members/invite")
async def invite_member(body: InviteMemberBody, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    from server.services.saas.tenant_guard import require_subscriber_permission

    require_subscriber_permission(principal, "app.members.write")
    try:
        return await auth_service.invite_member(
            principal.tenant_id,
            principal.user_id,
            email=body.email,
            role=body.role,
        )
    except ValueError as e:
        raise HTTPException(status_code=403, detail={"error": {"code": str(e), "message": str(e)}})


@router.post("/api/tenants/leave")
async def leave_tenant(principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    try:
        await auth_service.leave_tenant(principal.user_id, principal.tenant_id)
        return {"ok": True}
    except ValueError as e:
        code = str(e)
        if code == "sole_admin":
            raise HTTPException(status_code=409, detail={"error": {"code": code, "message": "Transfer ownership first"}})
        raise HTTPException(status_code=404, detail={"error": {"code": code, "message": code}})


class TransferOwnershipBody(BaseModel):
    newAdminUserId: str


@router.post("/api/tenants/transfer-ownership")
async def transfer_ownership(
    body: TransferOwnershipBody,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    from server.services.saas.tenant_guard import require_subscriber_permission

    require_subscriber_permission(principal, "app.members.write")
    try:
        await auth_service.transfer_ownership(
            principal.tenant_id,
            principal.user_id,
            uuid.UUID(body.newAdminUserId),
        )
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=403, detail={"error": {"code": str(e), "message": str(e)}})


@router.delete("/api/tenants/members/{user_id}")
async def remove_member(user_id: str, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    from server.services.saas.tenant_guard import require_subscriber_permission

    require_subscriber_permission(principal, "app.members.write")
    try:
        await auth_service.remove_member(principal.tenant_id, principal.user_id, uuid.UUID(user_id))
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=403, detail={"error": {"code": str(e), "message": str(e)}})


class GoogleTokenBody(BaseModel):
    idToken: str = Field(..., min_length=10)


@router.get("/api/auth/google/config")
async def auth_google_config():
    from server.services.saas.google_oauth_service import google_signin_config

    return google_signin_config()


@router.get("/api/auth/google/start")
async def auth_google_start():
    from fastapi.responses import RedirectResponse

    from server.services.saas.google_oauth_service import google_oauth_authorize_url, new_oauth_state

    _ensure_saas_db()
    try:
        state = new_oauth_state()
        url = google_oauth_authorize_url(state)
        return RedirectResponse(url)
    except ValueError as e:
        raise HTTPException(status_code=503, detail={"error": {"code": str(e), "message": str(e)}})


@router.get("/api/auth/google/callback")
async def auth_google_callback(
    code: str | None = None,
    error: str | None = None,
    state: str | None = None,
):
    from fastapi.responses import RedirectResponse

    from server.config.env import get_settings
    from server.services.saas.google_oauth_service import (
        consume_oauth_state,
        exchange_code_for_tokens,
        login_or_register_google,
    )

    settings = get_settings()
    if error or not code:
        return RedirectResponse(f"{settings.voxly_frontend_url}/?auth_error=google")
    if not consume_oauth_state(state):
        return RedirectResponse(f"{settings.voxly_frontend_url}/?auth_error=google_state")
    _ensure_saas_db()
    try:
        id_token = await exchange_code_for_tokens(code)
        data = await login_or_register_google(id_token)
        q = f"accessToken={data['accessToken']}&expiresIn={data.get('expiresIn', 900)}"
        resp = RedirectResponse(f"{settings.voxly_frontend_url}/#auth/callback?{q}")
        if data.get("refreshToken"):
            set_refresh_cookie(resp, data["refreshToken"])
        return resp
    except ValueError:
        return RedirectResponse(f"{settings.voxly_frontend_url}/?auth_error=google")


@router.post("/api/auth/google")
async def auth_google(body: GoogleTokenBody, response: Response):
    _ensure_saas_db()
    from server.services.saas.google_oauth_service import login_or_register_google

    try:
        data = await login_or_register_google(body.idToken)
        return _attach_refresh(response, data)
    except ValueError as e:
        code = str(e)
        status = 401 if "invalid" in code else 400
        raise HTTPException(status_code=status, detail={"error": {"code": code, "message": code}})


@router.post("/api/auth/github")
async def auth_github():
    raise HTTPException(status_code=501, detail={"error": {"code": "not_implemented", "message": "OAuth later"}})


@router.post("/api/tenants/delete")
async def tenants_delete(principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    try:
        job_id = await auth_service.delete_tenant(principal.tenant_id, principal.user_id)
        return {"ok": True, "jobId": str(job_id)}
    except ValueError as e:
        raise HTTPException(status_code=403, detail={"error": {"code": str(e), "message": str(e)}})
