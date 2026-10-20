"""The database diagnostic must reject stale releases without changing data."""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from scripts import verify_postgres


@pytest.mark.asyncio
@pytest.mark.parametrize("revision,ready", [(None, False), ("039_native_billing_rates", False), ("future_unknown_revision", False), ("current", True)])
async def test_migration_check_requires_exact_release_head(revision, ready):
    expected = verify_postgres._expected_heads()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE TABLE sentinel (value TEXT)"))
            await conn.execute(text("INSERT INTO sentinel VALUES ('preserve')"))
            if revision:
                await conn.execute(text("CREATE TABLE alembic_version (version_num TEXT)"))
                for value in expected if revision == "current" else {revision}:
                    await conn.execute(text("INSERT INTO alembic_version VALUES (:revision)"), {"revision": value})
            result, current = await verify_postgres._migration_state(conn, expected)
            assert result is ready
            assert current == (expected if revision == "current" else {revision} if revision else set())
            assert await conn.scalar(text("SELECT value FROM sentinel")) == "preserve"
    finally:
        await engine.dispose()


def test_required_heads_resolve_outside_repository_working_directory(monkeypatch, tmp_path):
    expected = verify_postgres._expected_heads()
    monkeypatch.chdir(tmp_path)
    assert verify_postgres._expected_heads() == expected


@pytest.mark.asyncio
async def test_connection_failure_is_redacted_and_closed(monkeypatch, capsys):
    from server.db import connection

    closed = []

    async def broken_init():
        raise RuntimeError("postgresql://private-user:private-password@private-host/customer-db")

    async def close():
        closed.append(True)

    monkeypatch.setattr(connection, "init_db", broken_init)
    monkeypatch.setattr(connection, "close_db", close)
    monkeypatch.setattr("server.config.env.get_settings", lambda: type("Settings", (), {"database_url": "configured"})())
    assert await verify_postgres._main() == 1
    output = capsys.readouterr()
    assert "RuntimeError" in output.err
    assert "private-" not in output.out + output.err
    assert closed == [True]
