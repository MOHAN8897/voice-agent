"""Subscriber signup, login, refresh, password, account lifecycle."""
from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.jwt_tokens import AccessTokenClaims, create_access_token
from server.auth.passwords import hash_portal_password, verify_portal_password
from server.auth.rbac import ROLE_CUSTOMER_ADMIN, ROLE_PLATFORM_ADMIN
from server.config.env import get_settings
from server.services.saas.platform_admins import (
    effective_membership_role,
    is_dev_tester_email,
    is_platform_admin_email,
)
from server.db.connection import get_session_factory
from server.db.models.entities import Agent, Tenant
from server.db.models.phase5_models import PhoneNumber
from server.db.models.saas_models import (
    AuthEvent,
    EmailVerificationToken,
    PasswordResetToken,
    RefreshToken,
    TenantMembership,
    TenantTeardownJob,
    User,
)
from server.services.saas.email_service import send_password_reset_email, send_verification_email
from server.services.saas.tenant_guard import resolve_usable_tenant

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# How long after a rotation a replay of the same token still counts as the parallel
# -request race rather than a leaked token. Long enough to cover a burst of console
# requests landing a few hundred ms apart, short enough that real reuse is caught.
REFRESH_REUSE_GRACE_SECONDS = 30


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _validate_password(password: str) -> None:
    if len(password) < 8:
        raise ValueError("password_too_short")


async def _log_event(
    session: AsyncSession,
    event_type: str,
    *,
    user_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    ip: str | None = None,
) -> None:
    session.add(
        AuthEvent(
            user_id=user_id,
            tenant_id=tenant_id,
            event_type=event_type,
            ip=ip,
            created_at=_utcnow(),
        )
    )


async def _issue_tokens(
    session: AsyncSession,
    user: User,
    tenant_id: uuid.UUID,
    role: str,
    family_id: uuid.UUID | None = None,
    *,
    impersonator: str | None = None,
    access_ttl_seconds: int | None = None,
    absolute_expires_at: datetime | None = None,
) -> dict[str, Any]:
    claims = AccessTokenClaims(
        user_id=str(user.user_id),
        tenant_id=str(tenant_id),
        role=role,
        email=user.email,
        impersonator=impersonator,
    )
    access, expires_in = create_access_token(claims, ttl_seconds=access_ttl_seconds)
    raw_refresh = secrets.token_urlsafe(48)
    # A rotation continues the caller's family so reuse detection can see the whole
    # chain; a fresh sign-in starts a new one.
    family_id = family_id or uuid.uuid4()
    settings = get_settings()
    # Impersonation refresh is short-lived so a leaked handoff cannot linger.
    refresh_days = 1 if impersonator else settings.jwt_refresh_ttl_days
    now = _utcnow()
    # The absolute ceiling belongs to the *sign-in*, not the token, so a rotation must
    # carry the family's original deadline forward. Otherwise every refresh would
    # restart the clock and the ceiling would never be reached.
    out_exp = await _session_absolute_deadline(
        session,
        family_id,
        default=now + timedelta(hours=max(1, settings.session_absolute_max_hours or 24)),
        inherit=absolute_expires_at,
    )
    session.add(
        RefreshToken(
            user_id=user.user_id,
            token_hash=_hash_token(raw_refresh),
            family_id=family_id,
            expires_at=now + timedelta(days=refresh_days),
            created_at=now,
            last_active_at=now,
            absolute_expires_at=out_exp,
        )
    )
    out: dict[str, Any] = {
        "accessToken": access,
        "refreshToken": raw_refresh,
        "expiresIn": expires_in,
        "sessionExpiresAt": out_exp.isoformat(),
    }
    if impersonator:
        out["impersonation"] = {
            "actor": impersonator,
            "expiresIn": expires_in,
        }
    return out


async def _session_absolute_deadline(
    session: AsyncSession,
    family_id: uuid.UUID,
    *,
    default: datetime,
    inherit: datetime | None,
) -> datetime:
    """Deadline that caps one sign-in, however often the token rotates."""
    if inherit is not None:
        return inherit
    existing = await session.scalar(
        select(func.min(RefreshToken.absolute_expires_at)).where(
            RefreshToken.family_id == family_id
        )
    )
    if existing is not None:
        return existing
    return default


def session_policy() -> dict[str, Any]:
    """The policy the client mirrors for its idle timer."""
    settings = get_settings()
    return {
        "idleTimeoutMinutes": settings.session_idle_timeout_minutes,
        "absoluteMaxHours": settings.session_absolute_max_hours,
        "accessTokenMinutes": settings.jwt_access_ttl_minutes,
    }


async def issue_impersonation_session(
    *,
    tenant_id: uuid.UUID,
    actor: str,
    user_id: uuid.UUID | None = None,
    ttl_seconds: int = 30 * 60,
) -> dict[str, Any]:
    """Mint a time-boxed subscriber session as a tenant member (support impersonation)."""
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    async with factory() as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None or tenant.deleted_at is not None:
            raise ValueError("tenant_not_found")
        if tenant.status in {"cancelled"}:
            raise ValueError("tenant_cancelled")
        mem_q = (
            select(TenantMembership, User)
            .join(User, User.user_id == TenantMembership.user_id)
            .where(
                TenantMembership.tenant_id == tenant_id,
                User.deleted_at.is_(None),
                User.status == "active",
            )
            .order_by(TenantMembership.created_at)
        )
        rows = (await session.execute(mem_q)).all()
        if not rows:
            raise ValueError("no_active_member")
        chosen = None
        if user_id is not None:
            for m, u in rows:
                if u.user_id == user_id:
                    chosen = (m, u)
                    break
            if chosen is None:
                raise ValueError("user_not_member")
        else:
            # Prefer customer_admin so the support view matches the tenant's admin console.
            for m, u in rows:
                if m.role in (ROLE_CUSTOMER_ADMIN, "customer_admin", ROLE_PLATFORM_ADMIN):
                    chosen = (m, u)
                    break
            if chosen is None:
                chosen = rows[0]
        membership, user = chosen
        role = _role_for_user(user.email, membership.role)
        tokens = await _issue_tokens(
            session,
            user,
            tenant_id,
            role,
            impersonator=actor.strip() or "dev-admin",
            access_ttl_seconds=ttl_seconds,
        )
        await _log_event(
            session,
            "admin_impersonation",
            user_id=user.user_id,
            tenant_id=tenant_id,
        )
        await session.commit()
        return {
            **tokens,
            **_session_public(user, tenant, role),
            "impersonation": {
                "actor": actor,
                "tenantId": str(tenant_id),
                "tenantName": tenant.name,
                "userId": str(user.user_id),
                "userEmail": user.email,
                "expiresIn": tokens["expiresIn"],
            },
        }


async def check_user_completed_onboarding(session: AsyncSession, user_id: uuid.UUID) -> bool:
    try:
        from server.db.models.saas_models import UserOnboardingSurvey

        result = await session.execute(
            select(UserOnboardingSurvey.id)
            .where(
                UserOnboardingSurvey.user_id == user_id,
                UserOnboardingSurvey.terms_and_telephony_accepted.is_(True),
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None
    except Exception:
        return False


def _user_public(user: User, has_completed_onboarding: bool = False) -> dict[str, Any]:
    return {
        "userId": str(user.user_id),
        "email": user.email,
        "fullName": user.full_name,
        "status": user.status,
        "emailVerified": user.email_verified_at is not None,
        "hasCompletedOnboarding": has_completed_onboarding,
    }


def _tenant_public(tenant: Tenant) -> dict[str, Any]:
    return {
        "tenantId": str(tenant.tenant_id),
        "name": tenant.name,
        "plan": tenant.plan,
        "status": tenant.status,
        "limits": tenant.limits or {},
    }


def _session_public(
    user: User,
    tenant: Tenant,
    role: str,
    has_completed_onboarding: bool = False,
) -> dict[str, Any]:
    return {
        "user": _user_public(user, has_completed_onboarding=has_completed_onboarding),
        "tenant": _tenant_public(tenant),
        "role": role,
        "isPlatformAdmin": is_platform_admin_email(user.email),
        "isDevTester": is_dev_tester_email(user.email),
        "hasCompletedOnboarding": has_completed_onboarding,
    }


def _role_for_user(email: str, stored_role: str | None = None) -> str:
    return effective_membership_role(email, stored_role or ROLE_CUSTOMER_ADMIN)


async def _seed_admin_wallet(tenant_id: uuid.UUID, user_id: uuid.UUID, email: str) -> None:
    try:
        from server.services.saas.billing_wallet_service import maybe_seed_admin_credits

        await maybe_seed_admin_credits(tenant_id, user_id, email)
    except Exception:
        pass


async def login_or_create_oauth_user(
    *,
    email: str,
    full_name: str,
    provider: str,
) -> dict[str, Any]:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    norm = _normalize_email(email)
    async with factory() as session:
        result = await session.execute(
            select(User).where(func.lower(User.email) == norm, User.deleted_at.is_(None))
        )
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                email=norm,
                password_hash=hash_portal_password(secrets.token_urlsafe(32)),
                full_name=full_name,
                status="active",
                email_verified_at=_utcnow(),
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
            session.add(user)
            await session.flush()
            tenant = Tenant(
                name=f"{full_name}'s Workspace",
                plan="starter",
                status="active",
                limits={"max_concurrent_pstn": 20, "max_agents": 20},
                billing_source="self_serve",
                created_at=_utcnow(),
            )
            session.add(tenant)
            await session.flush()
            signup_role = _role_for_user(norm)
            session.add(
                TenantMembership(
                    user_id=user.user_id,
                    tenant_id=tenant.tenant_id,
                    role=signup_role,
                    created_at=_utcnow(),
                )
            )
            await _log_event(session, f"signup_{provider}", user_id=user.user_id, tenant_id=tenant.tenant_id)
            tokens = await _issue_tokens(session, user, tenant.tenant_id, signup_role)
            await session.commit()
            await _seed_admin_wallet(tenant.tenant_id, user.user_id, norm)
            return {
                **tokens,
                **_session_public(user, tenant, signup_role),
            }
        picked = await resolve_usable_tenant(session, user.user_id)
        if picked is None:
            tenant = Tenant(
                name=f"{user.full_name or 'My'}'s Workspace",
                plan="starter",
                status="active",
                limits={"max_concurrent_pstn": 20, "max_agents": 20},
                billing_source="self_serve",
                created_at=_utcnow(),
            )
            session.add(tenant)
            await session.flush()
            role = _role_for_user(user.email)
            membership = TenantMembership(
                user_id=user.user_id,
                tenant_id=tenant.tenant_id,
                role=role,
                created_at=_utcnow(),
            )
            session.add(membership)
        else:
            membership, tenant = picked
            role = _role_for_user(user.email, membership.role)
            if membership.role != role:
                membership.role = role
        if user.email_verified_at is None:
            user.email_verified_at = _utcnow()
        if user.status == "pending_verification":
            user.status = "active"
            user.updated_at = _utcnow()
        tokens = await _issue_tokens(session, user, tenant.tenant_id, role)
        await _log_event(session, f"login_{provider}", user_id=user.user_id, tenant_id=tenant.tenant_id)
        onboarded = await check_user_completed_onboarding(session, user.user_id)
        await session.commit()
        await _seed_admin_wallet(tenant.tenant_id, user.user_id, user.email)
        return {**tokens, **_session_public(user, tenant, role, has_completed_onboarding=onboarded)}


def _generate_email_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


async def _create_email_verification_token(session: AsyncSession, user_id: uuid.UUID) -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    otp = _generate_email_otp()
    await session.execute(
        delete(EmailVerificationToken).where(
            EmailVerificationToken.user_id == user_id,
            EmailVerificationToken.used_at.is_(None),
        )
    )
    session.add(
        EmailVerificationToken(
            token_hash=_hash_token(raw),
            user_id=user_id,
            otp_hash=_hash_token(otp),
            expires_at=_utcnow() + timedelta(minutes=15),
            created_at=_utcnow(),
        )
    )
    return raw, otp


async def signup(
    *,
    email: str,
    password: str,
    full_name: str,
    org_name: str,
    ip: str | None = None,
    expose_debug_otp: bool = False,
) -> dict[str, Any]:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    _validate_password(password)
    norm = _normalize_email(email)
    async with factory() as session:
        existing = await session.execute(
            select(User).where(func.lower(User.email) == norm, User.deleted_at.is_(None))
        )
        if existing.scalar_one_or_none():
            raise ValueError("email_taken")
        user = User(
            email=norm,
            password_hash=hash_portal_password(password),
            full_name=full_name.strip(),
            status="pending_verification",
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        session.add(user)
        await session.flush()
        tenant = Tenant(
            name=org_name.strip(),
            plan="starter",
            status="active",
            limits={"max_concurrent_pstn": 20, "max_agents": 20},
            billing_source="self_serve",
            created_at=_utcnow(),
        )
        session.add(tenant)
        await session.flush()
        signup_role = _role_for_user(norm)
        session.add(
            TenantMembership(
                user_id=user.user_id,
                tenant_id=tenant.tenant_id,
                role=signup_role,
                created_at=_utcnow(),
            )
        )
        await _log_event(session, "signup", user_id=user.user_id, tenant_id=tenant.tenant_id, ip=ip)
        verify_raw, otp = await _create_email_verification_token(session, user.user_id)
        user_out = _user_public(user)
        tenant_out = _tenant_public(tenant)
        await session.commit()
    settings = get_settings()
    base = settings.voxly_frontend_url.rstrip("/")
    verify_url = f"{base}/#verify-email?token={verify_raw}"
    delivery = await send_verification_email(norm, verify_url, otp)
    if not delivery.ok:
        # The account row is committed before the send, so a swallowed send failure
        # strands a pending_verification account nobody can complete — and the only
        # thing the person can do next is retry signup, which reads as "email taken".
        # The reason belongs in the operator's log, not in the signup response.
        logger.error(
            "signup verification email not delivered to %s: code=%s status=%s detail=%s",
            norm,
            delivery.code,
            delivery.provider_status,
            delivery.detail,
        )
    payload = {
        "ok": True,
        "requiresEmailVerification": True,
        "message": "Enter the 6-digit code we sent to your email to finish signing up.",
        "email": norm,
        "user": user_out,
        "tenant": tenant_out,
    }
    if expose_debug_otp and not delivery.ok:
        # Dev/staging only (AUTH_DEBUG_EXPOSE_RESET_TOKEN). Only expose fallback when delivery failed.
        payload["debugOtp"] = otp
    return payload


async def login(*, email: str, password: str, ip: str | None = None) -> dict[str, Any]:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    norm = _normalize_email(email)
    async with factory() as session:
        result = await session.execute(
            select(User).where(func.lower(User.email) == norm, User.deleted_at.is_(None))
        )
        user = result.scalar_one_or_none()
        if user is None or not verify_portal_password(user.password_hash, password):
            if user:
                await _log_event(session, "login_failed", user_id=user.user_id, ip=ip)
                await session.commit()
            raise ValueError("invalid_credentials")
        settings = get_settings()
        if user.email_verified_at is None:
            raise ValueError("email_unverified")
        if user.status == "disabled":
            raise ValueError("account_disabled")
        if user.status == "pending_verification" and user.email_verified_at is None:
            raise ValueError("email_unverified")
        picked = await resolve_usable_tenant(session, user.user_id)
        if picked is None:
            # Distinguish "no workspace at all" from "every workspace is closed" so the
            # route keeps returning its specific error.
            total = await session.scalar(
                select(func.count())
                .select_from(TenantMembership)
                .where(TenantMembership.user_id == user.user_id)
            )
            raise ValueError("tenant_inactive" if total else "no_tenant")
        membership, tenant = picked
        role = _role_for_user(user.email, membership.role)
        if membership.role != role:
            membership.role = role
        await _log_event(
            session,
            "login",
            user_id=user.user_id,
            tenant_id=tenant.tenant_id,
            ip=ip,
        )
        tokens = await _issue_tokens(session, user, tenant.tenant_id, role)
        onboarded = await check_user_completed_onboarding(session, user.user_id)
        await session.commit()
        await _seed_admin_wallet(tenant.tenant_id, user.user_id, user.email)
        return {
            **tokens,
            **_session_public(user, tenant, role, has_completed_onboarding=onboarded),
        }


async def refresh(refresh_token: str) -> dict[str, Any]:
    """
    Rotate a refresh token (OAuth 2.0 Security BCP 4.14.2).

    Refresh tokens are single-use: presenting one revokes it and issues a replacement
    in the same family. The console fires a workspace sync as several parallel
    requests, and they do not all observe a rotated cookie at the same instant, so a
    token can legitimately be presented twice within milliseconds. Rejecting the
    second presentation logged the user out mid-sync — it surfaced as one resource
    failing with "Your session expired" while its siblings succeeded.

    So a replay is judged by *when* it arrives:
      - inside REFRESH_REUSE_GRACE_SECONDS of the rotation, it is that race → re-issue.
      - after the grace window, an already-used token is a real reuse → burn the whole
        family, because that means the token leaked and one of the two holders is an
        attacker. Revoking only the presented token would leave the thief working.

    Two time bounds also apply before any of that (see SESSION_IDLE_TIMEOUT_MINUTES /
    SESSION_ABSOLUTE_MAX_HOURS). They are what stop a 30-day token from acting as a
    30-day session: the browser's silent 401-refresh used to resurrect a session that
    nobody had touched for hours, on a machine that had been walked away from.
    """
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    settings = get_settings()
    idle_limit = settings.session_idle_timeout_minutes
    absolute_limit = settings.session_absolute_max_hours
    th = _hash_token(refresh_token)
    async with factory() as session:
        now = _utcnow()
        result = await session.execute(select(RefreshToken).where(RefreshToken.token_hash == th))
        row = result.scalar_one_or_none()
        if row is None or row.expires_at <= now:
            raise ValueError("invalid_refresh")

        # Sliding window + absolute ceiling. Both are per-family, so they revoke the
        # whole chain rather than leaving sibling tokens usable.
        last_active = row.last_active_at or row.created_at or now
        absolute_deadline = row.absolute_expires_at or row.expires_at
        breach: str | None = None
        if idle_limit and idle_limit > 0 and (now - last_active) > timedelta(minutes=idle_limit):
            breach = "session_idle"
        elif (
            absolute_limit
            and absolute_limit > 0
            and (now - (row.created_at or now)) >= timedelta(hours=absolute_limit)
        ):
            breach = "session_absolute_max"
        if breach is not None:
            await session.execute(
                update(RefreshToken)
                .where(RefreshToken.family_id == row.family_id, RefreshToken.revoked_at.is_(None))
                .values(revoked_at=now)
            )
            await _log_event(session, breach, user_id=row.user_id, tenant_id=None)
            await session.commit()
            raise ValueError(breach)

        is_race_replay = False
        if row.revoked_at is not None:
            if (now - row.revoked_at).total_seconds() > REFRESH_REUSE_GRACE_SECONDS:
                # Too late to be the rotation race — treat as theft and kill the chain.
                await session.execute(
                    update(RefreshToken)
                    .where(
                        RefreshToken.family_id == row.family_id,
                        RefreshToken.revoked_at.is_(None),
                    )
                    .values(revoked_at=now)
                )
                await session.commit()
                raise ValueError("invalid_refresh")
            is_race_replay = True

        user = await session.get(User, row.user_id)
        if user is None or user.deleted_at is not None or user.status == "disabled":
            raise ValueError("invalid_refresh")

        picked = await resolve_usable_tenant(session, user.user_id)
        if picked is None:
            # Every workspace for this user is soft-deleted or closed, so there is
            # nothing to re-issue against. The client must sign in again rather than
            # retry into a dead tenant.
            if not is_race_replay:
                row.revoked_at = now
                await session.commit()
            raise ValueError("tenant_inactive")
        membership, tenant = picked
        role = _role_for_user(user.email, membership.role)
        if membership.role != role:
            membership.role = role
        if not is_race_replay:
            row.revoked_at = now
        tokens = await _issue_tokens(
            session,
            user,
            membership.tenant_id,
            role,
            family_id=row.family_id,
            absolute_expires_at=absolute_deadline,
        )
        onboarded = await check_user_completed_onboarding(session, user.user_id)
        await session.commit()
        await _seed_admin_wallet(membership.tenant_id, user.user_id, user.email)
        return {**tokens, **_session_public(user, tenant, role, has_completed_onboarding=onboarded)}


async def logout(refresh_token: str | None) -> None:
    if not refresh_token:
        return
    factory = get_session_factory()
    if factory is None:
        return
    th = _hash_token(refresh_token)
    async with factory() as session:
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == th, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=_utcnow())
        )
        await session.commit()


async def logout_all(user_id: uuid.UUID) -> None:
    factory = get_session_factory()
    if factory is None:
        return
    async with factory() as session:
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=_utcnow())
        )
        await session.commit()


async def get_me(
    principal_user_id: uuid.UUID,
    principal_tenant_id: uuid.UUID,
    *,
    impersonator: str | None = None,
) -> dict[str, Any]:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    async with factory() as session:
        user = await session.get(User, principal_user_id)
        tenant = await session.get(Tenant, principal_tenant_id)
        if user is None or tenant is None:
            raise ValueError("not_found")
        memberships = await session.execute(
            select(TenantMembership).where(TenantMembership.user_id == user.user_id)
        )
        mems = [
            {"tenantId": str(m.tenant_id), "role": m.role}
            for m in memberships.scalars().all()
        ]
        mem = await session.execute(
            select(TenantMembership).where(
                TenantMembership.user_id == user.user_id,
                TenantMembership.tenant_id == principal_tenant_id,
            )
        )
        current = mem.scalar_one_or_none()
        stored = current.role if current else ROLE_CUSTOMER_ADMIN
        role = _role_for_user(user.email, stored)
        if current is not None and current.role != role:
            current.role = role
            await session.commit()
        onboarded = await check_user_completed_onboarding(session, user.user_id)
        payload = {
            **_session_public(user, tenant, role, has_completed_onboarding=onboarded),
            "memberships": mems,
        }
        if impersonator:
            payload["impersonation"] = {
                "actor": impersonator,
                "tenantId": str(principal_tenant_id),
                "tenantName": tenant.name,
                "userId": str(user.user_id),
                "userEmail": user.email,
            }
        await _seed_admin_wallet(principal_tenant_id, user.user_id, user.email)
        return payload


async def change_password(user_id: uuid.UUID, current: str, new: str) -> dict[str, Any]:
    """Rotate a signed-in user's password.

    Every other session for the account is revoked (a password change must log out
    anyone holding a stolen cookie), and the caller gets a fresh session of its own so
    the person who just changed the password is not signed out of the tab they did it
    in — they would otherwise have to re-enter the new password immediately.
    """
    _validate_password(new)
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    async with factory() as session:
        user = await session.get(User, user_id)
        if user is None or not verify_portal_password(user.password_hash, current):
            raise ValueError("invalid_credentials")
        user.password_hash = hash_portal_password(new)
        user.updated_at = _utcnow()
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=_utcnow())
        )
        await _log_event(session, "password_change", user_id=user.user_id)
        session_payload = await _reissue_session(session, user)
        await session.commit()
    await _seed_admin_wallet(session_payload["tenant"]["tenantId"], user.user_id, user.email)
    return session_payload


async def _reissue_session(session: AsyncSession, user: User) -> dict[str, Any]:
    """Fresh access + refresh for a user who has just proved who they are."""
    picked = await resolve_usable_tenant(session, user.user_id)
    if picked is None:
        raise ValueError("tenant_inactive")
    membership, tenant = picked
    role = _role_for_user(user.email, membership.role)
    if membership.role != role:
        membership.role = role
    tokens = await _issue_tokens(session, user, membership.tenant_id, role)
    onboarded = await check_user_completed_onboarding(session, user.user_id)
    return {**tokens, **_session_public(user, tenant, role, has_completed_onboarding=onboarded)}


async def forgot_password(email: str) -> str | None:
    """Returns raw reset token if user exists (caller sends email); else None."""
    factory = get_session_factory()
    if factory is None:
        return None
    norm = _normalize_email(email)
    async with factory() as session:
        result = await session.execute(
            select(User).where(func.lower(User.email) == norm, User.deleted_at.is_(None))
        )
        user = result.scalar_one_or_none()
        if user is None:
            return None
        raw = secrets.token_urlsafe(32)
        session.add(
            PasswordResetToken(
                token_hash=_hash_token(raw),
                user_id=user.user_id,
                expires_at=_utcnow() + timedelta(hours=1),
                created_at=_utcnow(),
            )
        )
        await session.commit()
        return raw


async def reset_password(token: str, new_password: str) -> dict[str, Any]:
    _validate_password(new_password)
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    th = _hash_token(token)
    async with factory() as session:
        result = await session.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == th,
                PasswordResetToken.expires_at > _utcnow(),
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise ValueError("invalid_token")
        user = await session.get(User, row.user_id)
        if user is None:
            raise ValueError("invalid_token")
        user.password_hash = hash_portal_password(new_password)
        user.updated_at = _utcnow()
        await session.delete(row)
        # Everything else on the account is signed out — the reset link may have been
        # forwarded, and the old password is no longer trustworthy.
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=_utcnow())
        )
        await _log_event(session, "password_reset", user_id=user.user_id)
        # Holding a valid single-use reset token *is* proof of identity — the email
        # owner clicked it. Returning a session here means the reset lands the person
        # straight in their console instead of making them retype the new password.
        session_payload = await _reissue_session(session, user)
        await session.commit()
    await _seed_admin_wallet(session_payload["tenant"]["tenantId"], user.user_id, user.email)
    return session_payload


async def switch_tenant(user_id: uuid.UUID, tenant_id: uuid.UUID) -> dict[str, Any]:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    async with factory() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise ValueError("not_found")
        mem = await session.execute(
            select(TenantMembership).where(
                TenantMembership.user_id == user_id,
                TenantMembership.tenant_id == tenant_id,
            )
        )
        membership = mem.scalar_one_or_none()
        if membership is None:
            raise ValueError("not_found")
        tenant = await assert_tenant_active_simple(session, tenant_id)
        tokens = await _issue_tokens(session, user, tenant.tenant_id, membership.role)
        await session.commit()
        return {**tokens, "tenant": _tenant_public(tenant), "role": membership.role}


async def assert_tenant_active_simple(session: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None or tenant.deleted_at is not None:
        raise ValueError("not_found")
    if tenant.status in ("suspended", "deleted", "pending_deletion", "cancelled"):
        raise ValueError("tenant_inactive")
    return tenant


async def delete_account(user_id: uuid.UUID, password: str, confirm: str) -> None:
    if confirm != "DELETE":
        raise ValueError("confirm_required")
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    async with factory() as session:
        user = await session.get(User, user_id)
        if user is None or not verify_portal_password(user.password_hash, password):
            raise ValueError("invalid_credentials")
        admin_rows = await session.execute(
            select(TenantMembership).where(
                TenantMembership.user_id == user_id,
                TenantMembership.role == ROLE_CUSTOMER_ADMIN,
            )
        )
        for membership in admin_rows.scalars():
            others = await session.execute(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == membership.tenant_id,
                    TenantMembership.user_id != user_id,
                    TenantMembership.role == ROLE_CUSTOMER_ADMIN,
                )
            )
            if others.scalar_one_or_none() is None:
                nums = await session.execute(
                    select(PhoneNumber).where(
                        PhoneNumber.tenant_id == membership.tenant_id,
                        PhoneNumber.released_at.is_(None),
                    )
                )
                if nums.first() is not None:
                    raise ValueError("sole_admin_with_numbers")
        user.status = "disabled"
        user.deleted_at = _utcnow()
        user.email = f"deleted+{user.user_id}@invalid.local"
        user.full_name = "Deleted User"
        await session.execute(delete(TenantMembership).where(TenantMembership.user_id == user_id))
        await _log_event(session, "account_deleted", user_id=user_id)
        await session.commit()
    await logout_all(user_id)


async def delete_tenant(tenant_id: uuid.UUID, user_id: uuid.UUID) -> uuid.UUID:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    async with factory() as session:
        mem = await session.execute(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id == user_id,
                TenantMembership.role == ROLE_CUSTOMER_ADMIN,
            )
        )
        if mem.scalar_one_or_none() is None:
            raise ValueError("forbidden")
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise ValueError("not_found")
        tenant.status = "pending_deletion"
        tenant.deleted_at = _utcnow()
        job = TenantTeardownJob(tenant_id=tenant_id, status="queued", created_at=_utcnow(), updated_at=_utcnow())
        session.add(job)
        await _log_event(session, "tenant_delete_requested", user_id=user_id, tenant_id=tenant_id)
        await session.commit()
        return job.job_id


async def invite_member(
    tenant_id: uuid.UUID,
    inviter_id: uuid.UUID,
    *,
    email: str,
    role: str,
) -> dict[str, Any]:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    norm = _normalize_email(email)
    async with factory() as session:
        inviter = await session.execute(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id == inviter_id,
                TenantMembership.role == ROLE_CUSTOMER_ADMIN,
            )
        )
        if inviter.scalar_one_or_none() is None:
            raise ValueError("forbidden")
        result = await session.execute(select(User).where(func.lower(User.email) == norm, User.deleted_at.is_(None)))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                email=norm,
                password_hash=hash_portal_password(secrets.token_urlsafe(16)),
                full_name="",
                status="pending_invite",
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
            session.add(user)
            await session.flush()
        existing = await session.execute(
            select(TenantMembership).where(
                TenantMembership.user_id == user.user_id,
                TenantMembership.tenant_id == tenant_id,
            )
        )
        if existing.scalar_one_or_none() is None:
            session.add(
                TenantMembership(
                    user_id=user.user_id,
                    tenant_id=tenant_id,
                    role=role,
                    invited_by=inviter_id,
                    created_at=_utcnow(),
                )
            )
        await session.commit()
        return {"ok": True, "userId": str(user.user_id)}


async def leave_tenant(user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    async with factory() as session:
        mem = await session.execute(
            select(TenantMembership).where(
                TenantMembership.user_id == user_id,
                TenantMembership.tenant_id == tenant_id,
            )
        )
        membership = mem.scalar_one_or_none()
        if membership is None:
            raise ValueError("not_found")
        if membership.role == ROLE_CUSTOMER_ADMIN:
            others = await session.execute(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == tenant_id,
                    TenantMembership.role == ROLE_CUSTOMER_ADMIN,
                    TenantMembership.user_id != user_id,
                )
            )
            if others.scalar_one_or_none() is None:
                raise ValueError("sole_admin")
        await session.execute(
            delete(TenantMembership).where(
                TenantMembership.user_id == user_id,
                TenantMembership.tenant_id == tenant_id,
            )
        )
        await _log_event(session, "tenant_leave", user_id=user_id, tenant_id=tenant_id)
        await session.commit()


async def transfer_ownership(tenant_id: uuid.UUID, admin_id: uuid.UUID, new_admin_id: uuid.UUID) -> None:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    async with factory() as session:
        current = await session.execute(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id == admin_id,
                TenantMembership.role == ROLE_CUSTOMER_ADMIN,
            )
        )
        if current.scalar_one_or_none() is None:
            raise ValueError("forbidden")
        target = await session.execute(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id == new_admin_id,
            )
        )
        new_mem = target.scalar_one_or_none()
        if new_mem is None:
            raise ValueError("not_found")
        new_mem.role = ROLE_CUSTOMER_ADMIN
        cur_row = (
            await session.execute(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == tenant_id,
                    TenantMembership.user_id == admin_id,
                )
            )
        ).scalar_one()
        cur_row.role = "voice_engineer"
        await _log_event(session, "ownership_transfer", user_id=admin_id, tenant_id=tenant_id)
        await session.commit()


async def remove_member(tenant_id: uuid.UUID, admin_id: uuid.UUID, member_user_id: uuid.UUID) -> None:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    async with factory() as session:
        admin = await session.execute(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id == admin_id,
                TenantMembership.role == ROLE_CUSTOMER_ADMIN,
            )
        )
        if admin.scalar_one_or_none() is None:
            raise ValueError("forbidden")
        await session.execute(
            delete(TenantMembership).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id == member_user_id,
            )
        )
        await session.commit()


async def verify_email_otp(email: str, otp: str, *, ip: str | None = None) -> dict[str, Any]:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    norm = _normalize_email(email)
    code = (otp or "").strip()
    if not code.isdigit() or len(code) != 6:
        raise ValueError("invalid_otp")
    otp_h = _hash_token(code)
    async with factory() as session:
        result = await session.execute(
            select(User).where(func.lower(User.email) == norm, User.deleted_at.is_(None))
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise ValueError("invalid_otp")
        tok = await session.execute(
            select(EmailVerificationToken).where(
                EmailVerificationToken.user_id == user.user_id,
                EmailVerificationToken.otp_hash == otp_h,
                EmailVerificationToken.expires_at > _utcnow(),
                EmailVerificationToken.used_at.is_(None),
            )
        )
        row = tok.scalar_one_or_none()
        if row is None:
            raise ValueError("invalid_otp")
        row.used_at = _utcnow()
        user.email_verified_at = _utcnow()
        user.status = "active"
        user.updated_at = _utcnow()
        mem = await session.execute(
            select(TenantMembership, Tenant)
            .join(Tenant, Tenant.tenant_id == TenantMembership.tenant_id)
            .where(TenantMembership.user_id == user.user_id)
            .order_by(TenantMembership.created_at)
        )
        mem_row = mem.first()
        if mem_row is None:
            raise ValueError("no_tenant")
        membership, tenant = mem_row
        role = _role_for_user(user.email, membership.role)
        if membership.role != role:
            membership.role = role
        await _log_event(session, "email_verified_otp", user_id=user.user_id, tenant_id=tenant.tenant_id, ip=ip)
        tokens = await _issue_tokens(session, user, tenant.tenant_id, role)
        onboarded = await check_user_completed_onboarding(session, user.user_id)
        await session.commit()
        await _seed_admin_wallet(tenant.tenant_id, user.user_id, user.email)
        return {**tokens, **_session_public(user, tenant, role, has_completed_onboarding=onboarded)}


async def verify_email_token(token: str) -> None:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    th = _hash_token(token.strip())
    async with factory() as session:
        result = await session.execute(
            select(EmailVerificationToken).where(
                EmailVerificationToken.token_hash == th,
                EmailVerificationToken.expires_at > _utcnow(),
                EmailVerificationToken.used_at.is_(None),
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise ValueError("invalid_token")
        user = await session.get(User, row.user_id)
        if user is None or user.deleted_at is not None:
            raise ValueError("invalid_token")
        row.used_at = _utcnow()
        user.email_verified_at = _utcnow()
        user.status = "active"
        user.updated_at = _utcnow()
        await session.commit()


async def resend_verification_email(email: str, *, expose_debug_otp: bool = False) -> dict[str, Any]:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    norm = _normalize_email(email)
    async with factory() as session:
        result = await session.execute(
            select(User).where(func.lower(User.email) == norm, User.deleted_at.is_(None))
        )
        user = result.scalar_one_or_none()
        if user is None or user.email_verified_at is not None:
            return {}
        verify_raw, otp = await _create_email_verification_token(session, user.user_id)
        await session.commit()
    settings = get_settings()
    verify_url = f"{settings.voxly_frontend_url.rstrip('/')}/#verify-email?token={verify_raw}"
    delivery = await send_verification_email(norm, verify_url, otp)
    if not delivery.ok:
        logger.error(
            "resent verification email not delivered to %s: code=%s status=%s detail=%s",
            norm,
            delivery.code,
            delivery.provider_status,
            delivery.detail,
        )
    return {"debugOtp": otp} if (expose_debug_otp and not delivery.ok) else {}
