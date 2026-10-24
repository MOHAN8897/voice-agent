"""Deployment guard: never serve traffic from a database behind the code head."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, text

ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def expected_revisions() -> frozenset[str]:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "server/db/migrations"))
    return frozenset(ScriptDirectory.from_config(config).get_heads())


async def check_schema_revision() -> dict[str, Any]:
    """Compare alembic_version with the shipped migration heads.

    Returns a secret-free status dict usable by /api/health and startup logs.
    """
    from server.db.connection import get_engine

    expected = sorted(expected_revisions())
    engine = get_engine()
    if engine is None:
        return {
            "ok": True,
            "configured": False,
            "current": [],
            "expected": expected,
            "message": "skipped",
        }
    try:
        async with engine.connect() as conn:
            has_version = await conn.run_sync(lambda sync: inspect(sync).has_table("alembic_version"))
            rows = await conn.execute(text("SELECT version_num FROM alembic_version")) if has_version else None
            current = sorted(rows.scalars()) if rows is not None else []
    except Exception as exc:
        # Driver errors can embed the DSN; expose only the exception type.
        return {
            "ok": False,
            "configured": True,
            "current": [],
            "expected": expected,
            "message": f"schema check failed ({type(exc).__name__})",
        }
    ok = set(current) == set(expected)
    return {
        "ok": ok,
        "configured": True,
        "current": current,
        "expected": expected,
        "message": "ok" if ok else "pending migrations; run python -m scripts.migrate_db",
    }
