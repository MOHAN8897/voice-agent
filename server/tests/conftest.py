"""Pytest defaults — no live Postgres unless LIVE_DB=1."""
from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def _isolate_test_database(tmp_path_factory):
    if os.getenv("LIVE_DB", "").strip().lower() in ("1", "true", "yes"):
        yield
        return
    # Deleting DATABASE_URL alone lets BaseSettings reload the developer's
    # live database from .env. Unit tests must supply their own configuration.
    from server.config.env import Settings, get_settings

    previous_env_file = Settings.model_config.get("env_file")
    previous_database_url = os.environ.pop("DATABASE_URL", None)
    previous_data_dir = os.environ.get("DATA_DIR")
    os.environ["DATA_DIR"] = str(tmp_path_factory.mktemp("voice-agent-unit-data"))
    test_secrets = {key: os.environ.get(key) for key in ("OPENAI_API_KEY", "SARVAM_API_KEY")}
    Settings.model_config["env_file"] = None
    for key in test_secrets:
        os.environ[key] = "unit-test-placeholder"
    try:
        from server.config.env import get_settings

        get_settings.cache_clear()
        from server.services.dev_secrets_store import dev_secrets_store

        dev_secrets_store.reload()
        from server.db import connection

        connection._engine = None
        connection._session_factory = None
        from server.db.tier_store import clear_tier_cache_for_tests

        clear_tier_cache_for_tests()
    except Exception:
        pass
    yield
    Settings.model_config["env_file"] = previous_env_file
    if previous_data_dir is None:
        os.environ.pop("DATA_DIR", None)
    else:
        os.environ["DATA_DIR"] = previous_data_dir
    if previous_database_url is not None:
        os.environ["DATABASE_URL"] = previous_database_url
    for key, value in test_secrets.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    try:
        from server.config.env import get_settings

        get_settings.cache_clear()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _stub_realtime_openai_ws(request):
    """Never open a live OpenAI Realtime socket from unit tests."""
    if os.getenv("LIVE_TEST", "").strip().lower() in ("1", "true", "yes"):
        yield
        return
    if request.node.get_closest_marker("live_realtime"):
        yield
        return
    from server.realtime.manager import realtime_text_manager
    from server.realtime.providers.openai import OpenAIRealtimeTextAdapter
    from server.realtime.testing import FakeRealtimeAdapter

    realtime_text_manager.reset_for_tests()
    realtime_text_manager._adapter_factory = FakeRealtimeAdapter
    yield
    realtime_text_manager.reset_for_tests()
    realtime_text_manager._adapter_factory = OpenAIRealtimeTextAdapter


@pytest.fixture(autouse=True)
def _isolate_request_limits():
    """Each test gets a fresh request window; rate-limit tests still enforce it."""
    from server.app import rate_limiter, tts_limiter

    rate_limiter.reset()
    tts_limiter.reset()
    yield
    rate_limiter.reset()
    tts_limiter.reset()
