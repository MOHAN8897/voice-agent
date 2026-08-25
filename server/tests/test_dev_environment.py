"""Dev environment overlay API tests."""
from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from server.services.dev_secrets_store import dev_secrets_store


@pytest.mark.asyncio
async def test_dev_environment_patch_toggle():
    import server.app as app_mod

    transport = ASGITransport(app=app_mod.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post(
            "/api/dev/login",
            json={"username": "dev", "password": "devpass"},
        )
        assert login.status_code == 200
        csrf = login.json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf}

        r = await client.patch(
            "/api/dev/environment",
            json={"enable_plivo": True, "plivo_webhook_base_url": "https://example.ngrok.app"},
            headers=headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert "enable_plivo" in body["applied_keys"]
        assert "plivo_webhook_base_url" in body["applied_keys"]

        snap = dev_secrets_store.snapshot()
        telephony = snap["groups"]["telephony"]
        webhook = next(x for x in telephony if x["field"] == "plivo_webhook_base_url")
        assert webhook["value"] == "https://example.ngrok.app"
        assert webhook["source"] == "overlay"

        delete_r = await client.delete("/api/dev/environment/plivo_webhook_base_url", headers=headers)
        assert delete_r.status_code == 200
        assert delete_r.json()["removed"] == "plivo_webhook_base_url"
