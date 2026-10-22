"""Public customer support endpoints for Contact Us page and flow configuration."""
from __future__ import annotations

import html
import logging
import time
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from server.services.saas.customer_support_service import (
    create_support_inquiry,
    get_support_config,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Rate limiting sliding window: max 5 submissions per 10 minutes per IP
_SUBMISSION_HISTORY: dict[str, list[float]] = defaultdict(list)
_MAX_SUBMISSIONS_PER_WINDOW = 5
_WINDOW_SECONDS = 600.0


class ContactInquiryBody(BaseModel):
    fullName: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    company: Optional[str] = Field(None, max_length=255)
    category: str = Field("technical_support", max_length=64)
    priority: str = Field("normal", max_length=32)
    subject: str = Field(..., min_length=2, max_length=255)
    message: str = Field(..., min_length=5, max_length=5000)
    botTrap: Optional[str] = Field(None, max_length=100)  # Honeypot field


@router.get("/api/support/config")
async def public_support_config():
    """Retrieve public customer support channels, business hours, social links, and SLAs."""
    config = await get_support_config(for_admin=False)
    return {"ok": True, "config": config}


@router.post("/api/support/contact")
async def public_submit_inquiry(body: ContactInquiryBody, request: Request):
    """Submit a contact inquiry or support ticket from the website with security guards."""
    # 1. Anti-bot honeypot check
    if body.botTrap and body.botTrap.strip():
        logger.info("Bot submission trapped via honeypot field from %s", request.client.host if request.client else "unknown")
        # Return synthetic success so spammers do not adapt
        return {
            "ok": True,
            "ticket": {
                "ticketNumber": "DT-ACK-REC",
                "fullName": body.fullName,
                "email": body.email,
                "status": "new",
            },
            "message": "Your inquiry has been submitted successfully.",
        }

    # 2. Rate limiting check
    client_ip = request.client.host if request.client else "anonymous"
    rate_key = f"{client_ip}:{body.email.lower()}"
    now = time.time()
    recent = [t for t in _SUBMISSION_HISTORY[rate_key] if now - t < _WINDOW_SECONDS]
    _SUBMISSION_HISTORY[rate_key] = recent

    if len(recent) >= _MAX_SUBMISSIONS_PER_WINDOW:
        raise HTTPException(
            status_code=429,
            detail={"error": {"code": "rate_limited", "message": "Too many support requests. Please try again in a few minutes."}},
        )
    _SUBMISSION_HISTORY[rate_key].append(now)

    # 3. Input sanitation (prevent HTML injection / stored XSS)
    clean_name = html.escape(body.fullName.strip())
    clean_company = html.escape(body.company.strip()) if body.company else None
    clean_subject = html.escape(body.subject.strip())
    clean_message = html.escape(body.message.strip())

    # 4. Optional tenant authentication resolution
    tenant_id = None
    try:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            from server.services.jwt_service import decode_token
            payload = decode_token(auth_header.split(" ", 1)[1])
            if payload and payload.get("tenant_id"):
                import uuid
                tenant_id = uuid.UUID(payload["tenant_id"])
    except Exception:
        pass

    try:
        inquiry = await create_support_inquiry(
            full_name=clean_name,
            email=body.email.strip().lower(),
            subject=clean_subject,
            message=clean_message,
            company=clean_company,
            category=body.category,
            priority=body.priority,
            tenant_id=tenant_id,
        )
        return {
            "ok": True,
            "ticket": inquiry,
            "message": "Your support inquiry has been submitted successfully.",
        }
    except Exception as exc:
        logger.error("Failed to submit support inquiry: %s", exc)
        raise HTTPException(
            status_code=500,
            detail={"error": {"code": "support_error", "message": "Failed to submit inquiry. Please try again."}},
        )
