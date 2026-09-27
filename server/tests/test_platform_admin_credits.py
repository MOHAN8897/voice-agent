"""Platform admin allowlist, credits flags, browser realtime_voice, rate-limit headers."""
from __future__ import annotations

import uuid

from server.auth.rbac import ROLE_CUSTOMER_ADMIN, ROLE_PLATFORM_ADMIN, role_has_permission
from server.config.env import get_settings
from server.services.saas.platform_admins import (
    effective_membership_role,
    is_dev_tester_email,
    is_platform_admin_email,
)
from server.utils.rate_limiter import RateLimiter, raise_rate_limited


def test_platform_admin_from_env(monkeypatch):
    monkeypatch.setenv("SAAS_PLATFORM_ADMIN_EMAILS", "mohansaiteja.99@gmail.com, other@x.com")
    monkeypatch.setenv("SAAS_DEV_TESTER_EMAILS", "")
    get_settings.cache_clear()
    assert is_platform_admin_email("mohansaiteja.99@gmail.com")
    assert is_platform_admin_email("Other@x.com")
    assert not is_platform_admin_email("random@example.com")
    assert effective_membership_role("mohansaiteja.99@gmail.com", ROLE_CUSTOMER_ADMIN) == ROLE_PLATFORM_ADMIN
    assert effective_membership_role("random@example.com", ROLE_PLATFORM_ADMIN) == ROLE_CUSTOMER_ADMIN
    get_settings.cache_clear()


def test_dev_tester_includes_platform_admin(monkeypatch):
    monkeypatch.setenv("SAAS_PLATFORM_ADMIN_EMAILS", "mohansaiteja.99@gmail.com")
    monkeypatch.setenv("SAAS_DEV_TESTER_EMAILS", "qa@example.com")
    get_settings.cache_clear()
    assert is_dev_tester_email("qa@example.com")
    assert is_dev_tester_email("mohansaiteja.99@gmail.com")
    get_settings.cache_clear()


def test_customer_admin_can_use_test_studio():
    assert role_has_permission(ROLE_CUSTOMER_ADMIN, "app.test_studio")
    assert role_has_permission(ROLE_PLATFORM_ADMIN, "app.admin")
    assert not role_has_permission(ROLE_CUSTOMER_ADMIN, "app.admin")


def test_parse_assign_agent_id():
    from server.services.saas.number_purchase_service import parse_assign_agent_id

    assert parse_assign_agent_id(None) is None
    assert parse_assign_agent_id("") is None
    uid = uuid.uuid4()
    assert parse_assign_agent_id(str(uid)) == uid
    try:
        parse_assign_agent_id("not-a-uuid")
        assert False, "expected invalid_agent"
    except ValueError as exc:
        assert str(exc) == "invalid_agent"


def test_rate_limited_sets_retry_after():
    limiter = RateLimiter(max_requests=1, window_s=30)
    ok, _ = limiter.allow("k")
    assert ok
    denied, retry = limiter.allow("k")
    assert not denied
    assert retry >= 1
    try:
        raise_rate_limited(retry, "slow down")
    except Exception as exc:
        assert exc.status_code == 429
        assert exc.headers["Retry-After"] == str(retry)
        assert exc.detail["error"]["code"] == "rate_limit"


def test_browser_call_keeps_realtime_voice(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import server.app as app_mod
    from server.call.audio_archive import audio_archive
    from server.call.call_context import clear_all
    from server.call.call_ledger import call_ledger
    from server.call.call_store import call_store
    from server.call.memory_manager import memory_manager

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CALL_AUTO_END_ON_START", "true")
    monkeypatch.setenv("SAAS_AUTH_ENABLED", "false")
    get_settings.cache_clear()
    clear_all()
    call_ledger.reset_for_tests()
    audio_archive.reset_for_tests()
    call_store.reset_for_tests()
    memory_manager.reset_for_tests()
    client = TestClient(app_mod.app)
    started = client.post(
        "/api/call/start",
        json={
            "sessionId": f"web-{uuid.uuid4()}",
            "channel": "browser",
            "stackOverride": {"pipeline": "realtime_voice"},
        },
    )
    assert started.status_code == 200, started.text
    body = started.json()
    assert body.get("pipeline") == "realtime_voice"
    get_settings.cache_clear()
