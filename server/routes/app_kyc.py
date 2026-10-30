"""Identity verification (Didit KYC) — session creation, status and the webhook.

The webhook is deliberately unauthenticated by JWT: Didit calls it with an
X-Signature-V2 HMAC instead, and it must answer 2xx inside 5 seconds.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from server.auth.subscriber_dependencies import require_subscriber_jwt
from server.services.saas.tenant_guard import (
    SubscriberPrincipal,
    require_subscriber_permission,
)
from server.config.env import get_settings
from server.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)
router = APIRouter()
_voice_session_limiter = RateLimiter(max_requests=12, window_s=3600)
_voice_refresh_limiter = RateLimiter(max_requests=12, window_s=60)


class KycSessionBody(BaseModel):
    email: str | None = None


class VoiceKycSessionBody(BaseModel):
    legal_name: str = Field(min_length=2, max_length=255)
    business_type: str = Field(min_length=1, max_length=40)
    return_url: str | None = Field(default=None, max_length=2048)


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
        "required": get_settings().kyc_gate_purchases and kyc_service.is_configured(),
    }


@router.get("/api/kyc/voice/status")
async def voice_kyc_status(principal: SubscriberPrincipal = Depends(require_subscriber_jwt), refresh: bool = False):
    """Tenant-scoped carrier verification status without exposing carrier credentials."""
    from server.services.telephony import active_telephony_provider

    if active_telephony_provider() != "vobiz":
        return {
            "required": False,
            "configured": True,
            "approved": True,
            "status": "not_required",
            "callsBlocked": False,
            "verifications": {},
        }

    from server.services.saas import voice_kyc_service

    if refresh:
        allowed, retry = _voice_refresh_limiter.allow(str(principal.tenant_id))
        if not allowed:
            from server.utils.rate_limiter import raise_rate_limited
            raise_rate_limited(retry, "Verification status was checked too often. Please retry shortly.")
    try:
        # A console refresh of an approved account needs no carrier round trip;
        # purchase/dial gates still force a live check.
        return await voice_kyc_service.refresh_kyc_status(
            principal.tenant_id, force=refresh, skip_if_approved=True
        )
    except voice_kyc_service.VoiceKycError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "error": {
                    "code": exc.code,
                    "message": "Phone service verification status is temporarily unavailable.",
                }
            },
        ) from exc


@router.post("/api/kyc/voice/session")
async def create_voice_kyc_session(
    body: VoiceKycSessionBody,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    """Create/reuse the tenant carrier account and return its hosted KYC URL."""
    require_subscriber_permission(principal, "app.billing.write")
    from server.db.connection import get_session_factory
    from server.db.models.saas_models import User
    from server.utils.rate_limiter import raise_rate_limited

    allowed, retry = _voice_session_limiter.allow(str(principal.tenant_id))
    if not allowed:
        raise_rate_limited(retry, "Verification request limit reached. Please retry later.")
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="database_required")
    async with factory() as session:
        user = await session.get(User, principal.user_id)
        if not user or not user.email_verified_at or user.email.lower() != principal.email.lower():
            raise HTTPException(status_code=403, detail={"error": {
                "code": "email_not_verified", "message": "Verify your account email before starting phone service verification.",
            }})
    from server.services.telephony import active_telephony_provider

    if active_telephony_provider() != "vobiz":
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "voice_verification_not_required",
                    "message": "Phone service verification is not required for the current setup.",
                }
            },
        )
    from server.services.saas import voice_kyc_service

    try:
        return await voice_kyc_service.start_kyc_session(
            tenant_id=principal.tenant_id,
            email=principal.email,
            legal_name=body.legal_name,
            business_type=body.business_type,
            return_url=body.return_url,
        )
    except voice_kyc_service.VoiceKycError as exc:
        # Operators need to see a failed KYC start (sub-account or hosted link)
        # without the tenant having to report it.
        from server.services.saas.activity_log import record_event

        await record_event(
            action="voice_kyc.start_failed",
            resource_type="voice_kyc",
            resource_id=str(principal.tenant_id),
            actor=principal.email or str(principal.user_id),
            tenant_id=principal.tenant_id,
            payload={"code": exc.code, "httpStatus": exc.status_code},
            source="subscriber",
            outcome="error" if exc.status_code >= 500 else "ok",
            severity="error" if exc.status_code >= 500 else "warning",
        )
        messages = {
            "voice_service_not_configured": "Phone service onboarding is not configured yet. Contact support.",
            "voice_kyc_encryption_not_configured": "Phone service onboarding is not configured yet. Contact support.",
            "voice_kyc_encryption_invalid": "Phone service onboarding is not configured yet. Contact support.",
            "voice_account_needs_review": "Your phone service setup needs a quick check from our team. Please contact support; there is no need to start again.",
            "voice_account_create_failed": "We couldn't set up verification with these details. Please check your legal name and entity type, then try again.",
            "voice_identity_locked": "These business details are already registered. Contact support to change them.",
            "business_type_invalid": "Select a valid legal entity type.",
            "legal_name_required": "Enter the legal name for this account.",
            "account_email_required": "A verified account email is required.",
            "invalid_voice_kyc_return_url": "Could not return to the console after verification. Refresh and try again.",
            "voice_kyc_session_failed": "We couldn't open the verification page just now. Please try again in a few minutes.",
        }
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "error": {
                    "code": exc.code,
                    "message": messages.get(
                        exc.code,
                        "Phone service verification is temporarily unavailable. Please try again.",
                    ),
                }
            },
        ) from exc


@router.post("/api/webhooks/voice-kyc")
async def voice_kyc_webhook(request: Request):
    """No JWT: authenticate the exact raw body with the parent's HMAC instead."""
    import json
    from server.services.saas import voice_kyc_service

    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 65536:
            raise HTTPException(status_code=413, detail="payload_too_large")
    try:
        voice_kyc_service.verify_voice_webhook(bytes(raw), request.headers.get("X-Vobiz-Signature", ""))
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("Expected object")
    except voice_kyc_service.VoiceKycError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="bad_json") from None
    try:
        return await voice_kyc_service.apply_voice_webhook(payload)
    except Exception as exc:
        logger.warning("Phone verification callback failed error_type=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="verification_refresh_pending") from None


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
