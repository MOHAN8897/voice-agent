"""Report the provisioning state of the configured platform-admin account.

Read-only. Tells you whether the account exists, is verified, holds the
platform_admin role, and whether a password is set (never prints any secret).
"""
from __future__ import annotations

import asyncio

from dotenv import load_dotenv
from sqlalchemy import func, select

load_dotenv()

from server.db.connection import get_session_factory, init_db  # noqa: E402
from server.db.models.saas_models import TenantMembership, User  # noqa: E402
from server.services.saas.demo_admin import demo_admin_emails  # noqa: E402


async def main() -> int:
    if not await init_db():
        print("DATABASE_URL is not configured")
        return 2
    factory = get_session_factory()
    assert factory is not None

    emails = demo_admin_emails()
    print("configured platform admins:", ", ".join(emails) or "(none)")
    if not emails:
        return 1

    async with factory() as session:
        for email in emails:
            user = (
                await session.execute(select(User).where(func.lower(User.email) == email))
            ).scalar_one_or_none()
            if user is None:
                print(f"\n{email}: NOT PROVISIONED — run scripts/seed_demo_admin.py")
                continue
            memberships = (
                await session.execute(
                    select(TenantMembership).where(TenantMembership.user_id == user.user_id)
                )
            ).scalars().all()
            print(f"\n{email}")
            print(f"  user id      {user.user_id}")
            print(f"  status       {user.status}")
            print(f"  verified     {user.email_verified_at is not None}")
            print(f"  password set {bool(user.password_hash)}")
            for m in memberships:
                print(f"  membership   tenant={m.tenant_id} role={m.role}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
