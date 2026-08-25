"""Pytest defaults — no live Postgres unless LIVE_DB=1."""
from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def _isolate_test_database():
    if os.getenv("LIVE_DB", "").strip().lower() in ("1", "true", "yes"):
        yield
        return
    os.environ.pop("DATABASE_URL", None)
    try:
        from server.config.env import get_settings

        get_settings.cache_clear()
        from server.db import connection

        connection._engine = None
        connection._session_factory = None
        from server.db.tier_store import clear_tier_cache_for_tests

        clear_tier_cache_for_tests()
    except Exception:
        pass
    yield
    try:
        from server.config.env import get_settings

        get_settings.cache_clear()
    except Exception:
        pass
