"""Identity verification (Didit KYC) — session creation, status and the webhook.

The webhook is deliberately unauthenticated by JWT: Didit calls it with an
X-Signature-V2 HMAC instead, and it must answer 2xx inside 5 seconds.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from server.auth.subscriber_dependencies import require_subscriber_jwt
from server.services.saas.tenant_guard import (
    SubscriberPrincipal,
    require_subscriber_permission,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class KycSessionBody(BaseModel):
    email: str | None = None


@router.post("/api/kyc/session")
async def create_kyc_session(
    body: KycSessionBody,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    """Create a verification session server-side and return only the hosted URL.

    The API key stays on this side of the wire — the client gets a `url` and a
    session id, nothing else.
    """
    from server.services.saas import kyc_service

    try:
        return await kyc_service.create_session(
            user_id=principal.user_id,
            tenant_id=principal.tenant_id,
            email=body.email or principal.email,
        )
    except kyc_service.KycNotConfigured as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "kyc_not_configured", "message": str(exc)}},
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "kyc_session_failed", "message": str(exc)}},
        ) from exc


@router.get("/api/kyc/status")
async def kyc_status(principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    """Current state for the signed-in user. Drives the 'verify before you buy' UI."""
    from server.services.saas import kyc_service

    return {
        **await kyc_service.get_status(principal.user_id),
        "configured": kyc_service.is_configured(),
    }


@router.post("/api/webhooks/didit")
async def didit_webhook(
    request: Request,
    x_signature_v2: str | None = Header(None, alias="X-Signature-V2"),
    x_timestamp: str | None = Header(None, alias="X-Timestamp"),
):
    """Verified webhook: the source of truth for every identity decision.

    Order matters — freshness, then canonical HMAC compare, then idempotency, then
    dispatch. Returns 2xx immediately.
    """
    from server.services.saas import kyc_service

    raw = await request.body()
    try:
        kyc_service.verify_signature(raw, x_signature_v2 or "", x_timestamp)
    except kyc_service.KycSignatureError as exc:
        logger.warning("[KYC] webhook rejected: %s", exc)
        raise HTTPException(status_code=401, detail="bad_signature") from exc

    import json

    try:
        payload: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="bad_json") from None

    try:
        return await kyc_service.apply_webhook(payload)
    except Exception:
        # A 5xx makes Didit retry twice, which is what we want for a transient
        # database fault — but log it loudly either way.
        logger.exception("[KYC] webhook handling failed event=%s", payload.get("event_id"))
        raise HTTPException(status_code=500, detail="webhook_failed") from None