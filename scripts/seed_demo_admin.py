"""Provision the backend platform-admin demo account.

Idempotent and safe to run on every environment.

    python -m scripts.seed_demo_admin
    python -m scripts.seed_demo_admin --describe

The password is read from ``SAAS_DEMO_ADMIN_PASSWORD`` (never from argv, so it does
not land in shell history or process listings). Without it the account is created
verified-but-passwordless, which means Google sign-in is the way in.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from server.services.saas.demo_admin import (
    DemoAccountError,
    describe_demo_admin,
    demo_admin_emails,
    ensure_all_demo_admins,
)


async def _run(describe_only: bool) -> int:
    emails = demo_admin_emails()
    if not emails:
        print("SAAS_PLATFORM_ADMIN_EMAILS is empty — nothing to provision.")
        return 1

    if describe_only:
        payload = [await describe_demo_admin(email) for email in emails]
        print(json.dumps(payload, indent=2))
        return 0

    results = await ensure_all_demo_admins()
    print(json.dumps(results, indent=2))
    return 0 if all("error" not in row for row in results) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the backend demo/platform-admin account.")
    parser.add_argument(
        "--describe",
        action="store_true",
        help="Print the stored role and memberships without changing anything.",
    )
    args = parser.parse_args()
    try:
        return asyncio.run(_run(args.describe))
    except DemoAccountError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
