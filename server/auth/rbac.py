"""RBAC role matrix — server/auth/rbac.py"""
from __future__ import annotations

from typing import FrozenSet

ROLE_ADMINISTRATOR = "administrator"
ROLE_DEVELOPER = "developer"
ROLE_PLATFORM_ADMIN = "platform_admin"
ROLE_CUSTOMER_ADMIN = "customer_admin"
ROLE_VOICE_ENGINEER = "voice_engineer"
ROLE_CUSTOMER_VIEWER = "customer_viewer"
# Admin-portal roles held by stored platform-admin accounts (see admin_accounts).
ROLE_SUPER_ADMIN = "super_admin"
ROLE_SUPPORT_AGENT = "support_agent"
ROLE_BILLING_ADMIN = "billing_admin"
ROLE_STACK_ENGINEER = "stack_engineer"

#: The permission that lets an admin invite, change, suspend and remove other admins.
PERMISSION_MANAGE_ADMINS = "dev.admin.admins"

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
    "dev.admin.support": frozenset({ROLE_ADMINISTRATOR, ROLE_DEVELOPER, ROLE_PLATFORM_ADMIN}),
    "app.brain.write": _CUSTOMER_WRITE | frozenset({ROLE_VOICE_ENGINEER}),
    "app.agents.write": _VOICE_WRITE,
    "app.telephony.write": _VOICE_WRITE,
    "app.billing.read": APP_READ_ROLES,
    "app.billing.write": _CUSTOMER_WRITE,
    "app.members.write": _CUSTOMER_WRITE,
    "app.calls.read": APP_READ_ROLES,
    "app.test_studio": frozenset(
        {ROLE_VOICE_ENGINEER, ROLE_DEVELOPER, ROLE_ADMINISTRATOR, ROLE_PLATFORM_ADMIN, ROLE_CUSTOMER_ADMIN}
    ),
    "app.admin": frozenset({ROLE_PLATFORM_ADMIN, ROLE_ADMINISTRATOR}),
    "app.campaigns.write": frozenset(
        {ROLE_CUSTOMER_ADMIN, ROLE_ADMINISTRATOR, ROLE_DEVELOPER, ROLE_PLATFORM_ADMIN}
    ),
    "app.integrations": frozenset(
        {ROLE_CUSTOMER_ADMIN, ROLE_ADMINISTRATOR, ROLE_DEVELOPER, ROLE_PLATFORM_ADMIN}
    ),
}



def _grant_admin_portal_roles() -> None:
    """Fold the admin-portal roles into the matrix.

    `super_admin` holds everything the legacy all-powerful roles hold, plus the
    right to manage other admins. The narrower roles get only the dev areas their
    job needs, so a support agent cannot touch provider stacks or wallets.
    """
    for name, allowed in list(_PERMISSIONS.items()):
        if ROLE_ADMINISTRATOR in allowed or ROLE_DEVELOPER in allowed:
            _PERMISSIONS[name] = allowed | {ROLE_SUPER_ADMIN}
    narrow = {
        ROLE_SUPPORT_AGENT: ("dev.admin.support", "dev.admin.tenants", "dev.admin.users"),
        ROLE_BILLING_ADMIN: ("dev.admin.billing", "dev.admin.tenants"),
        ROLE_STACK_ENGINEER: ("dev.stack.read", "dev.stack.write", "dev.promote", "dev.platform_brain"),
    }
    for role, names in narrow.items():
        for name in names:
            _PERMISSIONS[name] = _PERMISSIONS[name] | {role}
    _PERMISSIONS[PERMISSION_MANAGE_ADMINS] = frozenset({ROLE_SUPER_ADMIN})


_grant_admin_portal_roles()


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
