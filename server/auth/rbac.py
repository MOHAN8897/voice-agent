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

_PERMISSIONS: dict[str, FrozenSet[str]] = {
    "dev.stack.read": DEV_ROLES,
    "dev.stack.write": DEV_ROLES,
    "dev.promote": DEV_ROLES,
    "dev.platform_brain": frozenset({ROLE_ADMINISTRATOR, ROLE_DEVELOPER, ROLE_PLATFORM_ADMIN}),
    "app.brain.write": frozenset({ROLE_CUSTOMER_ADMIN, ROLE_PLATFORM_ADMIN, ROLE_ADMINISTRATOR}),
    "app.calls.read": APP_READ_ROLES,
    "app.test_studio": frozenset({ROLE_VOICE_ENGINEER, ROLE_DEVELOPER, ROLE_ADMINISTRATOR, ROLE_PLATFORM_ADMIN}),
    "app.campaigns.write": frozenset({ROLE_CUSTOMER_ADMIN, ROLE_ADMINISTRATOR, ROLE_DEVELOPER}),
    "app.integrations": frozenset({ROLE_CUSTOMER_ADMIN, ROLE_ADMINISTRATOR, ROLE_DEVELOPER}),
}


def role_has_permission(role: str, permission: str) -> bool:
    allowed = _PERMISSIONS.get(permission)
    if allowed is None:
        return False
    return role in allowed
