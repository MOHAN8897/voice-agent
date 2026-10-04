"""SaaS subscriber auth — JWT (PRD-03)."""
from __future__ import annotations

import logging
import uuid

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import AliasChoices, BaseModel, Field, field_validator

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

logger = logging.getLogger(__name__)

router = APIRouter()
_signup_limiter = RateLimiter(max_requests=20, window_s=3600)
_login_limiter = RateLimiter(max_requests=30, window_s=300)


def _mask_email(email: str) -> str:
    """Enough to correlate a log line with an account, not enough to harvest one."""
    local, _, domain = (email or "").partition("@")
    if not domain:
        return "***"
    head = local[:1] or "*"
    return f"{head}***@{domain}"


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


class OnboardingSurveyBody(BaseModel):
    fullName: str = Field(..., min_length=2, validation_alias=AliasChoices("fullName", "full_name"))
    companyName: str = Field(..., min_length=2, validation_alias=AliasChoices("companyName", "company_name"))
    role: str
    referralSource: str = Field(..., validation_alias=AliasChoices("referralSource", "referral_source"))
    primaryUseCase: str = Field(..., validation_alias=AliasChoices("primaryUseCase", "primary_use_case"))
    estimatedMonthlyMinutes: str = Field(
        ..., validation_alias=AliasChoices("estimatedMonthlyMinutes", "estimated_monthly_minutes")
    )
    termsAccepted: bool = Field(..., validation_alias=AliasChoices("termsAccepted", "terms_accepted"))
    termsVersion: str = Field("2026-10-v1", validation_alias=AliasChoices("termsVersion", "terms_version"))
    acceptableUseVersion: str = Field(
        "2026-10-v1", validation_alias=AliasChoices("acceptableUseVersion", "acceptable_use_version")
    )

    @field_validator("termsAccepted")
    @classmethod
    def validate_terms_accepted(cls, v: bool) -> bool:
        if not v:
            raise ValueError("You must agree to the Terms of Service and Telephony Acceptable Use Policy.")
        return v


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
    out = payload
    if refresh:
        set_refresh_cookie(response, refresh)
        out = {k: v for k, v in payload.items() if k != "refreshToken"}
    # Every authenticated response carries the policy the browser mirrors for its idle
    # timer, so the client never has a hard-coded copy that can drift from the server.
    out.setdefault("sessionPolicy", auth_service.session_policy())
    return out


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

    from server.services.saas.email_service import email_provider_status

    settings = get_settings()
    # Same gate /forgot-password uses, for the same reason. signup() commits the account
    # before it sends, so an undeliverable provider would strand a pending_verification
    # account nobody can complete — and every retry after that answers 409 "email taken",
    # which reads as "your details are wrong". Refusing first keeps signup retryable.
    # A dev deployment with the debug flag set has no working mail by definition, so it
    # skips the gate and hands back the code instead.
    if not settings.auth_debug_expose_reset_token:
        provider = await email_provider_status()
        if not provider.get("deliverable"):
            logger.error("signup refused: email delivery unavailable (%s)", provider.get("reason"))
            raise HTTPException(
                status_code=503,
                detail={
                    "error": {
                        "code": "email_delivery_unavailable",
                        "message": "We could not send your verification email right now. Please try again shortly.",
                    }
                },
            )

    try:
        data = await auth_service.signup(
            email=body.email,
            password=body.password,
            full_name=body.fullName,
            org_name=body.orgName,
            ip=ip,
            expose_debug_otp=settings.auth_debug_expose_reset_token,
        )
        return data
    except ValueError as e:
        code = str(e)
        if code == "email_taken":
            raise HTTPException(
                status_code=409,
                detail={
                    "error": {
                        "code": "email_taken",
                        "message": "An account already exists for this email. Sign in instead, or reset your password.",
                    }
                },
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


@router.get("/api/auth/session-policy")
async def auth_session_policy():
    """Idle / absolute session limits, so the client timer matches the server's."""
    return {"ok": True, "policy": auth_service.session_policy()}


@router.post("/api/auth/refresh")
async def auth_refresh(request: Request, response: Response, body: RefreshBody | None = None):
    _ensure_saas_db()
    token = refresh_from_request(request, body.refreshToken if body else None)
    if not token:
        raise HTTPException(status_code=401, detail={"error": {"code": "invalid_refresh", "message": "Invalid refresh token"}})
    try:
        data = await auth_service.refresh(token)
        return _attach_refresh(response, data)
    except ValueError as e:
        code = str(e)
        if code in ("session_idle", "session_absolute_max"):
            # Not an error state — the session was closed on purpose. Tell the client
            # which bound it hit so the sign-in screen can explain the sign-out.
            clear_refresh_cookie(response)
            message = (
                "You were signed out after a period of inactivity. Please sign in again."
                if code == "session_idle"
                else "Your session reached its maximum length. Please sign in again."
            )
            raise HTTPException(status_code=401, detail={"error": {"code": code, "message": message}})
        if code == "tenant_inactive":
            clear_refresh_cookie(response)
            raise HTTPException(
                status_code=401,
                detail={"error": {"code": code, "message": "This workspace is no longer active."}},
            )
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
async def auth_change_password(
    body: ChangePasswordBody,
    request: Request,
    response: Response,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    try:
        data = await auth_service.change_password(principal.user_id, body.currentPassword, body.newPassword)
    except ValueError as e:
        code = str(e)
        if code in ("invalid_credentials",):
            raise HTTPException(
                status_code=401,
                detail={"error": {"code": "invalid_credentials", "message": "Current password is incorrect."}},
            )
        if code == "password_too_short":
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": code, "message": "New password must be at least 8 characters."}},
            )
        if code == "tenant_inactive":
            raise HTTPException(
                status_code=403,
                detail={"error": {"code": code, "message": "This workspace is not active."}},
            )
        raise HTTPException(status_code=400, detail={"error": {"code": code, "message": code}})
    # All other sessions were revoked; hand this browser a fresh one so the person who
    # changed the password stays signed in here.
    return _attach_refresh(response, data)


@router.post("/api/auth/forgot-password")
async def auth_forgot_password(body: ForgotPasswordBody, request: Request):
    _ensure_saas_db()
    ip = _client_ip(request) or "unknown"
    allowed, retry = _login_limiter.allow(f"forgot:{ip}")
    if not allowed:
        raise HTTPException(status_code=429, detail={"error": {"code": "rate_limit", "retry_after": retry}})

    from server.services.saas.email_service import email_provider_status, send_password_reset_email

    settings = get_settings()
    provider = await email_provider_status()
    # Fail loudly, but identically for every caller. Reporting "delivery is broken"
    # only when it is broken platform-wide leaks nothing about whether *this* address
    # has an account; reporting it per-address would be an account-existence oracle.
    # A dev deployment with the debug flag set has no working mail by definition, so it
    # skips the gate and hands back the link instead of 503-ing the whole flow.
    if not provider.get("deliverable") and not settings.auth_debug_expose_reset_token:
        logger.error("forgot-password refused: email delivery unavailable (%s)", provider.get("reason"))
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "email_delivery_unavailable",
                    "message": "We could not send the reset email right now. Please try again shortly or contact support.",
                }
            },
        )

    email = body.email.strip().lower()
    token = await auth_service.forgot_password(email)

    delivery: dict = {"attempted": False}
    if token:
        reset_url = f"{settings.voxly_frontend_url.rstrip('/')}/#reset-password?token={token}"
        result = await send_password_reset_email(email, reset_url)
        delivery = {"attempted": True, "sent": result.ok, "reason": result.code}
        if not result.ok:
            # Still 200 with the same generic message — the address may simply be
            # undeliverable. The operator needs the real reason in the logs, not the
            # person who pressed "reset" finding out how the backend is wired.
            logger.error(
                "password reset email not delivered to %s: code=%s status=%s detail=%s",
                _mask_email(email),
                result.code,
                result.provider_status,
                result.detail,
            )

    payload: dict = {
        "ok": True,
        "message": "If an account exists for this email, password reset instructions were sent.",
    }
    if settings.auth_debug_expose_reset_token and token and not delivery.get("sent"):
        # Dev/staging only fallback when email delivery failed or is unconfigured.
        payload["debugResetUrl"] = f"{settings.voxly_frontend_url.rstrip('/')}/#reset-password?token={token}"
    if delivery.get("attempted") and not delivery.get("sent"):
        # Still the same generic message — the address may simply be undeliverable. The
        # operator needs the real reason in the logs, not the person who pressed "reset"
        # finding out how the backend is wired.
        logger.error(
            "password reset email not delivered to %s: code=%s status=%s detail=%s",
            _mask_email(email),
            delivery.get("reason"),
            provider.get("reason"),
            provider.get("detail") or "",
        )
        if settings.app_environment != "production":
            payload["debugDelivery"] = {**delivery, "provider": provider.get("reason")}
    return payload


@router.post("/api/auth/reset-password")
async def auth_reset_password(body: ResetPasswordBody, request: Request, response: Response):
    _ensure_saas_db()
    ip = _client_ip(request) or "unknown"
    allowed, retry = _login_limiter.allow(f"reset:{ip}")
    if not allowed:
        raise HTTPException(status_code=429, detail={"error": {"code": "rate_limit", "retry_after": retry}})
    try:
        data = await auth_service.reset_password(body.token, body.newPassword)
    except ValueError as e:
        code = str(e)
        if code == "invalid_token":
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": code, "message": "This reset link is invalid or has expired."}},
            )
        if code == "password_too_short":
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": code, "message": "Password must be at least 8 characters."}},
            )
        raise HTTPException(status_code=400, detail={"error": {"code": code, "message": code}})
    # The token already proved the person owns the mailbox, so the reset signs them in
    # instead of dumping them back on the sign-in form with a message to retype it.
    return _attach_refresh(response, data)


class VerifyEmailBody(BaseModel):
    token: str = Field(..., min_length=10)


class VerifyEmailOtpBody(BaseModel):
    email: str = Field(..., min_length=3)
    otp: str = Field(..., min_length=6, max_length=6)


@router.post("/api/auth/verify-email")
async def auth_verify_email(body: VerifyEmailBody):
    _ensure_saas_db()
    try:
        await auth_service.verify_email_token(body.token)
        return {"ok": True, "message": "Email verified. You can sign in now."}
    except ValueError:
        raise HTTPException(status_code=400, detail={"error": {"code": "invalid_token", "message": "Invalid or expired link"}})


@router.post("/api/auth/verify-email-otp")
async def auth_verify_email_otp(body: VerifyEmailOtpBody, request: Request, response: Response):
    _ensure_saas_db()
    ip = _client_ip(request) or "unknown"
    allowed, retry = _login_limiter.allow(f"verify-otp:{ip}:{body.email}")
    if not allowed:
        raise HTTPException(status_code=429, detail={"error": {"code": "rate_limit", "retry_after": retry}})
    try:
        data = await auth_service.verify_email_otp(body.email, body.otp, ip=ip)
        return _attach_refresh(response, data)
    except ValueError as e:
        code = str(e)
        if code == "invalid_otp":
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "invalid_otp", "message": "Invalid or expired code. Request a new one."}},
            )
        raise HTTPException(status_code=400, detail={"error": {"code": code, "message": code}})


@router.post("/api/auth/resend-verification")
async def auth_resend_verification(body: ResendVerificationBody, request: Request):
    _ensure_saas_db()
    ip = _client_ip(request) or "unknown"
    allowed, retry = _signup_limiter.allow(f"resend:{ip}")
    if not allowed:
        raise HTTPException(status_code=429, detail={"error": {"code": "rate_limit", "retry_after": retry}})
    settings = get_settings()
    data = await auth_service.resend_verification_email(
        body.email, expose_debug_otp=settings.auth_debug_expose_reset_token
    )
    return {"ok": True, "message": "If an unverified account exists, a new email was sent.", **data}


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


class HandoffBody(BaseModel):
    handoff: str = Field(..., min_length=10, max_length=200)


@router.get("/api/auth/google/config")
async def auth_google_config():
    from server.services.saas.google_oauth_service import google_signin_config

    return google_signin_config()


@router.get("/api/auth/google/start")
async def auth_google_start(return_to: str | None = None):
    from fastapi.responses import RedirectResponse

    from server.services.saas.google_oauth_service import google_oauth_authorize_url, new_oauth_state

    _ensure_saas_db()
    try:
        state = new_oauth_state(return_to)
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
        create_auth_handoff,
        exchange_code_for_tokens,
        login_or_register_google,
    )

    settings = get_settings()
    default_front = settings.voxly_frontend_url.rstrip("/")
    state_info = consume_oauth_state(state)
    front = (state_info or {}).get("return_to") or default_front
    if error or not code:
        return RedirectResponse(f"{front}/?auth_error=google")
    if state_info is None:
        return RedirectResponse(f"{front}/?auth_error=google_state")
    _ensure_saas_db()
    try:
        id_token = await exchange_code_for_tokens(code)
        data = await login_or_register_google(id_token)
        # Do NOT Set-Cookie on this redirect — the API host is often not the SPA
        # origin (api-dev vs app-dev / Vite). SPA redeems handoff via same-origin /api.
        hid = create_auth_handoff(data)
        return RedirectResponse(f"{front}/#auth/callback?handoff={hid}")
    except ValueError:
        return RedirectResponse(f"{front}/?auth_error=google")


@router.post("/api/auth/handoff")
async def auth_handoff(body: HandoffBody, response: Response):
    """Redeem a one-time OAuth handoff; sets refresh cookie on the SPA origin (via proxy)."""
    _ensure_saas_db()
    from server.services.saas.google_oauth_service import consume_auth_handoff

    data = consume_auth_handoff(body.handoff)
    if not data or not data.get("accessToken"):
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "invalid_handoff", "message": "Sign-in link expired. Try again."}},
        )
    return _attach_refresh(response, data)


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


@router.post("/api/auth/onboarding-survey")
async def submit_onboarding_survey(
    body: OnboardingSurveyBody,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    if not body.termsAccepted:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "terms_required",
                    "message": "You must accept the Terms of Service and Telephony Acceptable Use Policy.",
                }
            },
        )
    from server.db.connection import get_session_factory

    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database required")

    from server.db.models.entities import Tenant
    from server.db.models.saas_models import User, UserOnboardingSurvey
    from sqlalchemy import select

    now = datetime.now(timezone.utc)
    async with factory() as session:
        # 1. Update canonical profile records (source of truth)
        user = await session.get(User, principal.user_id)
        if user:
            user.full_name = body.fullName.strip()
        tenant = await session.get(Tenant, principal.tenant_id)
        if tenant:
            tenant.name = body.companyName.strip()

        # 2. Persist telemetry to user_onboarding_surveys (no duplicate name columns)
        existing_survey = await session.execute(
            select(UserOnboardingSurvey).where(UserOnboardingSurvey.user_id == principal.user_id)
        )
        survey = existing_survey.scalar_one_or_none()
        if survey:
            survey.tenant_id = principal.tenant_id
            survey.role = body.role
            survey.referral_source = body.referralSource
            survey.primary_use_case = body.primaryUseCase
            survey.estimated_monthly_minutes = body.estimatedMonthlyMinutes
            survey.terms_and_telephony_accepted = True
            survey.terms_version = body.termsVersion
            survey.acceptable_use_version = body.acceptableUseVersion
            survey.terms_accepted_at = now
        else:
            survey = UserOnboardingSurvey(
                id=uuid.uuid4(),
                user_id=principal.user_id,
                tenant_id=principal.tenant_id,
                role=body.role,
                referral_source=body.referralSource,
                primary_use_case=body.primaryUseCase,
                estimated_monthly_minutes=body.estimatedMonthlyMinutes,
                terms_and_telephony_accepted=True,
                terms_version=body.termsVersion,
                acceptable_use_version=body.acceptableUseVersion,
                terms_accepted_at=now,
                created_at=now,
            )
            session.add(survey)

        await session.commit()

    return {
        "ok": True,
        "hasCompletedOnboarding": True,
        "fullName": body.fullName.strip(),
        "companyName": body.companyName.strip(),
    }


@router.get("/api/auth/onboarding-survey")
async def get_onboarding_survey(principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    from server.db.connection import get_session_factory

    factory = get_session_factory()
    if factory is None:
        return {"hasCompletedOnboarding": False, "survey": None}

    from server.db.models.saas_models import UserOnboardingSurvey
    from sqlalchemy import select

    async with factory() as session:
        result = await session.execute(
            select(UserOnboardingSurvey).where(UserOnboardingSurvey.user_id == principal.user_id)
        )
        survey = result.scalar_one_or_none()
        if not survey:
            return {"hasCompletedOnboarding": False, "survey": None}
        return {
            "hasCompletedOnboarding": bool(survey.terms_and_telephony_accepted),
            "survey": {
                "role": survey.role,
                "referralSource": survey.referral_source,
                "primaryUseCase": survey.primary_use_case,
                "estimatedMonthlyMinutes": survey.estimated_monthly_minutes,
                "termsAccepted": survey.terms_and_telephony_accepted,
                "termsVersion": survey.terms_version,
                "acceptableUseVersion": survey.acceptable_use_version,
                "termsAcceptedAt": survey.terms_accepted_at.isoformat() if survey.terms_accepted_at else None,
            },
        }
