"""Dev portal login — env credentials and special-character passwords."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from server.config.env import get_settings


@pytest.mark.asyncio
async def test_dev_login_admin_password_with_at_symbol(monkeypatch):
    monkeypatch.setenv("DEV_PORTAL_USERNAME", "admin")
    monkeypatch.setenv("DEV_PORTAL_PASSWORD", "Mohan@8897")
    get_settings.cache_clear()

    import server.app as app_mod

    transport = ASGITransport(app=app_mod.app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        bad = await client.post("/api/dev/login", json={"username": "admin", "password": "wrong"})
        assert bad.status_code == 200
        assert bad.json().get("ok") is False

        ok = await client.post(
            "/api/dev/login",
            json={"username": "Admin", "password": "Mohan@8897"},
        )
        assert ok.status_code == 200
        body = ok.json()
        assert body.get("ok") is True
        assert body.get("csrf_token")

        me = await client.get("/api/auth/dev-me")
        assert me.status_code == 200
        assert me.json().get("authenticated") is True

    get_settings.cache_clear()
