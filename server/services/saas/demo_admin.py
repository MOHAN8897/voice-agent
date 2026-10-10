"""Demo/admin account provisioning.

The demo account is recognised by the *backend* — an env allowlist re-read on every
request in ``platform_admins`` — and every protected route then authorises through
the normal RBAC matrix using the role on the authenticated principal. No frontend
check, hidden flag, or client-supplied email is involved.

This module makes that account reproducible across dev/staging/demo: it creates the
user, verifies the address through the same field the normal flow sets, grants the
``platform_admin`` membership, and seeds wallet credits. It is idempotent.

Credentials are never stored in source. A password must be supplied via
``SAAS_DEMO_ADMIN_PASSWORD``; when it is absent the account is provisioned without
one and the operator is told to set it (or use Google sign-in).
"""
from __future__ import annotations

import os
import uuid
from typing import Any

from sqlalchemy import func, select

from server.auth.rbac import ROLE_PLATFORM_ADMIN
from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.entities import Tenant
from server.db.models.saas_models import TenantMembership, User
from server.services.saas.platform_admins import platform_admin_emails


class DemoAccountError(RuntimeError):
    """Raised when the demo account cannot be provisioned."""


def demo_admin_emails() -> list[str]:
    """Emails the backend treats as platform admins, lowercased and sorted."""
    return sorted(platform_admin_emails())


def _normalize(email: str) -> str:
    return str(email or "").strip().lower()


def _utcnow():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def _password_hash(password: str) -> str:
    from server.auth.passwords import hash_portal_password

    return hash_portal_password(password)


async def ensure_demo_admin(
    email: str,
    *,
    full_name: str = "Demo Admin",
    password: str | None = None,
    seed_credits: bool = True,
) -> dict[str, Any]:
    """Idempotently provision one platform-admin account.

    Returns a summary of what was created or left untouched. Raises
    :class:`DemoAccountError` when no database is configured.
    """
    norm = _normalize(email)
    if not norm or "@" not in norm:
        raise DemoAccountError("a valid email address is required")

    # Check the allowlist before touching the database: whether an address is
    # allowed is a configuration question, not a storage one.
    if norm not in platform_admin_emails():
        raise DemoAccountError(
            f"{norm} is not in SAAS_PLATFORM_ADMIN_EMAILS, so the backend will not grant it platform admin"
        )

    factory = get_session_factory()
    if factory is None:
        raise DemoAccountError("DATABASE_URL is required to provision the demo account")

    settings = get_settings()
    resolved_password = password if password is not None else (os.getenv("SAAS_DEMO_ADMIN_PASSWORD") or "")
    created_user = False
    created_membership = False
    set_password = False

    try:
        tenant_id = uuid.UUID(str(settings.default_tenant_id))
    except (ValueError, TypeError):
        tenant_id = uuid.uuid4()

    async with factory() as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            tenant = Tenant(
                tenant_id=tenant_id,
                name="Demo Workspace",
                plan="enterprise",
                status="active",
                limits={"max_concurrent_pstn": 20, "max_agents": 50},
            )
            session.add(tenant)
            await session.flush()

        result = await session.execute(select(User).where(func.lower(User.email) == norm))
        user = result.scalar_one_or_none()
        if user is None:
            # No usable password means the account is reachable via Google sign-in
            # only, which is a legitimate state for a demo identity.
            user = User(
                user_id=uuid.uuid4(),
                email=norm,
                password_hash=_password_hash(resolved_password) if resolved_password else "",
                full_name=full_name,
                status="active",
                email_verified_at=_utcnow(),
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
            session.add(user)
            await session.flush()
            created_user = True
        else:
            if user.deleted_at is not None or user.status != "active":
                user.deleted_at = None
                user.status = "active"
            # Verified through the same field the normal verification flow sets.
            if user.email_verified_at is None:
                user.email_verified_at = _utcnow()
            if resolved_password:
                user.password_hash = _password_hash(resolved_password)
                set_password = True

        membership = (
            await session.execute(
                select(TenantMembership).where(
                    TenantMembership.user_id == user.user_id,
                    TenantMembership.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            session.add(
                TenantMembership(
                    id=uuid.uuid4(),
                    user_id=user.user_id,
                    tenant_id=tenant_id,
                    role=ROLE_PLATFORM_ADMIN,
                    created_at=_utcnow(),
                )
            )
            created_membership = True
        elif membership.role != ROLE_PLATFORM_ADMIN:
            membership.role = ROLE_PLATFORM_ADMIN

        await session.commit()
        user_id = user.user_id

    seeded = False
    if seed_credits:
        try:
            from server.services.saas.billing_wallet_service import maybe_seed_admin_credits

            await maybe_seed_admin_credits(tenant_id, user_id, norm)
            seeded = True
        except Exception:
            seeded = False

    return {
        "email": norm,
        "userId": str(user_id),
        "tenantId": str(tenant_id),
        "role": ROLE_PLATFORM_ADMIN,
        "createdUser": created_user,
        "createdMembership": created_membership,
        "passwordSet": bool(resolved_password) and (created_user or set_password),
        "verified": True,
        "creditsSeeded": seeded,
        "hint": (
            None
            if resolved_password
            else "No password set. Set SAAS_DEMO_ADMIN_PASSWORD, or sign in with Google."
        ),
    }


async def ensure_all_demo_admins(*, password: str | None = None) -> list[dict[str, Any]]:
    """Provision every configured platform admin. Safe to run on every boot."""
    out: list[dict[str, Any]] = []
    for email in demo_admin_emails():
        try:
            out.append(await ensure_demo_admin(email, password=password))
        except DemoAccountError as exc:
            out.append({"email": email, "error": str(exc)})
    return out


async def describe_demo_admin(email: str) -> dict[str, Any]:
    """Report the stored role for an account without creating anything."""
    norm = _normalize(email)
    factory = get_session_factory()
    if factory is None:
        return {"email": norm, "exists": False, "reason": "no_database"}
    async with factory() as session:
        user = (
            await session.execute(select(User).where(func.lower(User.email) == norm))
        ).scalar_one_or_none()
        if user is None:
            return {"email": norm, "exists": False}
        rows = (
            await session.execute(
                select(TenantMembership).where(TenantMembership.user_id == user.user_id)
            )
        ).scalars()
        memberships = [
            {"tenantId": str(m.tenant_id), "role": m.role} for m in rows
        ]
    return {
        "email": norm,
        "exists": True,
        "userId": str(user.user_id),
        "verified": user.email_verified_at is not None,
        "status": user.status,
        "memberships": memberships,
        "isPlatformAdminByConfig": norm in platform_admin_emails(),
    }
