"""Database connection health tests — Phase 1."""
from __future__ import annotations

import os

import pytest

from server.config.env import Settings
from server.db.connection import check_db_health, init_db
from server.db.migrations.versions import __init__ as _versions_pkg  # noqa: F401


@pytest.fixture
def settings_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    from server.config.env import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_db_not_configured(settings_env):
    status = await check_db_health()
    assert status["configured"] is False
    assert status["ok"] is False


@pytest.mark.asyncio
async def test_db_init_skipped_without_url(settings_env):
    connected = await init_db()
    assert connected is False


@pytest.mark.asyncio
async def test_sarvam_ws_model_from_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("SARVAM_STT_MODEL", "saaras:v3")
    from server.config.env import get_settings
    from server.services.sarvam_ws import _resolve_realtime_stt_model

    get_settings.cache_clear()
    assert _resolve_realtime_stt_model() == "saaras:v3-realtime"
    get_settings.cache_clear()


def test_alembic_revision_chain():
    import importlib.util
    from pathlib import Path

    versions = Path(__file__).resolve().parents[1] / "db" / "migrations" / "versions"
    p1 = versions / "001_phase1_initial.py"
    p2 = versions / "002_phase2_brains.py"
    p3 = versions / "003_phase3_calls.py"
    for path, rev, down in (
        (p1, "001_phase1", None),
        (p2, "002_phase2_brains", "001_phase1"),
        (p3, "003_phase3_calls", "002_phase2_brains"),
    ):
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.revision == rev
        assert mod.down_revision == down


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
async def test_db_health_when_configured():
    from server.config.env import get_settings

    get_settings.cache_clear()
    await init_db()
    status = await check_db_health()
    assert status["configured"] is True
    get_settings.cache_clear()

