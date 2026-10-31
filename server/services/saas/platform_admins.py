"""Platform admin / dev-tester allowlists — env-backed, never hardcoded in UI."""
from __future__ import annotations

from fastapi import HTTPException

from server.auth.rbac import ROLE_CUSTOMER_ADMIN, ROLE_PLATFORM_ADMIN
from server.config.env import get_settings


def _parse_email_csv(raw: str) -> frozenset[str]:
    return frozenset(
        part.strip().lower()
        for part in (raw or "").split(",")
        if part.strip() and "@" in part
    )


def platform_admin_emails() -> frozenset[str]:
    settings = get_settings()
    return _parse_email_csv(settings.saas_platform_admin_emails)


def dev_tester_emails() -> frozenset[str]:
    settings = get_settings()
    emails = _parse_email_csv(settings.saas_dev_tester_emails)
    return emails | platform_admin_emails()


def is_platform_admin_email(email: str | None) -> bool:
    return bool(email) and str(email).strip().lower() in platform_admin_emails()


def is_dev_tester_email(email: str | None) -> bool:
    return bool(email) and str(email).strip().lower() in dev_tester_emails()


def effective_membership_role(email: str | None, stored_role: str | None) -> str:
    """Re-evaluate platform admin from env on every request. JWT role is not enough."""
    if is_platform_admin_email(email):
        return ROLE_PLATFORM_ADMIN
    role = (stored_role or ROLE_CUSTOMER_ADMIN).strip() or ROLE_CUSTOMER_ADMIN
    if role == ROLE_PLATFORM_ADMIN:
        return ROLE_CUSTOMER_ADMIN
    return role


def require_platform_admin_email(email: str | None) -> None:
    if not is_platform_admin_email(email):
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "auth_error", "message": "Platform admin required"}},
        )
