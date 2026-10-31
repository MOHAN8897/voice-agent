"""Plain-language catalogue of admin-portal roles and permissions.

The *grants* live in `rbac._PERMISSIONS` and nowhere else; this module only adds
words to them so the Roles & access page can say what a role can see and do
without the UI carrying its own (drifting) copy of the matrix. A test asserts
that every permission in the matrix has a description here.

Roles are built in. The backend has no storage for custom roles, so the page
shows them read-only and says so.
"""
from __future__ import annotations

from typing import Any

from server.auth import rbac

#: Areas, in the order the page shows them.
AREAS: list[tuple[str, str]] = [
    ("accounts", "Accounts"),
    ("billing", "Billing, rates & payments"),
    ("numbers", "Phone numbers"),
    ("support", "Support & delivery"),
    ("voice", "Voice stacks & releases"),
    ("admins", "Admin team"),
    ("console", "Business console (inside a workspace)"),
]

PERMISSION_INFO: dict[str, dict[str, str]] = {
    "dev.admin.tenants": {
        "area": "accounts",
        "label": "Workspaces and the admin overview",
        "detail": "See and change every workspace: status, plan, limits, members; the overview dashboard and analytics.",
    },
    "dev.admin.users": {
        "area": "accounts",
        "label": "Customer users",
        "detail": "See customer users, change their status and workspace roles, send password resets, and delete users.",
    },
    "dev.admin.billing": {
        "area": "billing",
        "label": "Wallets, rates, payments and activity log",
        "detail": "Wallet balances and credits, call rates, number purchases, refunds, payment settings, and the platform activity log.",
    },
    "dev.admin.numbers": {
        "area": "numbers",
        "label": "Number pool and assignments",
        "detail": "Allocate, park, release and reassign phone numbers across workspaces.",
    },
    "dev.admin.support": {
        "area": "support",
        "label": "Support tickets and delivery",
        "detail": "Read and answer customer support requests and check email delivery.",
    },
    "dev.stack.read": {
        "area": "voice",
        "label": "View voice stacks",
        "detail": "See provider stacks, tiers, voices and their configuration.",
    },
    "dev.stack.write": {
        "area": "voice",
        "label": "Change voice stacks",
        "detail": "Edit provider stacks, tiers, voices and telephony settings.",
    },
    "dev.promote": {
        "area": "voice",
        "label": "Release to production",
        "detail": "Promote a tested configuration to live customer calls.",
    },
    "dev.platform_brain": {
        "area": "voice",
        "label": "Platform brain and Test Studio",
        "detail": "Edit platform-wide agent instructions and place test calls from Test Studio.",
    },
    rbac.PERMISSION_MANAGE_ADMINS: {
        "area": "admins",
        "label": "Manage admins",
        "detail": "Invite admins, change their roles, suspend, sign out, reset passwords and remove them; read the admin-team audit trail.",
    },
    "app.admin": {
        "area": "console",
        "label": "Console admin tools",
        "detail": "Platform-admin tools inside the business console.",
    },
    "app.agents.write": {"area": "console", "label": "Agents", "detail": "Create and edit agents in a workspace."},
    "app.billing.read": {"area": "console", "label": "Workspace billing (view)", "detail": "See a workspace's billing."},
    "app.billing.write": {"area": "console", "label": "Workspace billing (change)", "detail": "Change a workspace's billing."},
    "app.brain.write": {"area": "console", "label": "Agent instructions", "detail": "Edit an agent's instructions."},
    "app.calls.read": {"area": "console", "label": "Calls", "detail": "Read call history and recordings."},
    "app.campaigns.write": {"area": "console", "label": "Campaigns and contacts", "detail": "Run campaigns and edit contacts."},
    "app.integrations": {"area": "console", "label": "Integrations", "detail": "Connect and configure integrations."},
    "app.members.write": {"area": "console", "label": "Workspace members", "detail": "Invite and change workspace members."},
    "app.telephony.write": {"area": "console", "label": "Telephony", "detail": "Change a workspace's telephony setup."},
    "app.test_studio": {"area": "console", "label": "Test calls", "detail": "Place test calls."},
}

#: Admin-portal roles, most to least powerful. `assignable` roles can be given to
#: stored accounts; the legacy ones exist for older sessions and integrations.
ADMIN_ROLES: list[dict[str, Any]] = [
    {
        "key": rbac.ROLE_SUPER_ADMIN,
        "label": "Super admin",
        "summary": "Everything, including inviting and removing other admins.",
        "assignable": True,
    },
    {
        "key": rbac.ROLE_ADMINISTRATOR,
        "label": "Administrator",
        "summary": "Runs the whole platform — accounts, billing, numbers, support and voice stacks — but cannot manage admins.",
        "assignable": True,
    },
    {
        "key": rbac.ROLE_SUPPORT_AGENT,
        "label": "Support",
        "summary": "Looks after customers: workspaces, users and support tickets. No billing, numbers or voice stacks.",
        "assignable": True,
    },
    {
        "key": rbac.ROLE_BILLING_ADMIN,
        "label": "Billing",
        "summary": "Wallets, rates, payments and the activity log, plus workspaces. No users, numbers or voice stacks.",
        "assignable": True,
    },
    {
        "key": rbac.ROLE_STACK_ENGINEER,
        "label": "Voice engineer",
        "summary": "Provider stacks, tiers, releases, platform brain and Test Studio. No customer accounts or money.",
        "assignable": True,
    },
    {
        "key": rbac.ROLE_DEVELOPER,
        "label": "Developer (legacy)",
        "summary": "Older sessions and API tokens. Same access as Administrator. Not assignable to new admins.",
        "assignable": False,
    },
    {
        "key": rbac.ROLE_PLATFORM_ADMIN,
        "label": "Platform admin (legacy)",
        "summary": "The console-side platform-admin role. Same portal access as Administrator. Not assignable here.",
        "assignable": False,
    },
]

ASSIGNABLE_ROLES = frozenset(r["key"] for r in ADMIN_ROLES if r["assignable"])
ROLE_LABELS = {r["key"]: r["label"] for r in ADMIN_ROLES}


def permissions_for_role(role: str) -> list[str]:
    return sorted(name for name, allowed in rbac._PERMISSIONS.items() if role in allowed)


def describe_roles() -> dict[str, Any]:
    """Roles with their permissions grouped by area, straight from the matrix."""
    area_labels = dict(AREAS)
    roles: list[dict[str, Any]] = []
    for meta in ADMIN_ROLES:
        granted = set(permissions_for_role(meta["key"]))
        groups = []
        for area, label in AREAS:
            perms = [
                {"name": name, "label": info["label"], "detail": info["detail"]}
                for name, info in PERMISSION_INFO.items()
                if info["area"] == area and name in granted
            ]
            if perms:
                groups.append({"area": area, "label": label, "permissions": perms})
        denied_areas = [
            area_labels[a]
            for a, _ in AREAS
            if a != "console"
            and not any(PERMISSION_INFO[n]["area"] == a for n in granted if n in PERMISSION_INFO)
        ]
        roles.append({**meta, "permissions": sorted(granted), "groups": groups, "cannot": denied_areas})
    permissions = [
        {
            "name": name,
            "area": PERMISSION_INFO.get(name, {}).get("area", "other"),
            "label": PERMISSION_INFO.get(name, {}).get("label", name),
            "detail": PERMISSION_INFO.get(name, {}).get("detail", ""),
            "roles": sorted(r for r in allowed if r in ROLE_LABELS),
        }
        for name, allowed in sorted(rbac._PERMISSIONS.items())
    ]
    return {
        "roles": roles,
        "areas": [{"key": k, "label": v} for k, v in AREAS],
        "permissions": permissions,
        "customRolesSupported": False,
    }
