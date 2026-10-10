"""Subscriber telephony API (PRD-05, PRD-04)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from server.utils.logger import logger

from server.auth.subscriber_dependencies import require_subscriber_jwt
from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.entities import Agent, Call
from server.db.models.phase5_models import PhoneNumber
from server.db.models.saas_models import TelephonyContact
from server.services.saas.call_callback_service import (
    list_callbacks,
    request_callback,
)
from server.services.saas.number_purchase_service import (
    create_purchase_checkout,
    get_purchase,
    purchase_with_wallet,
)
from server.services.saas.dev_tester_workspace import ensure_dev_tester_phone_line
from server.services.saas.tenant_guard import (
    SubscriberPrincipal,
    require_subscriber_permission,
    subscriber_workspace_tenant_id,
)
from server.services.saas.voice_catalog import phone_voice_catalog
from server.services.saas.telephony_orchestrator import subscriber_outbound
from server.config.constants import constants
from server.utils.rate_limiter import RateLimiter, raise_rate_limited

router = APIRouter()
_outbound_limiter = RateLimiter(max_requests=12, window_s=60)
_buy_limiter = RateLimiter(max_requests=8, window_s=3600)


class OutboundCallBody(BaseModel):
    agentId: str
    fromE164: str | None = None
    toE164: str
    dialRequestId: str | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_stack_fields(cls, data):
        if isinstance(data, dict):
            for key in ("stackOverride", "stack_override", "tier", "pipeline"):
                if key in data:
                    raise ValueError(f"{key} not allowed for subscriber calls")
        return data


class BuyNumberBody(BaseModel):
    e164: str = Field(..., min_length=8)
    country: str = Field("US", max_length=8)
    payMethod: str = Field("wallet")
    assignAgentId: str | None = None


class AssignNumberBody(BaseModel):
    agentId: str | None = None


class RoutingBody(BaseModel):
    agentId: str | None = None
    inboundEnabled: bool | None = None
    outboundEnabled: bool | None = None


class ContactBody(BaseModel):
    name: str
    phone: str
    notes: str | None = None


@router.post("/api/telephony/calls/outbound")
async def telephony_outbound(body: OutboundCallBody, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    require_subscriber_permission(principal, "app.telephony.write")
    settings = get_settings()
    if not settings.saas_telephony_enabled:
        raise HTTPException(status_code=503, detail={"error": {"code": "telephony_disabled", "message": "Telephony disabled"}})
    allowed, retry = _outbound_limiter.allow(f"out:{principal.tenant_id}")
    if not allowed:
        raise_rate_limited(retry, "Outbound call rate limit reached. Wait and try again.")
    return await subscriber_outbound(
        principal,
        agent_id=body.agentId,
        from_e164=body.fromE164,
        to_e164=body.toE164,
        dial_request_id=body.dialRequestId,
    )


@router.post("/api/calls/outbound")
async def calls_outbound_alias(body: OutboundCallBody, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    return await telephony_outbound(body, principal)


@router.get("/api/telephony/provider")
async def telephony_provider_info(principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    """Return backend-configured active telephony provider details so frontend dynamically aligns."""
    from server.services.telephony import active_telephony_provider
    from server.services.telephony_status import all_provider_status

    active = active_telephony_provider()
    statuses = await all_provider_status()
    active_details = next((s for s in statuses if s.get("id") == active), {})
    return {
        "activeProvider": active,
        "activeLabel": active_details.get("label") or active.title(),
        "ready": bool(active_details.get("ready")),
        "enabled": bool(active_details.get("enabled")),
        "phoneNumber": active_details.get("phone_number"),
        "supportedProviders": ["telnyx", "vobiz", "exotel"],
        "providers": [
            {
                "id": s.get("id"),
                "label": s.get("label"),
                "enabled": s.get("enabled"),
                "ready": s.get("ready"),
                "phoneNumber": s.get("phone_number"),
                "balance": s.get("balance"),
                "connectionId": s.get("connection_id"),
                "webhookUrl": s.get("webhook_url") or s.get("answer_url"),
                "hangupUrl": s.get("hangup_url"),
                "fallbackUrl": s.get("fallback_url"),
                "recordingUrl": s.get("recording_url"),
                "streamWs": s.get("stream_ws"),
                "accountInfo": s.get("account_info"),
                "checklist": s.get("checklist"),
            }
            for s in statuses
        ],
    }


class SwitchTelephonyProviderBody(BaseModel):
    provider: str = Field(..., pattern="^(telnyx|vobiz|exotel|plivo)$")


@router.post("/api/telephony/provider")
async def telephony_set_provider(
    body: SwitchTelephonyProviderBody,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    from server.services.dev_secrets_store import dev_secrets_store

    enable_key = f"enable_{body.provider}"
    dev_secrets_store.update({
        "telephony_provider": body.provider,
        enable_key: True,
    })
    return {"ok": True, "activeProvider": body.provider}



@router.get("/api/telephony/voice-options")
async def telephony_voice_options(principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    """Subscriber-safe voice list for the production phone AI stack (no dev stack UI)."""
    # Only languages the platform offers at creation, so the settings tab cannot
    # be used to sidestep the admin enablement list.
    from server.services.saas.platform_languages import language_options

    languages = language_options()
    return {
        "stackLabel": "Live phone AI",
        "stackDescription": "Same voice engine for incoming calls, outgoing calls, and browser practice calls.",
        "defaultVoiceId": "marin",
        "voices": phone_voice_catalog(),
        "languages": languages,
    }


class VoicePreviewBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=400)
    voiceId: str | None = Field(None, max_length=64)


@router.post("/api/telephony/voice-preview")
async def voice_preview(
    body: VoicePreviewBody, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)
):
    """Speak `text` in the agent's real production voice, and return it as a WAV.

    Runs the same live model a caller would reach, so what the operator hears in
    the studio is what a customer hears on the line. The browser's own speech
    synthesis is deliberately not used — it is a different engine with different
    voices, and approving against it means approving the wrong thing.
    """
    require_subscriber_permission(principal, "app.billing.write")
    from server.services.saas.voice_preview import synthesize_preview

    try:
        result = await synthesize_preview(body.text, voice_id=body.voiceId)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": str(exc), "message": "Nothing to preview."}},
        ) from None
    except Exception as exc:
        logger.warning("[VOICE] preview failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail={
                "error": {
                    "code": "voice_preview_unavailable",
                    "message": "Could not reach the voice service. Check the voice configuration.",
                }
            },
        ) from None
    return Response(
        content=result["audio"],
        media_type="audio/wav",
        headers={
            "X-Voice-Name": result["voice"],
            "X-Voice-Label": result["label"],
            "X-Voice-Model": result["model"],
            "Cache-Control": "no-store",
        },
    )


@router.get("/api/telephony/numbers")
async def list_numbers(principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    workspace_tid = subscriber_workspace_tenant_id(principal)
    await ensure_dev_tester_phone_line(workspace_tid, principal.email)
    factory = get_session_factory()
    if factory is None:
        return {"numbers": []}
    async with factory() as session:
        result = await session.execute(
            select(PhoneNumber).where(
                PhoneNumber.tenant_id == workspace_tid,
                PhoneNumber.released_at.is_(None),
            )
        )
        numbers = []
        from server.services.saas.billing_rates import rates_with_derived_inr
        from server.services.telephony import active_telephony_provider

        active_prov = active_telephony_provider()
        rates = rates_with_derived_inr()
        monthly_usd = round(rates["did_monthly_usd_cents"] / 100.0, 2)
        monthly_inr = round(rates["did_monthly_inr_paise"] / 100.0, 2)
        for n in result.scalars():
            e164 = n.e164 or ""
            prov = "telnyx" if (n.telnyx_number_id or e164 == "+13526146416") else ("vobiz" if n.plivo_number_id else "vobiz")
            if prov != active_prov:
                continue
            if e164.startswith("+1"):
                country = "US"
            elif e164.startswith("+44"):
                country = "GB"
            elif e164.startswith("+61"):
                country = "AU"
            elif e164.startswith("+91"):
                country = "IN"
            elif e164.startswith("+65"):
                country = "SG"
            else:
                country = None
            numbers.append(
                {
                    "id": str(n.id),
                    "e164": n.e164,
                    "status": n.status,
                    "agentId": str(n.agent_id) if n.agent_id else None,
                    "inboundEnabled": n.inbound_enabled,
                    "outboundEnabled": n.outbound_enabled,
                    "billingSource": n.billing_source,
                    "monthlyCost": monthly_usd,
                    "monthlyInr": monthly_inr,
                    "country": country,
                    "provider": prov,
                    "telnyxNumberId": n.telnyx_number_id,
                    "plivoNumberId": n.plivo_number_id,
                }
            )
    return {"numbers": numbers, "activeProvider": active_prov}


@router.get("/api/telephony/numbers/search")
async def search_numbers(
    country: str | None = None,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    require_subscriber_permission(principal, "app.telephony.write")
    from server.services.telnyx_client import TelnyxClient
    from server.services.saas.telephony_countries import normalize_buy_country
    from server.services.saas.billing_rates import rates_with_derived_inr
    from server.services.saas.number_inventory import list_inventory_for_sale
    from server.services.telephony import active_telephony_provider

    active_prov = active_telephony_provider()
    country_default = "IN" if active_prov == "vobiz" else "US"
    country = normalize_buy_country(country or country_default, default=country_default)
    rates = rates_with_derived_inr()
    # Chargeable platform rate — must match wallet debit and the buy-modal header.
    monthly_usd = round(rates["did_monthly_usd_cents"] / 100.0, 2)
    monthly_inr = round(rates["did_monthly_inr_paise"] / 100.0, 2)

    priced: list[dict] = []
    seen: set[str] = set()

    # Pre-seed seen with all numbers already assigned or unavailable in the system
    factory = get_session_factory()
    if factory is not None:
        async with factory() as session:
            from server.services.saas.number_inventory import ensure_platform_inventory_tenant
            from server.db.models.saas_models import NumberReservation
            from datetime import datetime, timezone
            inv_tid = await ensure_platform_inventory_tenant()

            # Numbers assigned to tenants or not available in inventory
            pn_rows = (
                await session.execute(
                    select(PhoneNumber.e164).where(
                        PhoneNumber.released_at.is_(None),
                        (PhoneNumber.tenant_id != inv_tid) | (PhoneNumber.status != "available"),
                    )
                )
            ).scalars().all()
            for n_e164 in pn_rows:
                if n_e164:
                    seen.add(str(n_e164).strip())

            # Unexpired reservations
            now_utc = datetime.now(timezone.utc)
            res_rows = (
                await session.execute(
                    select(NumberReservation.e164).where(NumberReservation.expires_at > now_utc)
                )
            ).scalars().all()
            for r_e164 in res_rows:
                if r_e164:
                    seen.add(str(r_e164).strip())

    # Admin inventory: only include inventory when Telnyx is active (since inventory holds Telnyx DIDs)
    if active_prov != "vobiz":
        for item in await list_inventory_for_sale(country=country):
            e164 = str(item.get("e164") or "")
            if not e164 or e164 in seen:
                continue
            seen.add(e164)
            priced.append(
                {
                    **item,
                    "monthlyUsd": monthly_usd,
                    "monthlyInr": monthly_inr,
                    "fee": monthly_usd,
                    "country": country,
                    "provider": "telnyx",
                }
            )

    try:
        if active_prov == "vobiz":
            from server.services.vobiz_client import VobizClient
            numbers = await VobizClient().search_available_numbers(country=country, limit=10)
        else:
            numbers = await TelnyxClient().search_available_numbers(country=country, limit=10)
    except Exception as exc:
        logger.warning("%s catalog search failed country=%s: %s", active_prov, country, exc)
        numbers = []
    for row in numbers:
        item = dict(row) if isinstance(row, dict) else {"e164": str(row)}
        e164 = str(item.get("e164") or item.get("phone_number") or "")
        if e164 and e164 in seen:
            continue
        if e164:
            seen.add(e164)
        item["monthlyInr"] = monthly_inr
        item["monthlyUsd"] = monthly_usd
        item["fee"] = monthly_usd
        item["country"] = country
        item.setdefault("source", active_prov)
        item.setdefault("provider", active_prov)
        priced.append(item)
    return {
        "numbers": priced,
        "country": country,
        "didMonthlyInr": monthly_inr,
        "didMonthlyUsd": monthly_usd,
        "activeProvider": active_prov,
    }


@router.get("/api/telephony/countries")
async def list_buy_countries(principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    """Countries SaaS buyers can purchase numbers in."""
    require_subscriber_permission(principal, "app.telephony.write")
    from server.services.saas.telephony_countries import buy_country_options
    from server.services.telephony import active_telephony_provider

    active_prov = active_telephony_provider()
    default_country = "IN" if active_prov == "vobiz" else "US"
    return {"countries": buy_country_options(), "default": default_country, "activeProvider": active_prov}


@router.get("/api/telephony/compliance")
async def list_compliance(
    country: str | None = Query(None, description="ISO-3166 alpha-2; omit for the full catalogue"),
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    """Compliance obligations for one country, or the catalogue for all of them.

    Advisory metadata for the agent settings screen. It is not consulted by the
    call path — nothing here changes how a call is placed.
    """
    require_subscriber_permission(principal, "app.telephony.write")
    from server.services.saas.country_compliance import compliance_catalog, compliance_for_country

    if country:
        return compliance_for_country(country)
    return {"countries": compliance_catalog()}


class ComplianceBody(BaseModel):
    """Which obligations the operator has confirmed for this agent."""

    acknowledged: dict[str, bool] = Field(default_factory=dict)


@router.put("/api/agents/{agent_id}/compliance")
async def put_agent_compliance(
    agent_id: str,
    body: ComplianceBody,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    """Record the operator's compliance acknowledgements for an agent.

    Persisted onto the agent so it survives a reload. Unknown keys are dropped
    rather than stored: a typo must not look like a satisfied obligation later.
    """
    require_subscriber_permission(principal, "app.agents.write")
    from server.services.saas.country_compliance import merge_agent_compliance

    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database required")
    async with factory() as session:
        row = await session.get(Agent, uuid.UUID(agent_id))
        if row is None or str(row.tenant_id) != str(principal.tenant_id):
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "not_found", "message": "Agent not found"}},
            )
        current = dict(row.voice_settings or {})
        current["compliance"] = {"acknowledged": body.acknowledged}
        row.voice_settings = current
        await session.commit()
        merged = merge_agent_compliance(current["compliance"], await _agent_country(row, session))
    from server.services.saas.activity_log import record_event

    await record_event(
        action="agent.compliance.updated",
        resource_type="agent",
        resource_id=agent_id,
        actor=principal.email or str(principal.user_id),
        tenant_id=principal.tenant_id,
        payload=merged,
        source="subscriber",
    )
    return {"ok": True, **merged}


@router.get("/api/agents/{agent_id}/compliance")
async def get_agent_compliance(
    agent_id: str, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)
):
    """Stored acknowledgements merged over the catalogue for the agent's country."""
    require_subscriber_permission(principal, "app.calls.read")
    from server.services.saas.country_compliance import merge_agent_compliance

    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database required")
    async with factory() as session:
        row = await session.get(Agent, uuid.UUID(agent_id))
        if row is None or str(row.tenant_id) != str(principal.tenant_id):
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "not_found", "message": "Agent not found"}},
            )
        saved = (row.voice_settings or {}).get("compliance")
        return merge_agent_compliance(saved, await _agent_country(row, session))


async def _agent_country(row, session) -> str:
    """The country this agent operates in, from its assigned number.

    Falls back to the platform default so the settings screen always shows a
    jurisdiction rather than an empty card.
    """
    from server.db.models.phase5_models import PhoneNumber

    result = await session.execute(
        select(PhoneNumber).where(PhoneNumber.agent_id == row.agent_id).limit(1)
    )
    number = result.scalars().first()
    if number and number.e164:
        # E.164 country calling code -> ISO-3166 alpha-2. NANP numbers (the +1
        # trunk) cover US, CA and AU, so the dialled number alone cannot tell them
        # apart; US is the platform default for a NANP number with no better signal.
        dial = str(number.e164).lstrip("+").split(".")[0][:1]
        return {"1": "US"}.get(dial, "US")
    return "US"


@router.post("/api/telephony/buy")
async def buy_number(
    body: BuyNumberBody,
    request: Request,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    require_subscriber_permission(principal, "app.billing.write")
    # Buying a number is a compliance-gated action (see server/services/saas/kyc_gate.py).
    from server.services.saas.activity_log import record_event
    from server.services.saas.kyc_gate import assert_kyc_approved

    allowed, retry = _buy_limiter.allow(f"buy:{principal.tenant_id}")
    if not allowed:
        raise_rate_limited(retry, "Number purchase rate limit reached.")
    pay = (body.payMethod or "wallet").strip().lower()
    # Every attempt is logged, including the ones that stop at the KYC gate. A
    # refused purchase is the thing an operator needs to see, and it never reaches
    # the purchase service — so logging only there would hide every refusal.
    try:
        await assert_kyc_approved(principal, action="buy a phone number")
        if pay == "stripe":
            result = await create_purchase_checkout(
                principal,
                e164=body.e164,
                country_code=body.country,
                assign_agent_id=body.assignAgentId,
            )
        else:
            result = await purchase_with_wallet(
                principal,
                e164=body.e164,
                country_code=body.country,
                assign_agent_id=body.assignAgentId,
            )
    except HTTPException as exc:
        await _log_purchase_refusal(
            request, principal, body, pay, exc, getattr(exc, "status_code", 500)
        )
        raise
    except ValueError as e:
        code = str(e)
        await _log_purchase_refusal_code(
            request, principal, body, pay, code, _purchase_error_status(code)
        )
        if code == "verification_required":
            status = 403
        elif code == "stripe_not_configured":
            status = 503
        elif code == "insufficient_balance":
            status = 402
        elif code == "carrier_balance_exhausted":
            # 503: our carrier account is out of funds, not the customer's problem.
            status = 503
        elif code == "carrier_not_configured":
            status = 503
        elif code == "carrier_order_failed":
            status = 502
        elif code == "kyc_required":
            status = 403
        else:
            status = 400
        messages = {
            "stripe_not_configured": "Card checkout is not configured. Use wallet credits to buy a number.",
            "verification_required": "Verify your email before buying a number.",
            "kyc_required": "Verify your identity before buying a phone number.",
            "carrier_balance_exhausted": (
                "Phone numbers are temporarily unavailable. Your wallet was not charged."
            ),
            "carrier_not_configured": "Telephony line service is being updated. Please contact support.",
            "carrier_order_failed": "Unable to complete number order with provider. Your wallet was not charged.",
            "number_reserved": "This number is reserved by another checkout. Try a different number.",
            "number_unavailable": "This number is no longer available.",
            "number_limit": "This workspace has reached its phone number limit.",
            "invalid_e164": "Enter a valid E.164 number.",
            "invalid_agent": "Choose a valid agent to assign this number to.",
            "insufficient_balance": "Add funds to your wallet before buying a number.",
        }
        raise HTTPException(
            status_code=status,
            detail={"error": {"code": code, "message": messages.get(code, code)}},
        )
    except Exception as exc:
        logger.exception("Unexpected error in buy_number: %s", exc)
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "purchase_temporarily_unavailable",
                    "message": "Phone line service is momentarily unavailable. Your account was not charged. Please try again shortly.",
                }
            },
        )

    # Paid and enqueued. Recorded here rather than in the service so the row also
    # captures what the customer actually asked for.
    await record_event(
        action="number.purchase.accepted",
        resource_type="number_purchase",
        resource_id=str(result.get("purchaseId") or ""),
        actor=principal.email or str(principal.user_id),
        tenant_id=principal.tenant_id,
        payload={
            "e164": body.e164,
            "country": body.country,
            "payMethod": pay,
            "assignAgentId": body.assignAgentId,
            "status": result.get("status"),
        },
        source="subscriber",
        request=request,
    )
    return result


#: Why a purchase was refused, in the operator's language. A refusal with no
#: explanation here is the case they cannot diagnose from the log.
_REFUSAL_HINTS = {
    "kyc_required": "identity verification not approved",
    "verification_required": "email not verified",
    "insufficient_balance": "wallet could not cover the number",
    "carrier_balance_exhausted": "carrier account out of funds — operator action",
    "number_reserved": "another checkout holds this number",
    "number_unavailable": "number no longer available at the carrier",
    "number_limit": "workspace number limit reached",
    "invalid_e164": "malformed number",
    "invalid_agent": "assignAgentId is not an agent of this workspace",
}


def _purchase_error_status(code: str) -> int:
    if code in ("verification_required", "kyc_required"):
        return 403
    if code == "stripe_not_configured":
        return 503
    if code == "insufficient_balance":
        return 402
    if code == "carrier_balance_exhausted":
        # Our carrier account is out of funds, not the customer's problem.
        return 503
    return 400


async def _log_purchase_refusal_code(
    request: Request,
    principal: SubscriberPrincipal,
    body: BuyNumberBody,
    pay: str,
    code: str,
    status: int,
) -> None:
    from server.services.saas.activity_log import record_event

    await record_event(
        action="number.purchase.refused",
        resource_type="number_purchase",
        resource_id=body.e164,
        actor=principal.email or str(principal.user_id),
        tenant_id=principal.tenant_id,
        payload={
            "error": code,
            "hint": _REFUSAL_HINTS.get(code, code),
            "httpStatus": status,
            "e164": body.e164,
            "country": body.country,
            "payMethod": pay,
            "assignAgentId": body.assignAgentId,
        },
        source="subscriber",
        # 402 is the customer's wallet; 5xx is ours. Only ours is an "error".
        outcome="error" if status >= 500 else "ok",
        severity="warning" if status < 500 else "error",
        request=request,
    )


async def _log_purchase_refusal(
    request: Request,
    principal: SubscriberPrincipal,
    body: BuyNumberBody,
    pay: str,
    exc: HTTPException,
    status: int,
) -> None:
    """Log an HTTP-shaped refusal (the KYC gate raises one)."""
    code = "unknown"
    try:
        detail = exc.detail
        if isinstance(detail, dict):
            code = str((detail.get("error") or {}).get("code") or "unknown")
    except Exception:
        pass
    await _log_purchase_refusal_code(request, principal, body, pay, code, status)


@router.get("/api/telephony/purchases/{purchase_id}")
async def get_purchase_status(purchase_id: str, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    row = await get_purchase(uuid.UUID(purchase_id), principal.tenant_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Not found"}})
    return row


@router.post("/api/telephony/numbers/{number_id}/assign")
async def assign_number(
    number_id: str,
    body: AssignNumberBody,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    require_subscriber_permission(principal, "app.telephony.write")
    workspace_tid = subscriber_workspace_tenant_id(principal)
    try:
        number_uuid = uuid.UUID(number_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "invalid_number_id", "message": "Invalid phone line id"}},
        )
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database required")
    async with factory() as session:
        pn = await session.get(PhoneNumber, number_uuid)
        if pn is None or pn.tenant_id != workspace_tid or pn.released_at is not None:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Not found"}})
        if pn.status not in ("active", "pending"):
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "number_not_assignable", "message": "Number is not active"}},
            )
        agent_id = (body.agentId or "").strip()
        if not agent_id:
            pn.agent_id = None
            await session.commit()
            return {"ok": True, "agentId": None}
        agent = await session.get(Agent, uuid.UUID(agent_id))
        if agent is None or agent.tenant_id != workspace_tid:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})
        pn.agent_id = agent.agent_id
        await session.commit()
    return {"ok": True, "agentId": str(agent.agent_id)}


@router.put("/api/telephony/numbers/{number_id}/routing")
async def update_routing(
    number_id: str,
    body: RoutingBody,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    require_subscriber_permission(principal, "app.telephony.write")
    workspace_tid = subscriber_workspace_tenant_id(principal)
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database required")
    async with factory() as session:
        pn = await session.get(PhoneNumber, uuid.UUID(number_id))
        if pn is None or pn.tenant_id != workspace_tid:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Not found"}})
        if body.agentId is not None:
            if body.agentId:
                agent = await session.get(Agent, uuid.UUID(body.agentId))
                if agent is None or agent.tenant_id != workspace_tid:
                    raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})
                pn.agent_id = agent.agent_id
            else:
                pn.agent_id = None
        if body.inboundEnabled is not None:
            pn.inbound_enabled = body.inboundEnabled
        if body.outboundEnabled is not None:
            pn.outbound_enabled = body.outboundEnabled
        await session.commit()
    return {"ok": True}


@router.get("/api/telephony/contacts")
async def list_contacts(principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    factory = get_session_factory()
    if factory is None:
        return {"contacts": []}
    async with factory() as session:
        result = await session.execute(
            select(TelephonyContact).where(TelephonyContact.tenant_id == principal.tenant_id)
        )
        return {
            "contacts": [
                {"contactId": str(c.contact_id), "name": c.name, "phone": c.phone, "notes": c.notes}
                for c in result.scalars()
            ]
        }


@router.post("/api/telephony/contacts")
async def create_contact(body: ContactBody, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    require_subscriber_permission(principal, "app.telephony.write")
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database required")
    from datetime import datetime, timezone

    async with factory() as session:
        row = TelephonyContact(
            tenant_id=principal.tenant_id,
            name=body.name.strip(),
            phone=body.phone.strip(),
            notes=body.notes,
            created_at=datetime.now(timezone.utc),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return {"ok": True, "contactId": str(row.contact_id)}


@router.get("/api/calls/{call_id}")
async def get_call_detail(call_id: str, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    require_subscriber_permission(principal, "app.calls.read")
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Not found"}})
    try:
        call_uuid = uuid.UUID(call_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "invalid_call_id", "message": "Invalid call id"}},
        )
    async with factory() as session:
        row = await session.get(Call, call_uuid)
        if row is None or row.tenant_id != principal.tenant_id:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Not found"}})
        from server.call.call_status import status_for_record

        record = {
            "direction": row.direction,
            "duration_sec": row.duration_sec,
            "end_reason": row.end_reason,
            "disposition": row.disposition,
            "ended_at": row.ended_at,
        }
        return {
            "callId": str(row.call_id),
            "agentId": str(row.agent_id),
            "direction": row.direction,
            "channel": row.channel,
            "status": row.status or status_for_record(record),
            "startedAt": row.started_at.isoformat(),
            "endedAt": row.ended_at.isoformat() if row.ended_at else None,
            "durationSec": row.duration_sec,
            "disposition": row.disposition,
            "endReason": row.end_reason,
        }


class CallbackBody(BaseModel):
    """Call a missed caller back. Any field may be omitted; we infer where safe."""

    toE164: str | None = None
    agentId: str | None = None
    fromE164: str | None = None
    dialRequestId: str | None = None
    mode: str = Field("manual", max_length=24)

    @model_validator(mode="before")
    @classmethod
    def reject_stack_fields(cls, data):
        if isinstance(data, dict):
            for key in ("stackOverride", "stack_override", "tier", "pipeline"):
                if key in data:
                    raise ValueError(f"{key} not allowed for subscriber calls")
        return data


@router.post("/api/calls/{call_id}/callback")
async def call_back(
    call_id: str,
    body: CallbackBody,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    """Re-dial a missed caller using the same outbound path as a manual call.

    Accepts either a connected call id or a ringing-attempt id, so the Missed tab
    and the call detail drawer share one action.
    """
    require_subscriber_permission(principal, "app.telephony.write")
    allowed, retry = _outbound_limiter.allow(f"callback:{principal.tenant_id}")
    if not allowed:
        raise_rate_limited(retry, "Callback rate limit reached. Wait and try again.")
    return await request_callback(
        principal,
        call_id=call_id,
        to_e164=body.toE164,
        agent_id=body.agentId,
        from_e164=body.fromE164,
        dial_request_id=body.dialRequestId,
        mode=body.mode,
    )


@router.get("/api/calls/{call_id}/callbacks")
async def call_callbacks(
    call_id: str,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    """Callback history for one call — who tried to call back, and whether it connected."""
    require_subscriber_permission(principal, "app.calls.read")
    return {"callbacks": await list_callbacks(principal, call_id=call_id)}


@router.patch("/api/telephony/contacts/{contact_id}")
async def patch_contact(
    contact_id: str,
    body: ContactBody,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    require_subscriber_permission(principal, "app.telephony.write")
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database required")
    async with factory() as session:
        row = await session.get(TelephonyContact, uuid.UUID(contact_id))
        if row is None or row.tenant_id != principal.tenant_id:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Not found"}})
        row.name = body.name.strip()
        row.phone = body.phone.strip()
        row.notes = body.notes
        await session.commit()
    return {"ok": True}


@router.post("/api/telephony/numbers/{number_id}/release")
async def release_number(number_id: str, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    require_subscriber_permission(principal, "app.telephony.write")
    from server.services.saas.number_inventory import move_to_inventory
    from server.services.saas.activity_log import record_event

    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database required")
    workspace_tid = subscriber_workspace_tenant_id(principal)
    async with factory() as session:
        pn = await session.get(PhoneNumber, uuid.UUID(number_id))
        if pn is None or pn.tenant_id != workspace_tid or pn.released_at is not None:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Not found"}})
        e164 = pn.e164
        telnyx_id = pn.telnyx_number_id
        plivo_id = pn.plivo_number_id
        nid = pn.id
    # Return the DID to the admin inventory pool — available to buy again.
    moved = await move_to_inventory(
        number_id=nid,
        e164=e164,
        telnyx_number_id=telnyx_id,
        plivo_number_id=plivo_id,
    )
    await record_event(
        action="number.released",
        resource_type="phone_number",
        resource_id=str(nid),
        actor=principal.email or str(principal.user_id),
        tenant_id=workspace_tid,
        payload={"e164": e164, "provider": "vobiz" if plivo_id else "telnyx"},
        source="subscriber",
    )
    return {"ok": True, "inventory": moved}


@router.delete("/api/telephony/contacts/{contact_id}")
async def delete_contact(contact_id: str, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    require_subscriber_permission(principal, "app.telephony.write")
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database required")
    async with factory() as session:
        row = await session.get(TelephonyContact, uuid.UUID(contact_id))
        if row is None or row.tenant_id != principal.tenant_id:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Not found"}})
        await session.delete(row)
        await session.commit()
    return {"ok": True}
