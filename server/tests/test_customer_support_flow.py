"""Unit tests for Customer Support Flow & Configuration endpoints."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from server.app import app
from server.services.saas.customer_support_service import (
    create_support_inquiry,
    get_support_config,
    update_support_config,
)


@pytest.mark.asyncio
async def test_public_support_config():
    """Verify public endpoint /api/support/config returns channels and business hours."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/support/config")
        assert res.status_code == 200
        data = res.json()
        assert data.get("ok") is True
        cfg = data.get("config", {})
        assert "supportEmail" in cfg or "support_email" in cfg
        assert "businessHours" in cfg or "business_hours" in cfg


@pytest.mark.asyncio
async def test_public_contact_us_ticket_submission():
    """Verify /api/support/contact submits an inquiry and generates a valid ticket number."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "fullName": "Mohan Saiteja",
            "email": "mohanssaiteja.99@gmail.com",
            "phone": "+1 555 123 4567",
            "company": "Acme Voice Corp",
            "category": "enterprise_fleet",
            "priority": "high",
            "subject": "Dedicated trunk setup assistance",
            "message": "We need help configuring our direct voice trunk for high-throughput concurrency.",
        }
        res = await client.post("/api/support/contact", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data.get("ok") is True
        ticket = data.get("ticket", {})
        assert "ticketNumber" in ticket
        assert ticket["ticketNumber"].startswith("DT-")
        assert ticket["fullName"] == "Mohan Saiteja"
        assert ticket["email"] == "mohanssaiteja.99@gmail.com"
        assert ticket["status"] in ("new", "open")


@pytest.mark.asyncio
async def test_contact_us_honeypot_bot_trap():
    """Verify anti-bot honeypot field silences spam bots with a synthetic ack without creating DB tickets."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "fullName": "Spam Bot",
            "email": "bot@automated-spam.com",
            "subject": "Spam payload",
            "message": "Click here for free coins",
            "botTrap": "malicious_bot_filled_input",
        }
        res = await client.post("/api/support/contact", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data.get("ok") is True
        # Synthetic ACK returned, real DB ticket never generated
        assert data.get("ticket", {}).get("ticketNumber") == "DT-ACK-REC"


@pytest.mark.asyncio
async def test_public_support_config_social_and_security():
    """Verify public config contains social links and never leaks internal SMTP passwords or wholesale carriers."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/support/config")
        assert res.status_code == 200
        data = res.json()
        cfg = data.get("config", {})
        # Social links present
        assert "socialLinks" in cfg
        social = cfg["socialLinks"]
        assert "twitter" in social
        assert "linkedin" in social
        assert "github" in social
        assert "youtube" in social
        assert "discord" in social
        # Private secrets NOT leaked to public
        assert "smtpPassword" not in cfg
        assert "smtpHost" not in cfg


@pytest.mark.asyncio
async def test_contact_us_validation_error():
    """Verify invalid input is rejected with 400 validation error."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/api/support/contact", json={"fullName": ""})
        assert res.status_code in (400, 422)


@pytest.mark.asyncio
async def test_admin_support_config_unauthenticated():
    """Admin support endpoints fail-closed without valid platform admin authorization."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/admin/support/config")
        assert res.status_code in (401, 403, 503)
        res_put = await client.put("/api/admin/support/config", json={"supportEmail": "test@dialtact.com"})
        assert res_put.status_code in (401, 403, 503)
        res_inq = await client.get("/api/admin/support/inquiries")
        assert res_inq.status_code in (401, 403, 503)
        res_smtp = await client.post("/api/admin/support/smtp/test", json={"smtpHost": "smtp.test.com"})
        assert res_smtp.status_code in (401, 403, 503)
