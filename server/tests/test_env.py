import os
import importlib


def test_missing_keys_raises(monkeypatch):
    """
    Schema must require both keys. Deterministic regardless of whether a
    developer's local .env file exists: bypass env-file with _env_file=None.
    """
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    from pydantic import ValidationError
    import server.config.env as env_mod

    env_mod.get_settings.cache_clear()
    try:
        try:
            env_mod.Settings(_env_file=None)  # type: ignore[call-arg]
            raise AssertionError("should have raised ValidationError for missing keys")
        except ValidationError as e:
            assert "OPENAI_API_KEY" in str(e)
            assert "SARVAM_API_KEY" in str(e)
            safe = env_mod._safe_error_details(e)
            wrapped = f"AI service configuration is invalid. Check .env — see .env.example. Details: {safe}"
            assert "AI service configuration is invalid" in wrapped
    finally:
        env_mod.get_settings.cache_clear()


def test_config_presence_booleans(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    import server.config.env as env_mod
    env_mod.get_settings.cache_clear()
    presence = env_mod.config_presence()
    assert presence["OPENAI_API_KEY"] is True
    assert presence["SARVAM_API_KEY"] is True
    env_mod.get_settings.cache_clear()
