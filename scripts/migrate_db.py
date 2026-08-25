"""Run Alembic migrations using DATABASE_URL from .env."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    from server.config.env import get_settings

    settings = get_settings()
    if not settings.database_url:
        print("DATABASE_URL is not set. Run scripts/setup_postgres_dev.py first.", file=sys.stderr)
        return 1

    env = dict(__import__("os").environ)
    env["DATABASE_URL"] = settings.database_url
    subprocess.check_call(
        [sys.executable, "-m", "alembic", "-c", str(ROOT / "alembic.ini"), "upgrade", "head"],
        cwd=ROOT,
        env=env,
    )
    print("Migrations applied (head)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
