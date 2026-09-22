"""Transactional email via Resend."""
from __future__ import annotations

import logging

import httpx

from server.config.env import get_settings

logger = logging.getLogger(__name__)


async def send_email(to: str, subject: str, html: str) -> bool:
    settings = get_settings()
    api_key = settings.resend_api_key
    if not api_key:
        logger.warning("Resend not configured; skipping email to %s", to)
        return False
    from_addr = settings.resend_from_email or "Voxly <onboarding@resend.dev>"
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"from": from_addr, "to": [to], "subject": subject, "html": html},
        )
    if resp.status_code >= 400:
        logger.error("Resend failed %s: %s", resp.status_code, resp.text[:500])
        return False
    return True


async def send_verification_email(to: str, verify_url: str) -> bool:
    html = f"""
    <p>Welcome to Voxly.</p>
    <p><a href="{verify_url}">Verify your email</a> to activate your account.</p>
    <p>This link expires in 24 hours.</p>
    """
    return await send_email(to, "Verify your Voxly email", html)


async def send_password_reset_email(to: str, reset_url: str) -> bool:
    html = f"""
    <p>We received a request to reset your Voxly password.</p>
    <p><a href="{reset_url}">Reset password</a></p>
    <p>If you did not request this, you can ignore this email.</p>
    <p>This link expires in 1 hour.</p>
    """
    return await send_email(to, "Reset your Voxly password", html)
