"""Dev environment overlay API tests."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from server.routes.dev_environment import EnvironmentPatch
from server.services.dev_secrets_store import ALLOWED_PATCH_KEYS, dev_secrets_store


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
            json={"enable_exotel": True, "exotel_webhook_base_url": "https://example.ngrok.app"},
            headers=headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert "enable_exotel" in body["applied_keys"]
        assert "exotel_webhook_base_url" in body["applied_keys"]

        snap = dev_secrets_store.snapshot()
        telephony = snap["groups"]["telephony"]
        webhook = next(x for x in telephony if x["field"] == "exotel_webhook_base_url")
        assert webhook["value"] == "https://example.ngrok.app"
        assert webhook["source"] == "overlay"

        delete_r = await client.delete("/api/dev/environment/exotel_webhook_base_url", headers=headers)
        assert delete_r.status_code == 200
        assert delete_r.json()["removed"] == "exotel_webhook_base_url"


@pytest.mark.asyncio
async def test_dev_environment_patch_cartesia_with_telnyx_fields():
    import server.app as app_mod

    transport = ASGITransport(app=app_mod.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post(
            "/api/dev/login",
            json={"username": "dev", "password": "devpass"},
        )
        assert login.status_code == 200
        csrf = login.json()["csrf_token"]
        r = await client.patch(
            "/api/dev/environment",
            json={
                "enable_cartesia": True,
                "enable_sarvam": True,
                "enable_telnyx": True,
                "enable_plivo": False,
                "telephony_provider": "telnyx",
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert r.status_code == 200, r.text
        applied = r.json()["applied_keys"]
        assert "enable_cartesia" in applied
        assert "enable_sarvam" in applied
        assert "enable_telnyx" in applied


def test_environment_patch_schema_covers_allowed_keys():
    assert set(EnvironmentPatch.model_fields) == ALLOWED_PATCH_KEYS


def test_environment_patch_accepts_telnyx_and_cartesia_toggles():
    body = EnvironmentPatch.model_validate(
        {
            "enable_telnyx": True,
            "enable_plivo": False,
            "enable_cartesia": True,
            "enable_sarvam": True,
            "telephony_provider": "telnyx",
            "telnyx_connection_id": "123",
            "telnyx_phone_number": "+15555550100",
            "telnyx_outbound_voice_profile_id": "456",
        }
    )
    dumped = body.model_dump(exclude_none=True)
    assert dumped["enable_cartesia"] is True
    assert dumped["enable_sarvam"] is True
    assert dumped["enable_telnyx"] is True
