"""
Async PostgreSQL connection — server/db/connection.py
Optional when DATABASE_URL is unset (local tests without Postgres).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from server.config.env import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _to_async_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def get_engine() -> AsyncEngine | None:
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession] | None:
    return _session_factory


async def init_db() -> bool:
    """Create engine + session factory. Returns True if DB configured and connected."""
    global _engine, _session_factory
    settings = get_settings()
    if not settings.database_url:
        return False
    url = _to_async_url(settings.database_url)
    _engine = create_async_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return True


async def close_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def check_db_health() -> dict[str, Any]:
    settings = get_settings()
    if not settings.database_url:
        return {"ok": False, "configured": False, "message": "DATABASE_URL not set"}
    if _engine is None:
        return {"ok": False, "configured": True, "message": "Database not initialized"}
    try:
        async with _engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"ok": True, "configured": True, "message": "connected"}
    except Exception as e:
        return {"ok": False, "configured": True, "message": str(e)[:200]}
