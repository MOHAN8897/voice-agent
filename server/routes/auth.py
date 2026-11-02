"""Auth routes — Dev Portal and Business Console login."""
from __future__ import annotations

import asyncio
import threading
import time

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from server.auth.passwords import verify_portal_password
from server.auth.rbac import ROLE_DEVELOPER, ROLE_SUPER_ADMIN
from server.auth.session import (
    BUILTIN_DEV_TTL_SEC,
    cookie_names,
    create_csrf_token,
    create_session_token,
    parse_session_token,
)
from server.config.env import get_settings
from server.services.saas.admin_audit import record_admin_action
from server.utils.rate_limiter import RateLimiter

router = APIRouter()
_login_limiter = RateLimiter(max_requests=10, window_s=300)
_SESSION_MAX_AGE = 86400 * 7


class _AccountLockout:
    """Per-account failure counter: `max_failures` wrong passwords inside `window_s`
    lock that login for `lock_s`, whatever IP they come from. Only failures count and a
    successful sign-in clears the slate. Shared through Redis (every worker and server sees
    the same count and lock); counted in-process when Redis is not reachable.
    """

    def __init__(self, max_failures: int = 10, window_s: int = 900, lock_s: int = 900, max_keys: int = 10000):
        self.max_failures = max_failures
        self.window_s = window_s
        self.lock_s = lock_s
        self.max_keys = max_keys
        self._failures: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _shared():
        from server.utils.rate_limiter import _redis, _redis_failed

        state = _redis()
        return (state["client"], _redis_failed) if state is not None else (None, None)

    def locked(self, key: str) -> int:
        """Seconds until `key` unlocks, or 0 when it is not locked."""
        client, failed = self._shared()
        if client is not None:
            try:
                ttl = client.ttl(f"lockout:dev:{key}")
                return int(ttl) + 1 if ttl and ttl > 0 else 0
            except Exception:
                failed()
        now = time.monotonic()
        with self._lock:
            until = self._locked_until.get(key)
            if until is None:
                return 0
            if until <= now:
                self._locked_until.pop(key, None)
                return 0
            return int(until - now) + 1

    def fail(self, key: str) -> bool:
        """Count one failure; True when this failure locked the account."""
        client, failed = self._shared()
        if client is not None:
            try:
                pipe = client.pipeline()
                pipe.incr(f"failures:dev:{key}")
                pipe.expire(f"failures:dev:{key}", self.window_s, nx=True)
                count = int(pipe.execute()[0])
                if count >= self.max_failures:
                    pipe = client.pipeline()
                    pipe.set(f"lockout:dev:{key}", 1, ex=self.lock_s)
                    pipe.delete(f"failures:dev:{key}")
                    pipe.execute()
                    return True
                return False
            except Exception:
                failed()
        now = time.monotonic()
        with self._lock:
            if key not in self._failures and len(self._failures) >= self.max_keys:
                self._failures = {k: v for k, v in self._failures.items() if v and now - v[-1] < self.window_s}
                self._locked_until = {k: v for k, v in self._locked_until.items() if v > now}
            recent = [t for t in self._failures.get(key, []) if now - t < self.window_s]
            recent.append(now)
            if len(recent) >= self.max_failures:
                self._failures.pop(key, None)
                self._locked_until[key] = now + self.lock_s
                return True
            self._failures[key] = recent
            return False

    def succeed(self, key: str) -> None:
        client, failed = self._shared()
        if client is not None:
            try:
                client.delete(f"failures:dev:{key}", f"lockout:dev:{key}")
            except Exception:
                failed()
        with self._lock:
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()
            self._locked_until.clear()


_account_lockout = _AccountLockout()


class LoginBody(BaseModel):
    username: str = Field(..., min_length=1, max_length=320)
    password: str = Field(..., min_length=1, max_length=200)


def _portal_username_matches(expected: str | None, provided: str) -> bool:
    exp = (expected or "").strip()
    got = (provided or "").strip()
    if not exp or not got:
        return False
    return exp.casefold() == got.casefold()


def _login_key(username: str) -> str:
    """The same normalisation the username match uses, so `Admin ` and `admin` share a bucket."""
    return (username or "").strip().casefold()


def _is_https(request: Request | None) -> bool:
    if request is None:
        return False
    if request.url.scheme == "https":
        return True
    forwarded = request.headers.get("x-forwarded-proto") or ""
    return forwarded.split(",")[0].strip().lower() == "https"


def _cookie_opts(request: Request | None = None) -> dict:
    # Only plain-http local development may send session cookies without `secure`.
    secure = get_settings().app_environment != "development" or _is_https(request)
    return {"httponly": True, "secure": secure, "samesite": "lax", "path": "/"}


def _set_session_cookies(
    response: Response,
    kind: str,
    token: str,
    csrf: str,
    request: Request | None = None,
    max_age: int = _SESSION_MAX_AGE,
) -> None:
    names = cookie_names()
    cookie_name = names["dev"] if kind == "dev" else names["app"]
    csrf_name = names["dev_csrf"] if kind == "dev" else names["app_csrf"]
    opts = _cookie_opts(request)
    response.set_cookie(cookie_name, token, max_age=max_age, **opts)
    response.set_cookie(csrf_name, csrf, httponly=False, secure=opts["secure"], samesite="lax", path="/", max_age=max_age)


def _clear_session_cookies(response: Response, kind: str, request: Request | None = None) -> None:
    names = cookie_names()
    cookie_name = names["dev"] if kind == "dev" else names["app"]
    csrf_name = names["dev_csrf"] if kind == "dev" else names["app_csrf"]
    opts = _cookie_opts(request)
    response.delete_cookie(
        cookie_name,
        path="/",
        httponly=True,
        samesite=opts["samesite"],
        secure=opts["secure"],
    )
    response.delete_cookie(
        csrf_name,
        path="/",
        httponly=False,
        samesite=opts["samesite"],
        secure=opts["secure"],
    )


@router.post("/api/dev/login")
async def dev_login(body: LoginBody, request: Request, response: Response):
    """Sign in to the admin portal.

    Two kinds of admin can sign in here: the built-in break-glass login configured
    by DEV_PORTAL_USERNAME / DEV_PORTAL_PASSWORD (a super admin, managed only by
    configuration), and stored platform-admin accounts managed on Roles & access.
    """
    settings = get_settings()
    builtin_configured = bool(settings.dev_portal_username and settings.dev_portal_password)
    ip = request.client.host if request.client else "unknown"
    login_key = _login_key(body.username)
    allowed, retry = _login_limiter.allow(f"dev:{ip}:{login_key}")
    if not allowed:
        return {
            "ok": False,
            "error": {"code": "rate_limit", "message": "Too many login attempts", "retry_after": retry},
        }
    locked_for = _account_lockout.locked(login_key)
    if locked_for:
        return {
            "ok": False,
            "error": {
                "code": "account_locked",
                "message": "Too many failed sign-ins. Try again later.",
                "retry_after": locked_for,
            },
        }
    if builtin_configured and _portal_username_matches(settings.dev_portal_username, body.username):
        # The built-in username is reserved: never fall through to stored accounts.
        if not await asyncio.to_thread(verify_portal_password, settings.dev_portal_password, body.password):
            await _record_failed_sign_in(login_key, ip, "builtin", request)
            return {"ok": False, "error": {"code": "auth_error", "message": "Invalid credentials"}}
        _account_lockout.succeed(login_key)
        csrf = create_csrf_token()
        token = create_session_token("dev", body.username, settings.default_tenant_id, ROLE_SUPER_ADMIN)
        _set_session_cookies(response, "dev", token, csrf, request, max_age=BUILTIN_DEV_TTL_SEC)
        await _record_sign_in(login_key, ip, "builtin", ROLE_SUPER_ADMIN, request)
        return {"ok": True, "role": ROLE_SUPER_ADMIN, "csrf_token": csrf}

    from server.services.saas import admin_accounts

    account = await admin_accounts.authenticate(body.username, body.password, ip=ip, request=request)
    if account is None:
        if not builtin_configured and not await admin_accounts.any_accounts():
            return {"ok": False, "error": {"code": "auth_error", "message": "Dev portal not configured"}}
        await _record_failed_sign_in(login_key, ip, "stored", request)
        return {"ok": False, "error": {"code": "auth_error", "message": "Invalid credentials"}}
    _account_lockout.succeed(login_key)
    csrf = create_csrf_token()
    token = create_session_token(
        "dev",
        account.username,
        settings.default_tenant_id,
        account.role,
        account_ref=admin_accounts.session_ref(account),
    )
    _set_session_cookies(response, "dev", token, csrf, request)
    await _record_sign_in(account.username, ip, "stored", account.role, request)
    return {"ok": True, "role": account.role, "csrf_token": csrf}


async def _record_failed_sign_in(login_key: str, ip: str, kind: str, request: Request) -> None:
    locked = _account_lockout.fail(login_key)
    try:
        await record_admin_action(
            actor=login_key[:255] or "unknown",
            action="dev_portal.sign_in_failed",
            resource_type="dev_session",
            resource_id=login_key[:255],
            payload={"ip": ip, "kind": kind, "locked": locked},
            request=request,
        )
    except Exception:
        pass


async def _record_sign_in(subject: str, ip: str, kind: str, role: str, request: Request) -> None:
    try:
        await record_admin_action(
            actor=subject[:255],
            action="dev_portal.sign_in",
            resource_type="dev_session",
            resource_id=subject[:255],
            payload={"ip": ip, "kind": kind, "role": role},
            request=request,
        )
    except Exception:
        pass


@router.post("/api/dev/logout")
async def dev_logout(request: Request, response: Response):
    # Stored-admin cookies are revoked server-side by bumping the account's session
    # epoch; the built-in login has no server state, which is why its TTL is short.
    session = parse_session_token(request.cookies.get(cookie_names()["dev"]) or "", "dev")
    if session is not None and session.account_ref:
        from server.services.saas import admin_accounts

        await admin_accounts.end_session(session.account_ref)
    _clear_session_cookies(response, "dev", request)
    return {"ok": True}


@router.post("/api/app/login")
async def app_login(body: LoginBody, response: Response, request: Request = None):
    settings = get_settings()
    if settings.saas_auth_enabled:
        raise HTTPException(
            status_code=410,
            detail={
                "error": {
                    "code": "deprecated",
                    "message": "Use POST /api/auth/login with email and password",
                }
            },
        )
    if not settings.app_console_username or not settings.app_console_password:
        return {"ok": False, "error": {"code": "auth_error", "message": "App login not configured"}}
    allowed, retry = _login_limiter.allow(f"app:{_login_key(body.username)}")
    if not allowed:
        return {
            "ok": False,
            "error": {"code": "rate_limit", "message": "Too many login attempts", "retry_after": retry},
        }
    if not _portal_username_matches(settings.app_console_username, body.username) or not await asyncio.to_thread(
        verify_portal_password, settings.app_console_password, body.password
    ):
        return {"ok": False, "error": {"code": "auth_error", "message": "Invalid credentials"}}
    csrf = create_csrf_token()
    token = create_session_token("app", body.username, settings.default_tenant_id, ROLE_DEVELOPER)
    _set_session_cookies(response, "app", token, csrf, request)
    return {"ok": True, "role": ROLE_DEVELOPER, "csrf_token": csrf}


@router.post("/api/app/logout")
async def app_logout(request: Request, response: Response):
    _clear_session_cookies(response, "app", request)
    return {"ok": True}


@router.get("/api/app/logout")
async def app_logout_get(request: Request, response: Response):
    _clear_session_cookies(response, "app", request)
    return {"ok": True}


@router.get("/api/auth/session")
async def auth_session():
    settings = get_settings()
    return {
        "dev_configured": bool(settings.dev_portal_username and settings.dev_portal_password),
        "app_configured": bool(settings.app_console_username and settings.app_console_password),
        "saas_auth_enabled": settings.saas_auth_enabled,
        "environment": settings.app_environment,
        "default_tenant_id": settings.default_tenant_id,
    }


@router.get("/api/auth/me")
async def auth_me(request: Request):
    settings = get_settings()
    if settings.saas_auth_enabled:
        from server.auth.jwt_tokens import decode_access_token
        from server.services.saas import auth_service as saas_auth

        auth_header = request.headers.get("authorization") or ""
        if auth_header.lower().startswith("bearer "):
            claims = decode_access_token(auth_header.split(" ", 1)[1].strip())
            if claims is None:
                raise HTTPException(
                    status_code=401,
                    detail={"error": {"code": "auth_error", "message": "Invalid or expired token"}},
                )
            import uuid

            try:
                return await saas_auth.get_me(
                    uuid.UUID(claims.user_id),
                    uuid.UUID(claims.tenant_id),
                    impersonator=claims.impersonator,
                    remember_me=claims.remember,
                )
            except ValueError:
                raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Not found"}})
    names = cookie_names()
    session = parse_session_token(request.cookies.get(names["app"]) or "", "app")
    if session:
        csrf = request.cookies.get(names["app_csrf"])
        return {
            "ok": True,
            "authenticated": True,
            "subject": session.subject,
            "role": session.role,
            "tenant_id": session.tenant_id,
            "csrf_token": csrf,
        }
    if settings.app_console_username and settings.app_console_password:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "auth_error", "message": "App session required"}},
        )
    return {"ok": True, "authenticated": False, "subject": "dev-stub", "role": "developer"}


@router.get("/api/auth/dev-me")
async def auth_dev_me(request: Request):
    settings = get_settings()
    names = cookie_names()
    from server.auth.dependencies import refresh_admin_sessions_if_needed

    await refresh_admin_sessions_if_needed(request.cookies.get(names["dev"]))
    session = parse_session_token(request.cookies.get(names["dev"]) or "", "dev")
    if session:
        csrf = request.cookies.get(names["dev_csrf"])
        return {
            "ok": True,
            "authenticated": True,
            "subject": session.subject,
            "role": session.role,
            "tenant_id": session.tenant_id,
            "csrf_token": csrf,
        }
    if settings.dev_portal_username and settings.dev_portal_password:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "auth_error", "message": "Dev session required"}},
        )
    raise HTTPException(
        status_code=401,
        detail={"error": {"code": "auth_error", "message": "Dev portal credentials not configured"}},
    )
