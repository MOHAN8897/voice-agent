"""
Bootstrap local PostgreSQL for voice-agent development.

Creates app user + database, runs Alembic migrations, and verifies connectivity.

Usage (from project root):
  python scripts/setup_postgres_dev.py
  python scripts/setup_postgres_dev.py --admin-password YOUR_POSTGRES_PASSWORD

Env (optional):
  POSTGRES_ADMIN_PASSWORD — postgres superuser password
  POSTGRES_ADMIN_USER     — defaults to postgres
  POSTGRES_APP_USER       — defaults to voice_agent
  POSTGRES_APP_PASSWORD   — defaults to voice_agent
  POSTGRES_DB             — defaults to voice_agent
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap local PostgreSQL for development")
    parser.add_argument(
        "--admin-password",
        default=os.getenv("POSTGRES_ADMIN_PASSWORD", "").strip(),
        help="PostgreSQL superuser password (or set POSTGRES_ADMIN_PASSWORD)",
    )
    parser.add_argument("--admin-user", default=os.getenv("POSTGRES_ADMIN_USER", "postgres"))
    parser.add_argument("--app-user", default=os.getenv("POSTGRES_APP_USER", "voice_agent"))
    parser.add_argument("--app-password", default=os.getenv("POSTGRES_APP_PASSWORD", "voice_agent"))
    parser.add_argument("--database", default=os.getenv("POSTGRES_DB", "voice_agent"))
    parser.add_argument("--skip-migrate", action="store_true")
    parser.add_argument("--skip-env-update", action="store_true")
    return parser.parse_args()


def _prompt_password() -> str:
    try:
        import getpass

        return getpass.getpass("PostgreSQL admin password (postgres user): ")
    except Exception:
        return input("PostgreSQL admin password (postgres user): ")


async def _bootstrap_db(
    admin_user: str,
    admin_password: str,
    app_user: str,
    app_password: str,
    database: str,
) -> None:
    import asyncpg

    admin_conn = await asyncpg.connect(
        host="localhost",
        port=5432,
        user=admin_user,
        password=admin_password,
        database="postgres",
    )

    user_exists = await admin_conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", app_user)
    if not user_exists:
        await admin_conn.execute(
            f"CREATE USER {app_user} WITH PASSWORD '{app_password.replace(chr(39), chr(39) + chr(39))}'"
        )
        print(f"Created user {app_user}")
    else:
        await admin_conn.execute(
            f"ALTER USER {app_user} WITH PASSWORD '{app_password.replace(chr(39), chr(39) + chr(39))}'"
        )
        print(f"User {app_user} already exists (password refreshed)")

    db_exists = await admin_conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", database)
    if not db_exists:
        await admin_conn.execute(f"CREATE DATABASE {database} OWNER {app_user}")
        print(f"Created database {database}")
    else:
        print(f"Database {database} already exists")

    await admin_conn.close()

    db_conn = await asyncpg.connect(
        host="localhost",
        port=5432,
        user=admin_user,
        password=admin_password,
        database=database,
    )
    await db_conn.execute(f"GRANT ALL ON SCHEMA public TO {app_user}")
    await db_conn.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {app_user}"
    )
    await db_conn.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO {app_user}"
    )
    await db_conn.close()


def _database_url(app_user: str, app_password: str, database: str) -> str:
    from urllib.parse import quote_plus

    return (
        f"postgresql://{quote_plus(app_user)}:{quote_plus(app_password)}@localhost:5432/{database}"
    )


def _update_env_file(database_url: str) -> None:
    if not ENV_FILE.exists():
        print(".env not found — set DATABASE_URL manually:")
        print(database_url)
        return

    text = ENV_FILE.read_text(encoding="utf-8")
    line = f"DATABASE_URL={database_url}"

    if re.search(r"^#?\s*DATABASE_URL=", text, flags=re.MULTILINE):
        text = re.sub(r"^#?\s*DATABASE_URL=.*$", line, text, count=1, flags=re.MULTILINE)
    else:
        text = text.rstrip() + "\n" + line + "\n"

    ENV_FILE.write_text(text, encoding="utf-8")
    print("Updated .env DATABASE_URL")


def _run_migrations(database_url: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    subprocess.check_call(
        [sys.executable, "-m", "alembic", "-c", str(ROOT / "alembic.ini"), "upgrade", "head"],
        cwd=ROOT,
        env=env,
    )
    print("Alembic migrations applied (head)")


async def _verify(database_url: str) -> None:
    os.environ["DATABASE_URL"] = database_url
    from server.config.env import get_settings

    get_settings.cache_clear()

    from server.db.connection import check_db_health, close_db, init_db

    if not await init_db():
        raise RuntimeError("init_db() returned False after migrations")
    health = await check_db_health()
    await close_db()
    if not health.get("ok"):
        raise RuntimeError(f"Database health check failed: {health}")
    print("Database health check OK")


def main() -> int:
    args = _parse_args()
    if not args.admin_password:
        args.admin_password = _prompt_password()
    if not args.admin_password:
        print("Admin password required.", file=sys.stderr)
        return 1

    database_url = _database_url(args.app_user, args.app_password, args.database)

    try:
        asyncio.run(
            _bootstrap_db(
                args.admin_user,
                args.admin_password,
                args.app_user,
                args.app_password,
                args.database,
            )
        )
    except Exception as e:
        print(f"Bootstrap failed: {e}", file=sys.stderr)
        print(
            "Tip: use the password you set when installing PostgreSQL 18, "
            "or reset it via pgAdmin.",
            file=sys.stderr,
        )
        return 1

    if not args.skip_migrate:
        try:
            _run_migrations(database_url)
        except subprocess.CalledProcessError as e:
            print(f"Migrations failed (exit {e.returncode})", file=sys.stderr)
            return e.returncode or 1

    if not args.skip_env_update:
        _update_env_file(database_url)

    os.environ["DATABASE_URL"] = database_url
    try:
        asyncio.run(_verify(database_url))
    except Exception as e:
        print(f"Verification failed: {e}", file=sys.stderr)
        return 1

    print("\nPostgreSQL is ready for development.")
    print(f"DATABASE_URL={database_url}")
    print("Start API: python -m uvicorn server.app:app --host 127.0.0.1 --port 8000")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
