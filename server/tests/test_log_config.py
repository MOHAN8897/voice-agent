"""Logging feature-flag tests."""
from server.utils.log_config import clear_log_flags_cache, get_log_flags, should_log


def test_log_flags_default_on(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-log")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test-log")
    monkeypatch.setenv("LOG_ENABLED", "true")
    from server.config.env import get_settings
    get_settings.cache_clear()
    clear_log_flags_cache()
    assert should_log("brain") is True
    assert should_log("ws") is True
    get_settings.cache_clear()
    clear_log_flags_cache()


def test_log_master_off(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-log")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test-log")
    monkeypatch.setenv("LOG_ENABLED", "false")
    from server.config.env import get_settings
    get_settings.cache_clear()
    clear_log_flags_cache()
    flags = get_log_flags()
    assert flags["enabled"] is False
    assert should_log("brain") is False
    get_settings.cache_clear()
    clear_log_flags_cache()


def test_log_category_off(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-log")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test-log")
    monkeypatch.setenv("LOG_ENABLED", "true")
    monkeypatch.setenv("LOG_WS", "false")
    from server.config.env import get_settings
    get_settings.cache_clear()
    clear_log_flags_cache()
    assert should_log("ws") is False
    assert should_log("brain") is True
    get_settings.cache_clear()
    clear_log_flags_cache()
