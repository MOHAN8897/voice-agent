"""Verify PostgreSQL connectivity and migration state."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

ROOT = Path(__file__).resolve().parents[1]


def _expected_heads() -> set[str]:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "server/db/migrations"))
    return set(ScriptDirectory.from_config(config).get_heads())


async def _migration_state(conn, expected: set[str]) -> tuple[bool, set[str]]:
    has_version = await conn.run_sync(lambda sync: inspect(sync).has_table("alembic_version"))
    current = set((await conn.execute(text("SELECT version_num FROM alembic_version"))).scalars()) if has_version else set()
    return current == expected, current


async def _main() -> int:
    from server.config.env import get_settings
    from server.db.connection import close_db, get_engine, init_db

    settings = get_settings()
    if not settings.database_url:
        print("DATABASE_URL not set")
        return 1

    try:
        if not await init_db():
            print("Database initialization failed")
            return 1
        engine = get_engine()
        if engine is None:
            print("Database initialization failed")
            return 1
        expected = _expected_heads()
        async with engine.connect() as conn:
            # This diagnostic must not seed records or change the schema.
            async with conn.begin():
                await conn.execute(text("SET TRANSACTION READ ONLY"))
                ready, current = await _migration_state(conn, expected)
        print("PostgreSQL connectivity OK")
        print("Alembic revision:", ", ".join(sorted(current)) or "not initialized")
        print("Required revision:", ", ".join(sorted(expected)))
        if not ready:
            print("Schema mismatch. Review pending migrations, then run: python -m scripts.migrate_db")
            return 1
        print("PostgreSQL integration OK (read-only check)")
        return 0
    except Exception as exc:
        # Driver exceptions can contain credentials or customer query parameters.
        print(f"PostgreSQL verification failed ({type(exc).__name__})", file=sys.stderr)
        return 1
    finally:
        await close_db()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
