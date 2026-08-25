"""Verify PostgreSQL connectivity and migration state."""
from __future__ import annotations

import asyncio
import sys


async def _main() -> int:
    from server.config.env import get_settings
    from server.db.connection import check_db_health, close_db, init_db
    from server.db.seed import ensure_default_tenant

    settings = get_settings()
    if not settings.database_url:
        print("DATABASE_URL not set")
        return 1

    print(f"DATABASE_URL configured: {settings.database_url.split('@')[-1]}")

    if not await init_db():
        print("init_db failed")
        return 1

    health = await check_db_health()
    print("Health:", health)

    if not health.get("ok"):
        await close_db()
        return 1

    agent_id = await ensure_default_tenant()
    print(f"Default tenant seeded, agent_id={agent_id}")

    from sqlalchemy import text
    from server.db.connection import get_engine

    engine = get_engine()
    if engine is None:
        print("No engine")
        return 1

    async with engine.connect() as conn:
        rev = await conn.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
        tables = await conn.scalar(
            text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
        )
    print(f"Alembic revision: {rev}")
    print(f"Public tables: {tables}")

    await close_db()
    print("PostgreSQL integration OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
