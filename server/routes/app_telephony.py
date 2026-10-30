"""Subscriber telephony API (PRD-05, PRD-04)."""
from __future__ import annotations

import uuid
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import or_, select

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
    # Integrations attached to this call ([{app, mode}]); None keeps agent defaults.
    integrations: list[dict] | None = Field(None, max_length=12)

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
    contact = None
    if body.integrations:
        from server.services.call_integrations import SelectionError, validate_selection

        try:
            selection = await validate_selection(
                str(subscriber_workspace_tenant_id(principal)), body.agentId, body.integrations,
            )
        except SelectionError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail()) from None
        if selection:
            # Travels with the call's contact into the ledger meta, so tool
            # discovery, execution and post-call dispatch read the same set.
            contact = {"integration_selection": selection}
    return await subscriber_outbound(
        principal,
        agent_id=body.agentId,
        from_e164=body.fromE164,
        to_e164=body.toE164,
        dial_request_id=body.dialRequestId,
        contact=contact,
    )


@router.post("/api/calls/outbound")
async def calls_outbound_alias(body: OutboundCallBody, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    return await telephony_outbound(body, principal)


@router.get("/api/telephony/provider")
async def telephony_provider_info(principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    """Return backend-configured active telephony provider details so frontend dynamically aligns."""
    from server.services.saas.platform_admins import is_platform_admin_email
    from server.services.telephony import active_telephony_provider
    from server.services.telephony_status import all_provider_status

    active = active_telephony_provider()
    statuses = await all_provider_status()
    active_details = next((s for s in statuses if s.get("id") == active), {})
    is_admin = is_platform_admin_email(principal.email)

    if not is_admin:
        # Tenants and standard subscribers receive generalized, vendor-neutral telemetry
        return {
            "activeProvider": "direct_voice",
            "activeLabel": "Enterprise Voice Network",
            "ready": bool(active_details.get("ready")),
            "enabled": bool(active_details.get("enabled")),
            "phoneNumber": None,
            "supportedProviders": ["direct_voice"],
            "providers": [
                {
                    "id": "direct_voice",
                    "label": "Enterprise Voice Network",
                    "enabled": bool(active_details.get("enabled")),
                    "ready": bool(active_details.get("ready")),
                    "phoneNumber": None,
                }
            ],
        }

    # Platform administrators see sanitized multi-carrier availability (without exposing raw secret keys or URLs)
    return {
        "activeProvider": active,
        "activeLabel": active_details.get("label") or active.title(),
        "ready": bool(active_details.get("ready")),
        "enabled": bool(active_details.get("enabled")),
        "phoneNumber": active_details.get("phone_number"),
        "supportedProviders": ["telnyx", "vobiz"],
        "providers": [
            {
                "id": s.get("id"),
                "label": s.get("label"),
                "enabled": s.get("enabled"),
                "ready": s.get("ready"),
                "phoneNumber": s.get("phone_number"),
                "balance": s.get("balance"),
            }
            for s in statuses
        ],
    }


class SwitchTelephonyProviderBody(BaseModel):
    provider: str = Field(..., pattern="^(telnyx|vobiz)$")


@router.post("/api/telephony/provider")
async def telephony_set_provider(
    body: SwitchTelephonyProviderBody,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    from server.services.saas.platform_admins import require_platform_admin_email
    require_platform_admin_email(principal.email)

    from server.services.dev_secrets_store import dev_secrets_store

    enable_key = f"enable_{body.provider}"
    dev_secrets_store.update({
        "telephony_provider": body.provider,
        enable_key: True,
    })
    return {"ok": True, "activeProvider": body.provider}



@router.get("/api/telephony/voice-options")
async def telephony_voice_options(
    response: Response,
    language: str = "te-IN",
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    """Subscriber-safe voice list for the production phone AI stack (no dev stack UI)."""
    # Only languages the platform offers at creation, so the settings tab cannot
    # be used to sidestep the admin enablement list.
    from server.services.saas.platform_languages import language_options
    from server.services.saas.platform_phone_stack import resolve_platform_phone_stack

    languages = language_options()
    phone_stack = await resolve_platform_phone_stack(language)
    llm = phone_stack.get("llm") if isinstance(phone_stack.get("llm"), dict) else {}
    from server.realtime.models import is_gemini_live_voice_model

    active_voice_provider = str(llm.get("provider") or "gemini").strip().lower()
    if is_gemini_live_voice_model(str(llm.get("model") or "")):
        active_voice_provider = "gemini"
    if active_voice_provider not in {"openai", "gemini"}:
        active_voice_provider = "gemini"
    voices = phone_voice_catalog()
    if active_voice_provider != "gemini":
        voices = [voice for voice in voices if voice.get("provider") != "gemini"]
    voices = [
        {**voice, "previewUrl": "/api/telephony/voice-preview/live?" + urlencode(
            {"voiceId": voice.get("id"), "language": language}
        )}
        if voice.get("provider") == active_voice_provider else voice
        for voice in voices
    ]
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    rv = phone_stack.get("realtime_voice") if isinstance(phone_stack.get("realtime_voice"), dict) else {}
    return {
        "stackLabel": "Live phone AI",
        "stackDescription": "Same voice engine for incoming calls, outgoing calls, and browser practice calls.",
        "activeVoiceProvider": active_voice_provider,
        "activeModel": str(llm.get("model") or ""),
        "defaultVoiceId": str(rv.get("voice") or "te-in-csagent-5"),
        "voices": voices,
        "languages": languages,
    }


class VoicePreviewBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=400)
    voiceId: str | None = Field(None, max_length=64)
    language: str | None = Field(None, max_length=32)
    speed: float | None = Field(None, ge=0.5, le=2.0)
    tier: str | None = Field(None, max_length=32)


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
    from server.auth.rbac import role_has_permission
    if not (
        role_has_permission(principal.role, "app.agents.write")
        or role_has_permission(principal.role, "app.telephony.write")
        or role_has_permission(principal.role, "app.billing.write")
    ):
        raise HTTPException(status_code=403, detail={"error": {"code": "auth_error", "message": "Permission denied"}})
    from server.services.saas.voice_preview import VoicePreviewRateLimited, synthesize_preview

    try:
        from server.services.saas.platform_phone_stack import resolve_platform_phone_stack
        from server.services.saas.voice_stack_profiles import lookup_cached_voice_alias, resolve_voice_alias

        raw_voice_id = getattr(body, "voiceId", None)
        raw_tier = getattr(body, "tier", None)
        raw_lang = getattr(body, "language", None)
        raw_speed = getattr(body, "speed", None)

        alias_match = lookup_cached_voice_alias(raw_voice_id or "")
        if not alias_match and raw_voice_id and raw_voice_id.startswith("voc_"):
            alias_match = await resolve_voice_alias(raw_voice_id)

        requested_tier = (raw_tier or (alias_match.get("tier") if alias_match else None) or "").strip().lower()
        effective_voice_id = (alias_match.get("providerVoiceId") if alias_match else None) or raw_voice_id

        if alias_match and alias_match.get("provider"):
            provider = str(alias_match.get("provider"))
            model = alias_match.get("model")
        elif requested_tier:
            from server.services.dev_runtime import effective_app_environment
            from server.services.saas.voice_stack_profiles import load_profile_records

            records = await load_profile_records(effective_app_environment(), (requested_tier,))
            profile = (records.get(requested_tier) or {}).get("profile") or {}
            matches = [(model_row, voice) for engine in profile.get("engines", []) for model_row in engine.get("models", [])
                for voice in model_row.get("voices", []) if effective_voice_id in {voice.get("id"), voice.get("providerVoiceId")}
                and raw_lang in voice.get("languages", [])]
            if len(matches) != 1:
                raise ValueError("voice_not_in_active_catalog")
            selected_model, selected_voice = matches[0]
            provider, model = selected_model["provider"], selected_model["model"]
            effective_voice_id = selected_voice["providerVoiceId"]
        else:
            phone_stack = await resolve_platform_phone_stack(raw_lang or "te-IN")
            llm = phone_stack.get("llm") if isinstance(phone_stack.get("llm"), dict) else {}
            realtime_voice = phone_stack.get("realtime_voice") if isinstance(phone_stack.get("realtime_voice"), dict) else {}
            provider = str(llm.get("provider") or "gemini")
            model = str(llm.get("model") or "")
            if not effective_voice_id:
                effective_voice_id = realtime_voice.get("voice")

        result = await synthesize_preview(
            body.text,
            voice_id=effective_voice_id,
            language=raw_lang,
            speed=raw_speed,
            provider=provider,
            model=model,
            tier=requested_tier or None,
        )
    except VoicePreviewRateLimited as exc:
        raise HTTPException(status_code=429, headers={"Retry-After": str(exc.retry_after)}, detail={
            "error": {"code": "voice_preview_rate_limited", "message": "Voice generation is temporarily rate limited. Stored voice samples remain available; try this uncached sample again later."}
        }) from None
    except ValueError as exc:
        code = str(exc)
        message = "Nothing to preview." if code == "empty_preview_text" else "The selected voice is not available in the active provider catalog."
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": code, "message": message}},
        ) from None
    except Exception as exc:
        logger.warning("[VOICE] preview failed provider=%s error=%s", str(locals().get("llm", {}).get("provider") or "gemini"), type(exc).__name__)
        error_text = str(exc).casefold()
        message = "Could not reach the voice service. Check the voice configuration."
        if ("denied access" in error_text and ("project" in error_text or "1008" in error_text)) or "permission_denied" in error_text:
            message = (
                "Google denied this project access to Gemini voice generation. "
                "Check Gemini API access for this Google project or contact Google support."
            )
        elif "api key is not configured" in error_text:
            message = "Gemini is the active phone voice stack, but the platform has not configured its API access."
        raise HTTPException(
            status_code=502,
            detail={
                "error": {
                    "code": "voice_preview_unavailable",
                    "message": message,
                }
            },
        ) from None
    public_label = (alias_match.get("label") if alias_match else None) or result.get("label") or "Voice 1"
    return Response(
        content=result["audio"],
        media_type="audio/wav",
        headers={
            "X-Voice-Name": public_label,
            "X-Voice-Label": public_label,
            "X-Voice-Model": "Enterprise Voice Engine",
            "X-Voice-Cache": "hit" if result.get("cacheHit") else "miss",
            "Cache-Control": "private, max-age=86400" if result.get("cacheable") else "no-store",
        },
    )


@router.get("/api/telephony/voice-preview/catalog")
async def catalog_voice_preview(
    voiceId: str = Query(..., min_length=4, max_length=64),
    language: str = Query(default="en-IN", min_length=2, max_length=16),
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    """Serve the stored sample for one opaque public catalog voice.

    Samples are generated once per voice/language with the server's own greeting
    text, then served from the disk cache so repeat plays cost no provider call.
    """
    from server.auth.rbac import role_has_permission
    if not (
        role_has_permission(principal.role, "app.agents.write")
        or role_has_permission(principal.role, "app.telephony.write")
        or role_has_permission(principal.role, "app.billing.write")
    ):
        raise HTTPException(status_code=403, detail={"error": {"code": "auth_error", "message": "Permission denied"}})
    from server.services.saas.voice_preview import VoicePreviewRateLimited, synthesize_catalog_preview

    try:
        result = await synthesize_catalog_preview(voiceId, language)
    except VoicePreviewRateLimited as exc:
        raise HTTPException(status_code=429, headers={"Retry-After": str(exc.retry_after)}, detail={
            "error": {"code": "voice_preview_rate_limited", "message": "Voice generation is temporarily rate limited. Try this sample again later."}
        }) from None
    except ValueError as exc:
        code = str(exc)
        if code == "unsupported_language":
            raise HTTPException(status_code=422, detail={
                "error": {"code": code, "message": "Choose a supported agent language."}
            }) from None
        raise HTTPException(status_code=404, detail={
            "error": {"code": "voice_not_available", "message": "This voice sample is not available in the current catalog."}
        }) from None
    except Exception as exc:
        logger.warning("[VOICE] catalog preview failed error=%s", type(exc).__name__, exc_info=True)
        raise HTTPException(status_code=502, detail={
            "error": {"code": "voice_preview_unavailable", "message": "The voice sample could not be prepared. Try again later."}
        }) from None
    label = str(result.get("label") or "Voice")
    return Response(
        content=result["audio"],
        media_type="audio/wav",
        headers={
            "X-Voice-Name": label,
            "X-Voice-Label": label,
            "X-Voice-Model": "Enterprise Voice Engine",
            "X-Voice-Cache": "hit" if result.get("cacheHit") else "miss",
            "Cache-Control": "private, max-age=86400",
        },
    )


@router.get("/api/telephony/voice-preview/live")
async def live_voice_preview(
    voiceId: str = Query(..., min_length=1, max_length=64),
    language: str = Query(default="te-IN", min_length=2, max_length=16),
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    """Serve the stored sample for one voice of the live phone stack."""
    from server.auth.rbac import role_has_permission
    if not (
        role_has_permission(principal.role, "app.agents.write")
        or role_has_permission(principal.role, "app.telephony.write")
        or role_has_permission(principal.role, "app.billing.write")
    ):
        raise HTTPException(status_code=403, detail={"error": {"code": "auth_error", "message": "Permission denied"}})
    from server.services.saas.voice_preview import VoicePreviewRateLimited, synthesize_live_preview

    try:
        result = await synthesize_live_preview(voiceId, language)
    except VoicePreviewRateLimited as exc:
        raise HTTPException(status_code=429, headers={"Retry-After": str(exc.retry_after)}, detail={
            "error": {"code": "voice_preview_rate_limited", "message": "Voice generation is temporarily rate limited. Try this sample again later."}
        }) from None
    except ValueError as exc:
        code = str(exc)
        if code == "unsupported_language":
            raise HTTPException(status_code=422, detail={
                "error": {"code": code, "message": "Choose a supported agent language."}
            }) from None
        raise HTTPException(status_code=404, detail={
            "error": {"code": "voice_not_available", "message": "This voice sample is not available in the current catalog."}
        }) from None
    except Exception as exc:
        logger.warning("[VOICE] live preview failed error=%s", type(exc).__name__, exc_info=True)
        raise HTTPException(status_code=502, detail={
            "error": {"code": "voice_preview_unavailable", "message": "The voice sample could not be prepared. Try again later."}
        }) from None
    return Response(
        content=result["audio"],
        media_type="audio/wav",
        headers={
            "X-Voice-Name": "Voice",
            "X-Voice-Label": "Voice",
            "X-Voice-Model": "Enterprise Voice Engine",
            "X-Voice-Cache": "hit" if result.get("cacheHit") else "miss",
            "Cache-Control": "private, max-age=86400",
        },
    )


def _rent_fields(n, purchased_at, renewals_on: bool, monthly_usd: float, monthly_inr: float) -> dict:
    """Next renewal of a number's monthly rent (only wallet-billed numbers pay rent)."""
    from server.services.saas.number_rental import next_renewal_at

    billed = n.billing_source == "wallet" and purchased_at is not None
    return {
        "rentBilled": billed,
        "renewalEnabled": bool(billed and renewals_on),
        "nextRenewalAt": next_renewal_at(purchased_at).isoformat() if billed and renewals_on else None,
        # The price in force now; an admin change before that date would apply instead.
        "nextRenewalUsd": monthly_usd if billed and renewals_on else None,
        "nextRenewalInr": monthly_inr if billed and renewals_on else None,
    }


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
        from server.services.saas.billing_rates import load_current_rates
        from server.services.saas.platform_admins import is_platform_admin_email
        from server.services.telephony import active_telephony_provider

        is_admin = is_platform_admin_email(principal.email)
        active_prov = active_telephony_provider()
        rates = await load_current_rates()
        monthly_usd = round(rates["did_monthly_usd_cents"] / 100.0, 2)
        monthly_inr = round(rates["did_monthly_inr_paise"] / 100.0, 2)
        phone_rows = list(result.scalars())
        # Wallet-billed numbers renew monthly on their purchase anniversary at the
        # admin "Phone number monthly rent" in force on that date.
        from server.db.models.saas_models import NumberPurchase
        from server.services.saas.number_rental import renewal_enabled

        purchase_ids = [n.purchase_id for n in phone_rows if n.purchase_id and n.billing_source == "wallet"]
        purchased_at: dict = {}
        if purchase_ids:
            purchased_at = dict(
                (
                    await session.execute(
                        select(NumberPurchase.id, NumberPurchase.created_at).where(NumberPurchase.id.in_(purchase_ids))
                    )
                ).all()
            )
        renewals_on = renewal_enabled()
        for n in phone_rows:
            e164 = n.e164 or ""
            prov = "telnyx" if (n.telnyx_number_id or e164 == "+13526146416") else "vobiz"
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
                    **_rent_fields(n, purchased_at.get(n.purchase_id), renewals_on, monthly_usd, monthly_inr),
                    "country": country,
                    "provider": prov if is_admin else "direct_voice",
                    "telnyxNumberId": n.telnyx_number_id if is_admin else None,
                    "carrierNumberId": getattr(n, "carrier_number_id", None) if is_admin else None,
                }
            )

        from server.services.saas.platform_admins import is_dev_tester_email
        from server.services.saas.telephony_orchestrator import dev_sandbox_e164

        if not numbers and is_dev_tester_email(principal.email):
            sandbox = dev_sandbox_e164()
            if sandbox:
                numbers.append(
                    {
                        "id": "platform-test-line",
                        "e164": sandbox,
                        "status": "active",
                        "agentId": None,
                        "inboundEnabled": True,
                        "outboundEnabled": True,
                        "billingSource": "platform",
                        "monthlyCost": 0.0,
                        "monthlyInr": 0.0,
                        "country": "IN" if sandbox.startswith("+91") else ("US" if sandbox.startswith("+1") else None),
                        "provider": "direct_voice",
                    }
                )
    return {"numbers": numbers, "activeProvider": active_prov if is_admin else "direct_voice"}


@router.get("/api/telephony/numbers/search")
async def search_numbers(
    country: str | None = None,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    require_subscriber_permission(principal, "app.telephony.write")
    from server.services.telnyx_client import TelnyxClient
    from server.services.saas.telephony_countries import normalize_buy_country
    from server.services.saas.billing_rates import load_current_rates
    from server.services.saas.number_inventory import list_inventory_for_sale
    from server.services.saas.platform_admins import is_platform_admin_email
    from server.services.telephony import active_telephony_provider

    is_admin = is_platform_admin_email(principal.email)
    active_prov = active_telephony_provider()
    country_default = "IN" if active_prov == "vobiz" else "US"
    country = normalize_buy_country(country or country_default, default=country_default)
    rates = await load_current_rates()
    # Chargeable platform rate — must match wallet debit and the buy-modal header.
    monthly_usd = round(rates["did_monthly_usd_cents"] / 100.0, 2)
    monthly_inr = round(rates["did_monthly_inr_paise"] / 100.0, 2)

    priced: list[dict] = []
    seen: set[str] = set()

    # Pre-seed seen with all numbers already assigned or unavailable in the system
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "number_inventory_unavailable", "message": "Phone number inventory is temporarily unavailable."}},
        )
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

        from server.db.models.saas_models import NumberPurchase
        # Paid/unconfirmed orders remain reserved even after the checkout TTL.
        now_utc = datetime.now(timezone.utc)
        res_rows = (
            await session.execute(
                select(NumberReservation.e164).where(or_(
                    NumberReservation.expires_at > now_utc,
                    NumberReservation.purchase_id.in_(select(NumberPurchase.id).where(
                        NumberPurchase.status.in_(["paid", "provisioning", "needs_attention"]),
                    )),
                ))
            )
        ).scalars().all()
        for r_e164 in res_rows:
            if r_e164:
                seen.add(str(r_e164).strip())

    # Telnyx keeps the platform-owned pool path. Vobiz inventory is sourced
    # directly from its unassigned inventory endpoint below; local/demo rows are
    # never used as a fallback for Vobiz availability.
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
                    "provider": "direct_voice" if not is_admin else item.get("source", active_prov),
                    "telnyxNumberId": item.get("telnyxNumberId") if is_admin else None,
                }
            )

    try:
        if active_prov == "vobiz":
            from server.services.vobiz_client import VobizClient
            # Fetch a wider page so assigned numbers/reservations filtered below
            # do not make the tenant catalog look empty prematurely.
            numbers = await VobizClient().search_available_numbers(country=country, limit=100)
        else:
            numbers = await TelnyxClient().search_available_numbers(country=country, limit=10)
    except Exception as exc:
        logger.warning(
            "%s catalog search failed country=%s error_type=%s",
            active_prov,
            country,
            type(exc).__name__,
        )
        if active_prov == "vobiz":
            raise HTTPException(
                status_code=502,
                detail={
                    "error": {
                        "code": "provider_inventory_unavailable",
                        "message": "Phone number inventory is temporarily unavailable.",
                    }
                },
            ) from None
        numbers = []
    for row in numbers:
        item = dict(row) if isinstance(row, dict) else {"e164": str(row)}
        e164 = str(item.get("e164") or item.get("phone_number") or "")
        if e164 and e164 in seen:
            continue
        if active_prov == "vobiz":
            if (
                str(item.get("status") or "").strip().lower() != "active"
                or any(
                    str(item.get(flag) or "").strip().lower() in {"1", "true", "yes", "on"}
                    for flag in ("is_trial_number", "is_test_number", "test_mode", "mock")
                )
                or item.get("auth_id") not in (None, "")
            ):
                continue
        if e164:
            seen.add(e164)
        item["monthlyInr"] = monthly_inr
        item["monthlyUsd"] = monthly_usd
        item["fee"] = monthly_usd
        item["country"] = country
        item["source"] = active_prov if is_admin else "direct_voice"
        item["provider"] = active_prov if is_admin else "direct_voice"
        if not is_admin and "telnyxNumberId" in item:
            item["telnyxNumberId"] = None
        if not is_admin:
            for internal_key in ("id", "account_id", "auth_id", "carrierNumberId", "providerNumberId"):
                item.pop(internal_key, None)
        priced.append(item)
        if len(priced) >= 10:
            break
    return {
        "numbers": priced,
        "country": country,
        "didMonthlyInr": monthly_inr,
        "didMonthlyUsd": monthly_usd,
        "activeProvider": active_prov if is_admin else "direct_voice",
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
    country: str | None = Query(None, description="Ignored; the checklist is India-only"),
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    """India compliance obligations for the agent settings screen.

    Advisory metadata only. It is not consulted by the call path — nothing here
    changes how a call is placed.
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
        merged = merge_agent_compliance({"acknowledged": body.acknowledged})
        current["compliance"] = {"country": merged["country"], "acknowledged": merged["acknowledged"]}
        row.voice_settings = current
        await session.commit()
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
    """Stored acknowledgements merged over the India checklist."""
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
        return merge_agent_compliance(saved)


@router.post("/api/telephony/buy")
async def buy_number(
    body: BuyNumberBody,
    request: Request,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    require_subscriber_permission(principal, "app.billing.write")
    from server.services.telephony import active_telephony_provider
    if active_telephony_provider() != "vobiz":
        from server.services.saas.kyc_gate import assert_kyc_approved
        await assert_kyc_approved(principal, action="buy a phone number")
    from server.services.saas.activity_log import record_event

    allowed, retry = _buy_limiter.allow(f"buy:{principal.tenant_id}")
    if not allowed:
        raise_rate_limited(retry, "Number purchase rate limit reached.")
    pay = (body.payMethod or "wallet").strip().lower()
    # Every attempt is logged, including the ones that stop at the KYC gate. A
    # refused purchase is the thing an operator needs to see, and it never reaches
    # the purchase service — so logging only there would hide every refusal.
    try:
        if pay == "stripe":  # stripe payment removed
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "stripe_removed",
                        "message": "Card checkout via Stripe has been removed. Please use wallet credits to buy a number.",
                    }
                },
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
        status = _purchase_error_status(code)
        await _log_purchase_refusal_code(request, principal, body, pay, code, status)
        messages = {
            "stripe_removed": "Card checkout is no longer supported. Use wallet credits to buy a number.",
            "stripe_not_configured": "Card checkout is not supported. Use wallet credits to buy a number.",
            "verification_required": "Verify your email before buying a number.",
            "kyc_required": "Verify your identity before buying a phone number.",
            "voice_kyc_required": "Complete phone service verification before buying a number.",
            "carrier_balance_exhausted": (
                "Phone numbers are temporarily unavailable. Your wallet was not charged."
            ),
            "carrier_not_configured": "Telephony line service is being updated. Please contact support.",
            "carrier_inventory_unavailable": "Phone number inventory is temporarily unavailable. Your wallet was not charged.",
            "carrier_order_failed": "Unable to complete number order with provider. Your wallet was not charged.",
            "number_reserved": "This number is reserved by another checkout. Try a different number.",
            "number_unavailable": "This number is no longer available.",
            "number_limit": "This workspace has reached its phone number limit.",
            "tenant_not_found": "Workspace not found.",
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
    "voice_kyc_required": "phone service verification not approved",
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
    """One mapping for the HTTP response and the audit row, so they never disagree."""
    if code in ("verification_required", "kyc_required", "voice_kyc_required"):
        return 403
    if code in ("stripe_not_configured", "stripe_removed"):
        return 400
    if code == "insufficient_balance":
        return 402
    if code in ("number_reserved", "number_unavailable"):
        return 409
    if code == "tenant_not_found":
        return 404
    if code == "carrier_order_failed":
        return 502
    if code in ("carrier_balance_exhausted", "carrier_not_configured", "carrier_inventory_unavailable"):
        # Our carrier account or provider, not the customer's problem.
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


def _parse_uuid_or_404(raw: str | None) -> uuid.UUID:
    """Malformed ids are indistinguishable from someone else's: 404, never 500."""
    try:
        return uuid.UUID(str(raw or ""))
    except ValueError:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Not found"}}) from None


@router.get("/api/telephony/purchases/{purchase_id}")
async def get_purchase_status(purchase_id: str, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    row = await get_purchase(_parse_uuid_or_404(purchase_id), principal.tenant_id)
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
        agent = await session.get(Agent, _parse_uuid_or_404(agent_id))
        if agent is None or agent.tenant_id != workspace_tid:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})
        pn.agent_id = agent.agent_id
        if pn.status in ("active", "pending"):
            pn.outbound_enabled = True
            pn.inbound_enabled = True
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
        pn = await session.get(PhoneNumber, _parse_uuid_or_404(number_id))
        if pn is None or pn.tenant_id != workspace_tid or pn.released_at is not None:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Not found"}})
        if pn.status not in ("active", "pending") and (body.inboundEnabled or body.outboundEnabled):
            # A suspended (unpaid) or releasing line cannot be switched back on
            # from the console; paying the rental or support restores it.
            raise HTTPException(
                status_code=409,
                detail={"error": {"code": "number_not_active", "message": "This line is not active."}},
            )
        if body.agentId is not None:
            if body.agentId:
                agent = await session.get(Agent, _parse_uuid_or_404(body.agentId))
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


class CallbackRequestStatusBody(BaseModel):
    status: str = Field(pattern="^(converted|dismissed)$")


@router.get("/api/callback-requests")
async def callback_requests(
    agentId: str | None = Query(None, max_length=64),
    status: str = Query("requested"),
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),  # noqa: B008 -- FastAPI auth dependency.
):
    require_subscriber_permission(principal, "app.calls.read")
    from server.services.saas.callback_request_service import list_callback_requests

    return {"requests": await list_callback_requests(principal, agent_id=agentId, status=status)}


@router.patch("/api/callback-requests/{callback_id}")
async def patch_callback_request(
    callback_id: uuid.UUID, body: CallbackRequestStatusBody,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),  # noqa: B008 -- FastAPI auth dependency.
):
    require_subscriber_permission(principal, "app.telephony.write")
    from server.services.saas.callback_request_service import update_callback_request

    return await update_callback_request(principal, callback_id, body.status)


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
        pn = await session.get(PhoneNumber, _parse_uuid_or_404(number_id))
        if pn is None or pn.tenant_id != workspace_tid or pn.released_at is not None:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Not found"}})
        e164 = pn.e164
        telnyx_id = pn.telnyx_number_id
        carrier_id = getattr(pn, "carrier_number_id", None)
        nid = pn.id
    # Return the DID to the admin inventory pool — available to buy again.
    moved = await move_to_inventory(
        number_id=nid,
        expected_tenant_id=workspace_tid,
        e164=e164,
        telnyx_number_id=telnyx_id,
        carrier_number_id=carrier_id,
    )
    await record_event(
        action="number.released",
        resource_type="phone_number",
        resource_id=str(nid),
        actor=principal.email or str(principal.user_id),
        tenant_id=workspace_tid,
        payload={"e164": e164, "provider": "vobiz" if carrier_id else "telnyx"},
        source="subscriber",
    )
    # Tenant-scope Vobiz DIDs report "release_pending" during the carrier's
    # 24h cancellable cool-down; the console shows that state rather than "gone".
    return {"ok": True, "status": (moved or {}).get("status"), "inventory": moved}


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
