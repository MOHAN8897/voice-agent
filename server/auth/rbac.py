"""RBAC role matrix — server/auth/rbac.py"""
from __future__ import annotations

from typing import FrozenSet

ROLE_ADMINISTRATOR = "administrator"
ROLE_DEVELOPER = "developer"
ROLE_PLATFORM_ADMIN = "platform_admin"
ROLE_CUSTOMER_ADMIN = "customer_admin"
ROLE_VOICE_ENGINEER = "voice_engineer"
ROLE_CUSTOMER_VIEWER = "customer_viewer"

DEV_ROLES = frozenset({ROLE_ADMINISTRATOR, ROLE_DEVELOPER, ROLE_PLATFORM_ADMIN})
APP_WRITE_ROLES = frozenset({ROLE_ADMINISTRATOR, ROLE_DEVELOPER, ROLE_CUSTOMER_ADMIN, ROLE_PLATFORM_ADMIN})
APP_READ_ROLES = frozenset(
    {
        ROLE_ADMINISTRATOR,
        ROLE_DEVELOPER,
        ROLE_PLATFORM_ADMIN,
        ROLE_CUSTOMER_ADMIN,
        ROLE_VOICE_ENGINEER,
        ROLE_CUSTOMER_VIEWER,
    }
)

_CUSTOMER_WRITE = frozenset({ROLE_CUSTOMER_ADMIN, ROLE_PLATFORM_ADMIN, ROLE_ADMINISTRATOR})
_VOICE_WRITE = frozenset({ROLE_CUSTOMER_ADMIN, ROLE_VOICE_ENGINEER, ROLE_PLATFORM_ADMIN, ROLE_ADMINISTRATOR})

_PERMISSIONS: dict[str, FrozenSet[str]] = {
    "dev.stack.read": DEV_ROLES,
    "dev.stack.write": DEV_ROLES,
    "dev.promote": DEV_ROLES,
    "dev.platform_brain": frozenset({ROLE_ADMINISTRATOR, ROLE_DEVELOPER, ROLE_PLATFORM_ADMIN}),
    "dev.admin.users": frozenset({ROLE_ADMINISTRATOR, ROLE_DEVELOPER, ROLE_PLATFORM_ADMIN}),
    "dev.admin.tenants": frozenset({ROLE_ADMINISTRATOR, ROLE_DEVELOPER, ROLE_PLATFORM_ADMIN}),
    "dev.admin.numbers": frozenset({ROLE_ADMINISTRATOR, ROLE_DEVELOPER, ROLE_PLATFORM_ADMIN}),
    "dev.admin.billing": frozenset({ROLE_ADMINISTRATOR, ROLE_DEVELOPER, ROLE_PLATFORM_ADMIN}),
    "app.brain.write": _CUSTOMER_WRITE | frozenset({ROLE_VOICE_ENGINEER}),
    "app.agents.write": _VOICE_WRITE,
    "app.telephony.write": _VOICE_WRITE,
    "app.billing.read": APP_READ_ROLES,
    "app.billing.write": _CUSTOMER_WRITE,
    "app.members.write": _CUSTOMER_WRITE,
    "app.calls.read": APP_READ_ROLES,
    "app.test_studio": frozenset({ROLE_VOICE_ENGINEER, ROLE_DEVELOPER, ROLE_ADMINISTRATOR, ROLE_PLATFORM_ADMIN}),
    "app.campaigns.write": frozenset({ROLE_CUSTOMER_ADMIN, ROLE_ADMINISTRATOR, ROLE_DEVELOPER}),
    "app.integrations": frozenset({ROLE_CUSTOMER_ADMIN, ROLE_ADMINISTRATOR, ROLE_DEVELOPER}),
}


def require_role_permission(role: str, permission: str) -> None:
    from fastapi import HTTPException

    if not role_has_permission(role, permission):
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "auth_error", "message": "Permission denied"}},
        )


def role_has_permission(role: str, permission: str) -> bool:
    allowed = _PERMISSIONS.get(permission)
    if allowed is None:
        return False
    return role in allowed
