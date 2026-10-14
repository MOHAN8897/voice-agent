"""Stripe webhooks — permanently decommissioned and secured (410 Gone)."""
from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/stripe/webhook")
async def stripe_webhook():
    """Stripe has been completely removed from this platform."""
    raise HTTPException(
        status_code=410,
        detail="Stripe endpoints have been permanently decommissioned.",
    )
