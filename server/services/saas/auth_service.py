"""Subscriber signup, login, refresh, password, account lifecycle."""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.jwt_tokens import AccessTokenClaims, create_access_token
from server.auth.passwords import hash_portal_password, verify_portal_password
from server.auth.rbac import ROLE_CUSTOMER_ADMIN
from server.config.env import get_settings
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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
) -> dict[str, Any]:
    claims = AccessTokenClaims(
        user_id=str(user.user_id),
        tenant_id=str(tenant_id),
        role=role,
        email=user.email,
    )
    access, expires_in = create_access_token(claims)
    raw_refresh = secrets.token_urlsafe(48)
    family_id = uuid.uuid4()
    settings = get_settings()
    session.add(
        RefreshToken(
            user_id=user.user_id,
            token_hash=_hash_token(raw_refresh),
            family_id=family_id,
            expires_at=_utcnow() + timedelta(days=settings.jwt_refresh_ttl_days),
            created_at=_utcnow(),
        )
    )
    return {
        "accessToken": access,
        "refreshToken": raw_refresh,
        "expiresIn": expires_in,
    }


def _user_public(user: User) -> dict[str, Any]:
    return {
        "userId": str(user.user_id),
        "email": user.email,
        "fullName": user.full_name,
        "status": user.status,
        "emailVerified": user.email_verified_at is not None,
    }


def _tenant_public(tenant: Tenant) -> dict[str, Any]:
    return {
        "tenantId": str(tenant.tenant_id),
        "name": tenant.name,
        "plan": tenant.plan,
        "status": tenant.status,
        "limits": tenant.limits or {},
    }


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
                limits={"max_concurrent_pstn": 3, "max_agents": 20},
                billing_source="self_serve",
                created_at=_utcnow(),
            )
            session.add(tenant)
            await session.flush()
            session.add(
                TenantMembership(
                    user_id=user.user_id,
                    tenant_id=tenant.tenant_id,
                    role=ROLE_CUSTOMER_ADMIN,
                    created_at=_utcnow(),
                )
            )
            await _log_event(session, f"signup_{provider}", user_id=user.user_id, tenant_id=tenant.tenant_id)
            tokens = await _issue_tokens(session, user, tenant.tenant_id, ROLE_CUSTOMER_ADMIN)
            await session.commit()
            return {
                **tokens,
                "user": _user_public(user),
                "tenant": _tenant_public(tenant),
            }
        mem = await session.execute(
            select(TenantMembership, Tenant)
            .join(Tenant, Tenant.tenant_id == TenantMembership.tenant_id)
            .where(TenantMembership.user_id == user.user_id)
            .limit(1)
        )
        row = mem.first()
        if row is None:
            raise ValueError("no_tenant")
        membership, tenant = row
        if user.email_verified_at is None:
            user.email_verified_at = _utcnow()
        tokens = await _issue_tokens(session, user, tenant.tenant_id, membership.role)
        await _log_event(session, f"login_{provider}", user_id=user.user_id, tenant_id=tenant.tenant_id)
        await session.commit()
        return {**tokens, "user": _user_public(user), "tenant": _tenant_public(tenant)}


async def _create_email_verification_token(session: AsyncSession, user_id: uuid.UUID) -> str:
    raw = secrets.token_urlsafe(32)
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
            expires_at=_utcnow() + timedelta(hours=24),
            created_at=_utcnow(),
        )
    )
    return raw


async def signup(
    *,
    email: str,
    password: str,
    full_name: str,
    org_name: str,
    ip: str | None = None,
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
            limits={"max_concurrent_pstn": 3, "max_agents": 20},
            billing_source="self_serve",
            created_at=_utcnow(),
        )
        session.add(tenant)
        await session.flush()
        session.add(
            TenantMembership(
                user_id=user.user_id,
                tenant_id=tenant.tenant_id,
                role=ROLE_CUSTOMER_ADMIN,
                created_at=_utcnow(),
            )
        )
        await _log_event(session, "signup", user_id=user.user_id, tenant_id=tenant.tenant_id, ip=ip)
        verify_raw = await _create_email_verification_token(session, user.user_id)
        user_out = _user_public(user)
        tenant_out = _tenant_public(tenant)
        await session.commit()
    settings = get_settings()
    base = settings.voxly_frontend_url.rstrip("/")
    verify_url = f"{base}/#verify-email?token={verify_raw}"
    await send_verification_email(norm, verify_url)
    return {
        "ok": True,
        "requiresEmailVerification": True,
        "message": "If signup succeeded, check your email to verify your account.",
        "user": user_out,
        "tenant": tenant_out,
    }


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
        if settings.saas_require_email_verification_for_login and user.email_verified_at is None:
            raise ValueError("email_unverified")
        if user.status == "disabled":
            raise ValueError("account_disabled")
        if user.status == "pending_verification" and user.email_verified_at is None:
            raise ValueError("invalid_credentials")
        mem = await session.execute(
            select(TenantMembership, Tenant)
            .join(Tenant, Tenant.tenant_id == TenantMembership.tenant_id)
            .where(TenantMembership.user_id == user.user_id)
            .order_by(TenantMembership.created_at)
        )
        row = mem.first()
        if row is None:
            raise ValueError("no_tenant")
        membership, tenant = row
        if tenant.status in ("suspended", "deleted", "pending_deletion"):
            raise ValueError("tenant_inactive")
        await _log_event(
            session,
            "login",
            user_id=user.user_id,
            tenant_id=tenant.tenant_id,
            ip=ip,
        )
        tokens = await _issue_tokens(session, user, tenant.tenant_id, membership.role)
        await session.commit()
        return {
            **tokens,
            "user": _user_public(user),
            "tenant": _tenant_public(tenant),
            "role": membership.role,
        }


async def refresh(refresh_token: str) -> dict[str, Any]:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    th = _hash_token(refresh_token)
    async with factory() as session:
        result = await session.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == th,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > _utcnow(),
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise ValueError("invalid_refresh")
        user = await session.get(User, row.user_id)
        if user is None or user.deleted_at is not None or user.status == "disabled":
            raise ValueError("invalid_refresh")
        row.revoked_at = _utcnow()
        mem = await session.execute(
            select(TenantMembership).where(TenantMembership.user_id == user.user_id).limit(1)
        )
        membership = mem.scalar_one_or_none()
        if membership is None:
            raise ValueError("no_tenant")
        tenant = await session.get(Tenant, membership.tenant_id)
        if tenant is None or tenant.status in ("suspended", "deleted"):
            raise ValueError("tenant_inactive")
        tokens = await _issue_tokens(session, user, membership.tenant_id, membership.role)
        await session.commit()
        return {**tokens, "user": _user_public(user), "tenant": _tenant_public(tenant)}


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


async def get_me(principal_user_id: uuid.UUID, principal_tenant_id: uuid.UUID) -> dict[str, Any]:
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
        return {
            "user": _user_public(user),
            "tenant": _tenant_public(tenant),
            "role": current.role if current else None,
            "memberships": mems,
        }


async def change_password(user_id: uuid.UUID, current: str, new: str) -> None:
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
        await _log_event(session, "password_change", user_id=user.user_id)
        await session.commit()
    await logout_all(user_id)


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


async def reset_password(token: str, new_password: str) -> None:
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
        await session.commit()
    await logout_all(user.user_id)


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
    if tenant.status in ("suspended", "deleted", "pending_deletion"):
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


async def resend_verification_email(email: str) -> None:
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
            return
        verify_raw = await _create_email_verification_token(session, user.user_id)
        await session.commit()
    settings = get_settings()
    verify_url = f"{settings.voxly_frontend_url.rstrip('/')}/#verify-email?token={verify_raw}"
    await send_verification_email(norm, verify_url)
