"""Portal password hashing tests."""
from server.auth.passwords import hash_portal_password, password_hash_needs_upgrade, verify_portal_password
import pytest


def test_plain_password_verify():
    assert verify_portal_password("secret", "secret")
    assert not verify_portal_password("secret", "wrong")


def test_pbkdf2_password_verify():
    stored = hash_portal_password("devpass")
    assert stored.startswith("pbkdf2-sha256$")
    assert verify_portal_password(stored, "devpass")
    assert not verify_portal_password(stored, "nope")


def test_random_salts_and_legacy_hash_compatibility():
    import hashlib
    first = hash_portal_password("audit-only-password")
    second = hash_portal_password("audit-only-password")
    assert first != second and first.startswith("pbkdf2-sha256$600000$")
    password = "legacy-audit-password"
    salt = hashlib.sha256(password.encode()).digest()[:16]
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120000)
    legacy = f"pbkdf2-sha256$120000${salt.hex()}${digest.hex()}"
    assert verify_portal_password(legacy, password)
    assert not verify_portal_password(legacy, "wrong")
    assert password_hash_needs_upgrade(legacy)
    assert not password_hash_needs_upgrade(first)
    assert password_hash_needs_upgrade("legacy-env-secret")


def test_malformed_hash_and_unicode_input_fail_safely():
    assert verify_portal_password("dev-only-secret", "\u0c24\u0c46\u0c32\u0c41\u0c17\u0c41") is False
    assert verify_portal_password("pbkdf2-sha256$-1$00$00", "input") is False
    assert verify_portal_password("pbkdf2-sha256$999999999$00$00", "input") is False


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["dev", "app"])
async def test_portal_password_checks_do_not_block_event_loop(monkeypatch, kind):
    import threading
    from types import SimpleNamespace
    from fastapi import Request, Response
    from server.routes import auth
    threads = []
    def verify(_stored, _provided):
        threads.append(threading.get_ident())
        return False
    monkeypatch.setattr(auth, "verify_portal_password", verify)
    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(
        saas_auth_enabled=False, dev_portal_username="audit", dev_portal_password="unused",
        app_console_username="audit", app_console_password="unused"))
    monkeypatch.setattr(auth, "_login_limiter", SimpleNamespace(allow=lambda _key: (True, 0)))
    body = auth.LoginBody(username="audit", password="isolated")
    response = Response()
    if kind == "dev":
        result = await auth.dev_login(body, Request({"type": "http", "client": ("127.0.0.1", 1234)}), response)
    else:
        result = await auth.app_login(body, response)
    assert result["ok"] is False
    assert len(threads) == 1 and threads[0] != threading.get_ident()
