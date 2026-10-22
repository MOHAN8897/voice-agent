"""The KYC gate: one place that decides whether an action is allowed.

Deliberately small and shared. Purchases and outbound PSTN calls both need an
Approved decision, and they must not each reimplement the check — the moment two
copies drift, one of the gates silently stops gating.

Browser practice sessions are NOT gated: blocking your own QA behind a compliance
step is how compliance gates get disabled by operators.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException


async def assert_kyc_approved(principal: Any, *, action: str) -> None:
    """Raise 403 unless this user's identity is verified.

    No-ops when the gate is switched off or Didit is not configured, so a
    misconfigured secret can never lock every customer out of the product.
    """
    from server.config.env import get_settings
    from server.services.saas import kyc_service

    settings = get_settings()
    if not settings.kyc_gate_purchases or not kyc_service.is_configured():
        return
    if await kyc_service.is_approved(getattr(principal, "user_id", None)):
        return
    state = await kyc_service.get_status(getattr(principal, "user_id", None))
    status = str(state.get("status") or "Not Started")
    raise HTTPException(
        status_code=403,
        detail={
            "error": {
                "code": "kyc_required",
                # The user needs the next step, not a bare refusal.
                "message": f"Verify your identity before you {action}.",
                "kycStatus": status,
                "verifyUrl": "/settings/verify-identity",
            }
        },
    )