"""Vobiz HTTP Webhook Handlers — Answer XML, Fallback, Hangup & Recording Callbacks."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import math
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import Response

from server.config.env import get_settings
from server.config.urls import public_api_base, ws_public_base
from server.services.pstn_debug import log_pstn, mark
from server.services.vobiz_client import (
    VobizClient,
    vobiz_call_registry,
    vobiz_enabled,
    vobiz_stream_tokens,
)

logger = logging.getLogger(__name__)
router = APIRouter()


async def _parse_vobiz_payload(request: Request) -> dict[str, Any]:
    payload: dict[str, Any] = dict(request.query_params)
    content_type = request.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        try:
            body_json = await request.json()
            if isinstance(body_json, dict):
                payload.update(body_json)
        except Exception:
            pass
        return payload
    # Form data or URL-encoded (standard VoiceXML webhooks)
    try:
        form = await request.form()
        payload.update(dict(form))
        return payload
    except Exception:
        pass
    try:
        body = await request.body()
        if body:
            import json
            data = json.loads(body.decode("utf-8"))
            if isinstance(data, dict):
                payload.update(data)
    except Exception:
        pass
    return payload


def _build_vobiz_xml_response(stream_ws_url: str, recording_callback_url: str = "") -> Response:
    """Generate compliant VoiceXML instructing Vobiz to connect bidirectional WebSocket."""
    import html

    escaped_url = html.escape(stream_ws_url.strip(), quote=True)
    record = (f'<Record recordSession="true" fileFormat="mp3" maxLength="14400" timeout="14400" playBeep="false" redirect="false" '
              f'callbackUrl="{html.escape(recording_callback_url, quote=True)}" callbackMethod="POST" />') if recording_callback_url else ""
    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    {record}
    <Stream bidirectional="true" audioTrack="inbound" keepCallAlive="true" contentType="audio/x-l16;rate=16000">{escaped_url}</Stream>
    <Hangup />
</Response>"""
    return Response(content=xml_content, media_type="application/xml")


def _normalize_num(num: str) -> str:
    n = (num or "").strip()
    if not n:
        return ""
    digits = "".join(c for c in n if c.isdigit())
    if not digits:
        return n
    if n.startswith("+"):
        return f"+{digits}"
    if len(digits) == 10:
        return f"+91{digits}"
    if len(digits) == 11 and digits.startswith("0"):
        return f"+91{digits[1:]}"
    if len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}"
    return f"+{digits}"


async def _vobiz_callback_tenant_id(payload: dict[str, Any]) -> str | None:
    keys = (
        payload.get("CallUUID"), payload.get("call_uuid"), payload.get("CallId"),
        payload.get("RequestUUID"), payload.get("request_uuid"), payload.get("outbound_id"),
    )
    for key in keys:
        row = await asyncio.to_thread(vobiz_call_registry.get, str(key or "")) if key else None
        tenant_id = str((row or {}).get("vobiz_account_tenant_id") or (row or {}).get("tenant_id") or "").strip()
        if tenant_id:
            return tenant_id
    called = str(payload.get("To") or payload.get("called") or "").strip()
    if not called:
        return None
    from server.services.saas.telephony_profile import profile_for_number

    profile = await profile_for_number(called)
    if not profile:
        normalized = _normalize_num(called)
        if normalized and normalized != called:
            profile = await profile_for_number(normalized)
    tenant_id = str((profile or {}).get("vobiz_account_tenant_id") or (profile or {}).get("tenant_id") or "").strip()
    return tenant_id or None


def _signature_matches(auth_token: str, request: Request) -> bool:
    if not auth_token:
        return False
    base_url = public_api_base().rstrip("/") + request.url.path
    for version, separator in (("v3", "."), ("v2", "")):
        signature = request.headers.get(f"x-vobiz-signature-{version}")
        nonce = request.headers.get(f"x-vobiz-signature-{version}-nonce")
        if not signature or not nonce:
            continue
        message = f"{base_url}{separator}{nonce}".encode()
        expected = base64.b64encode(hmac.new(auth_token.encode(), message, hashlib.sha256).digest())
        if hmac.compare_digest(signature.encode(), expected):
            return True
    return False


async def _verify_vobiz_request(request: Request, payload: dict[str, Any]) -> None:
    """Accept parent or mapped tenant credentials, or a call-scoped bearer token."""
    settings = get_settings()
    from server.services.dev_secrets_store import dev_secrets_store

    auth_token = str(dev_secrets_store.effective_secret("vobiz_auth_token") or settings.vobiz_auth_token or "").strip()
    is_prod = str(getattr(settings, "app_environment", "") or "").lower() in ("production", "staging")
    signature_present = any(
        request.headers.get(f"x-vobiz-signature-{version}")
        or request.headers.get(f"x-vobiz-signature-{version}-nonce")
        for version in ("v2", "v3")
    )
    if _signature_matches(auth_token, request):
        return

    tenant_id = await _vobiz_callback_tenant_id(payload)
    child_token = ""
    if tenant_id:
        try:
            import uuid

            from server.services.saas.voice_kyc_service import vobiz_client_for_tenant

            child_client = await vobiz_client_for_tenant(uuid.UUID(tenant_id))
            child_token = str(child_client.cfg.get("auth_token") or "")
        except Exception as exc:
            logger.info("[VOBIZ] tenant callback lookup unavailable error_type=%s", type(exc).__name__)
    if child_token and _signature_matches(child_token, request):
        return

    # The signed media token is a separate, high-entropy call-scoped authenticator.
    passed_token = str(request.query_params.get("token") or payload.get("token") or "")
    if passed_token:
        token_meta = await asyncio.to_thread(vobiz_stream_tokens.peek, passed_token)
        call_uuid = str(payload.get("CallUUID") or payload.get("call_uuid") or payload.get("CallId") or "")
        if token_meta:
            expected_call = str(token_meta.get("call_uuid") or "")
            if call_uuid and expected_call and not expected_call.startswith("vobiz-") and call_uuid != expected_call:
                raise HTTPException(status_code=401, detail="Call token mismatch")
            return
        if request.url.path in {"/api/vobiz/hangup", "/api/vobiz/recording", "/api/vobiz/fallback"}:
            key = (payload.get("CallUUID") or payload.get("call_uuid") or payload.get("CallId")
                   or payload.get("RequestUUID") or payload.get("request_uuid") or payload.get("outbound_id"))
            record = await asyncio.to_thread(vobiz_call_registry.get, str(key)) if key else None
            expected = str((record or {}).get("webhook_token") or (record or {}).get("token") or "")
            if expected and hmac.compare_digest(passed_token.encode(), expected.encode()):
                return
        raise HTTPException(status_code=401, detail="Invalid stream token")

    header_token = str(
        request.headers.get("X-Vobiz-Auth-Token")
        or request.headers.get("X-Vobiz-Signature")
        or request.headers.get("Authorization", "").replace("Bearer ", "").replace("Basic ", "")
        or request.query_params.get("auth_token")
        or ""
    ).strip()
    if header_token:
        if auth_token and hmac.compare_digest(header_token.encode(), auth_token.encode()):
            return
        if child_token and hmac.compare_digest(header_token.encode(), child_token.encode()):
            return
        raise HTTPException(status_code=401, detail="Invalid auth token")

    if signature_present:
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    if is_prod or auth_token:
        logger.warning("[VOBIZ] Webhook rejected: missing authentication")
        raise HTTPException(status_code=401, detail="Unauthorized carrier webhook")


@router.post("/api/vobiz/answer")
@router.get("/api/vobiz/answer")
async def vobiz_answer(request: Request):
    """Primary Answer URL — triggered when a call starts on Vobiz."""
    payload = await _parse_vobiz_payload(request)
    await _verify_vobiz_request(request, payload)
    q = request.query_params

    # 1. Resolve token and identifiers
    passed_token = str(q.get("token") or payload.get("token") or "")
    token_meta = await asyncio.to_thread(vobiz_stream_tokens.peek, passed_token) if passed_token else None

    outbound_id = str(q.get("outbound_id") or payload.get("outbound_id") or "")
    request_uuid = str(
        payload.get("RequestUUID")
        or payload.get("request_uuid")
        or payload.get("ALegRequestUUID")
        or outbound_id
        or (token_meta or {}).get("request_uuid")
        or ""
    )
    call_uuid = str(
        payload.get("CallUUID")
        or payload.get("call_uuid")
        or payload.get("CallId")
        or payload.get("call_id")
        or request_uuid
        or uuid.uuid4()
    )
    from_number = str(payload.get("From") or payload.get("caller") or (token_meta or {}).get("from_number") or "")
    to_number = str(payload.get("To") or payload.get("called") or (token_meta or {}).get("to_number") or "")
    direction = str(payload.get("Direction") or (token_meta or {}).get("direction") or "inbound").lower()

    mark(call_uuid)
    log_pstn(
        "vobiz.answer_requested",
        call_uuid=call_uuid,
        request_uuid=request_uuid,
        from_=from_number,
        to=to_number,
        direction=direction,
        has_token=bool(token_meta),
    )

    # 2. Retrieve existing call context from registry or token
    local_reg: dict[str, Any] = {}
    if call_uuid:
        local_reg = await asyncio.to_thread(vobiz_call_registry.get, call_uuid) or {}
    if not local_reg and request_uuid:
        local_reg = await asyncio.to_thread(vobiz_call_registry.get, request_uuid) or {}
    if not local_reg and outbound_id:
        local_reg = await asyncio.to_thread(vobiz_call_registry.get, outbound_id) or {}

    agent_id: str | None = (token_meta or {}).get("agent_id") or local_reg.get("agent_id")
    tenant_id: str | None = (token_meta or {}).get("tenant_id") or local_reg.get("tenant_id")
    tier: str | None = (token_meta or {}).get("tier") or local_reg.get("tier")
    language: str | None = (token_meta or {}).get("language") or local_reg.get("language")
    stack_override: dict[str, Any] | None = (token_meta or {}).get("stack_override") or local_reg.get("stack_override")
    source_session_id: str | None = (token_meta or {}).get("source_session_id") or local_reg.get("source_session_id")

    # 3. If agent_id not yet known (inbound call or unmapped outbound), resolve via profile
    lookup_num = from_number if direction == "outbound" else to_number
    profile: dict[str, Any] | None = None
    if not agent_id and lookup_num:
        try:
            from server.services.saas.telephony_profile import profile_for_number

            profile = await profile_for_number(lookup_num)
            if not profile and lookup_num != _normalize_num(lookup_num):
                profile = await profile_for_number(_normalize_num(lookup_num))
            if profile:
                agent_id = str(profile.get("agent_id") or "")
                tenant_id = str(profile.get("tenant_id") or "")
        except Exception as e:
            logger.warning("[VOBIZ] agent lookup via profile failed: %s", e)

    account_scope = (token_meta or {}).get("vobiz_account_scope") or local_reg.get("vobiz_account_scope") or (profile or {}).get("vobiz_account_scope") or "platform"
    account_tenant_id = (token_meta or {}).get("vobiz_account_tenant_id") or local_reg.get("vobiz_account_tenant_id") or (profile or {}).get("vobiz_account_tenant_id") or tenant_id
    # This must precede transfers as well as media streaming. Browser redirects
    # and submitted documents never authorize a call.
    if account_scope == "tenant":
        try:
            from server.services.saas.voice_kyc_service import assert_voice_kyc_approved
            if not account_tenant_id:
                raise ValueError("Missing account owner")
            from server.db.connection import get_session_factory
            from server.db.models.entities import Tenant
            factory = get_session_factory()
            if factory is None:
                raise ValueError("Account database unavailable")
            async with factory() as session:
                tenant = await session.get(Tenant, uuid.UUID(str(account_tenant_id)))
                if tenant is None or tenant.status != "active":
                    raise ValueError("Account inactive")
            await assert_voice_kyc_approved(uuid.UUID(str(account_tenant_id)), action="receive a phone call")
        except Exception as exc:
            logger.warning("Phone call denied at verification gate error_type=%s", type(exc).__name__)
            return Response(content='<Response><Hangup /></Response>', media_type="application/xml")

    # 4b. Fail-closed quarantine enforcement: non-active tenants cannot receive or place calls
    if tenant_id:
        try:
            from server.db.connection import get_session_factory
            from server.db.models.entities import Tenant

            factory = get_session_factory()
            if factory is None:
                raise RuntimeError("Tenant storage unavailable")
            if factory:
                async with factory() as session:
                    t_row = await session.get(Tenant, uuid.UUID(tenant_id))
                    if t_row is None or t_row.status != "active" or t_row.deleted_at is not None:
                        log_pstn("vobiz.declined", call_uuid=call_uuid, reason="tenant_quarantined")
                        xml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Hangup reason="busy" />
</Response>"""
                        return Response(content=xml, media_type="application/xml")
        except Exception as e:
            logger.warning("Phone tenant check failed error_type=%s", type(e).__name__)
            return Response(content='<Response><Hangup /></Response>', media_type="application/xml")

    # 6. Check wallet balance if inbound payment wall is enabled
    settings = get_settings()
    if settings.pstn_enforce_wallet_on_inbound and tenant_id:
        try:
            from server.services.saas.billing_wallet_service import wallet_allows_inbound

            allowed = await wallet_allows_inbound(uuid.UUID(tenant_id))
            if not allowed:
                log_pstn("vobiz.declined", call_uuid=call_uuid, reason="insufficient_balance")
                xml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Speak>The service account has an insufficient wallet balance. Please top up your account.</Speak>
    <Hangup />
</Response>"""
                return Response(content=xml, media_type="application/xml")
        except Exception as e:
            logger.warning("Phone wallet check failed error_type=%s", type(e).__name__)
            return Response(content='<Response><Hangup /></Response>', media_type="application/xml")

    # 4. Inbound policy check (business hours, voicemail, transfer, decline)
    if direction == "inbound" and profile:
        try:
            from server.services.saas.telephony_profile import evaluate_inbound_policy

            decision = evaluate_inbound_policy(profile)
            if not decision.should_answer:
                log_pstn("vobiz.inbound.declined", call_uuid=call_uuid, reason=decision.reason)
                if decision.route == "transfer" and decision.transfer_number:
                    import html
                    xfer = html.escape(str(decision.transfer_number).strip(), quote=True)
                    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Dial>
        <Number>{xfer}</Number>
    </Dial>
</Response>"""
                    return Response(content=xml, media_type="application/xml")
                xml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Hangup />
</Response>"""
                return Response(content=xml, media_type="application/xml")
        except Exception as e:
            logger.warning("Phone policy check failed error_type=%s", type(e).__name__)
            return Response(content='<Response><Hangup /></Response>', media_type="application/xml")

    # 5. Handle unassigned numbers without cross-tenant agent leakage
    if not agent_id:
        if direction == "inbound":
            log_pstn("vobiz.inbound.unassigned", call_uuid=call_uuid, to=to_number)
            xml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Speak>This number is not assigned to an active voice assistant. Please check your configuration.</Speak>
    <Hangup />
</Response>"""
            return Response(content=xml, media_type="application/xml")
        else:
            log_pstn("vobiz.outbound.unassigned", call_uuid=call_uuid)
            xml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Speak>No agent is associated with this call.</Speak>
    <Hangup />
</Response>"""
            return Response(content=xml, media_type="application/xml")

    # Versioned composed selections use the same snapshot across channels.
    # Answer retries keep their admitted revision; legacy and Premium calls
    # retain their existing stack resolution path.
    if direction == "inbound" and not stack_override:
        try:
            from server.brain.agent_service import agent_service
            from server.services.saas.pstn_saas_stack import saas_stack_override_for_agent
            from server.services.saas.voice_stack_profiles import canonical_voice_tier

            if not tenant_id:
                raise ValueError("Missing inbound voice profile owner")
            agent = await agent_service.get_agent(str(agent_id), tenant_id=str(tenant_id))
            voice_settings = agent.get("voice_settings") or {}
            selected_tier = canonical_voice_tier(agent.get("default_tier") or "medium")
            if selected_tier in {"low", "medium"} and voice_settings.get("stackSelectionVersion") == 1:
                tier = selected_tier
                stack_override = await saas_stack_override_for_agent(agent)
                language = str(stack_override.get("language") or (agent.get("languages") or ["te-IN"])[0])
        except Exception as exc:
            logger.warning("Inbound voice profile unavailable error_type=%s", type(exc).__name__)
            return Response(content='<Response><Hangup /></Response>', media_type="application/xml")

    # 7. Create or update single-use stream token
    from server.call.billing_timing import utc_timestamp
    answered_at = utc_timestamp(payload.get("AnswerTime") or payload.get("answer_time"))
    admission_key = (token_meta or {}).get("admission_key") or local_reg.get("admission_key")
    admission_tenant_id = (token_meta or {}).get("admission_tenant_id") or local_reg.get("admission_tenant_id") or tenant_id
    if direction == "inbound" and tenant_id and not admission_key:
        from server.services.saas.call_admission import reserve, finish
        try:
            admission_key, _ = await reserve(uuid.UUID(str(tenant_id)), f"inbound:{call_uuid}",
                provider="vobiz", payload={"direction": "inbound", "agent": agent_id, "call": call_uuid})
            await finish(admission_key, uuid.UUID(str(tenant_id)), result={"ok": True, "call_control_id": call_uuid})
        except Exception as exc:
            logger.warning("Inbound call admission denied error_type=%s", type(exc).__name__)
            return Response(content='<Response><Hangup /></Response>', media_type="application/xml")
    if passed_token and token_meta:
        token = passed_token
        token_meta.update({
            "call_uuid": call_uuid,
            "request_uuid": request_uuid,
            "from_number": from_number,
            "to_number": to_number,
            "agent_id": agent_id,
            "tenant_id": tenant_id,
            "vobiz_account_scope": account_scope,
            "vobiz_account_tenant_id": account_tenant_id,
            "tier": tier,
            "language": language,
            "stack_override": stack_override,
            "direction": direction,
            "source_session_id": source_session_id,
            "provider": "vobiz",
            "answered_at": answered_at,
            "admission_key": admission_key,
            "admission_tenant_id": admission_tenant_id,
        })
        await asyncio.to_thread(vobiz_stream_tokens.put, token, **token_meta)
    else:
        token = await asyncio.to_thread(vobiz_stream_tokens.create,
            call_uuid=call_uuid,
            request_uuid=request_uuid,
            from_number=from_number,
            to_number=to_number,
            agent_id=agent_id,
            tenant_id=tenant_id,
            vobiz_account_scope=account_scope,
            vobiz_account_tenant_id=account_tenant_id,
            tier=tier,
            language=language,
            stack_override=stack_override,
            direction=direction,
            source_session_id=source_session_id,
            provider="vobiz",
            answered_at=answered_at,
            contact=(token_meta or {}).get("contact") or local_reg.get("contact"),
            admission_key=admission_key,
            admission_tenant_id=admission_tenant_id,
        )

    # 8. Construct secure WebSocket URL
    ws_base = ws_public_base()
    stream_ws_url = f"{ws_base}/ws/vobiz-stream?token={token}&call_uuid={call_uuid}"

    # 9. Register in call registry under CallUUID and link aliases
    session_data = {
        "call_uuid": call_uuid,
        "request_uuid": request_uuid,
        "from": from_number,
        "to": to_number,
        "direction": direction,
        "agent_id": agent_id,
        "tenant_id": tenant_id,
        "vobiz_account_scope": account_scope,
        "vobiz_account_tenant_id": account_tenant_id,
        "tier": tier,
        "language": language,
        "stack_override": stack_override,
        "source_session_id": source_session_id,
        "status": "in-progress",
        "answered_at": answered_at,
        "stream_url": stream_ws_url,
        "webhook_token": token,
        "contact": (token_meta or {}).get("contact") or local_reg.get("contact"),
        "admission_key": admission_key,
        "admission_tenant_id": admission_tenant_id,
    }
    await asyncio.to_thread(vobiz_call_registry.upsert, call_uuid, session_data)
    if request_uuid and request_uuid != call_uuid:
        await asyncio.to_thread(vobiz_call_registry.upsert, request_uuid, session_data)
        await asyncio.to_thread(vobiz_call_registry.alias, request_uuid, call_uuid)
    if outbound_id and outbound_id not in (call_uuid, request_uuid):
        await asyncio.to_thread(vobiz_call_registry.upsert, outbound_id, session_data)
        await asyncio.to_thread(vobiz_call_registry.alias, outbound_id, call_uuid)

    if admission_key and admission_tenant_id:
        from server.services.saas.call_admission import provider_event
        await provider_event(tenant_id=uuid.UUID(str(admission_tenant_id)), key=admission_key,
                             carrier_ids=(call_uuid, request_uuid), status="answered")

    from urllib.parse import urlencode
    recording_callback = f"{public_api_base()}/api/vobiz/recording?{urlencode({'token': token, 'outbound_id': outbound_id})}"
    return _build_vobiz_xml_response(stream_ws_url, recording_callback)


@router.post("/api/vobiz/fallback")
@router.get("/api/vobiz/fallback")
async def vobiz_fallback(request: Request):
    """Fallback Answer URL — used if the primary answer URL fails or times out."""
    payload = await _parse_vobiz_payload(request)
    await _verify_vobiz_request(request, payload)
    call_uuid = str(payload.get("CallUUID") or payload.get("call_uuid") or payload.get("RequestUUID") or "")
    log_pstn("vobiz.fallback_triggered", call_uuid=call_uuid)
    logger.error("[VOBIZ] Fallback Answer URL reached for call %s", call_uuid)

    fallback_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Speak>We are experiencing a temporary network delay. Please call back in a moment.</Speak>
    <Hangup />
</Response>"""
    return Response(content=fallback_xml, media_type="application/xml")


@router.post("/api/vobiz/hangup")
@router.get("/api/vobiz/hangup")
async def vobiz_hangup(request: Request):
    """Hangup URL — notified when the call finishes."""
    payload = await _parse_vobiz_payload(request)
    await _verify_vobiz_request(request, payload)
    call_uuid = str(
        payload.get("CallUUID")
        or payload.get("call_uuid")
        or payload.get("CallId")
        or payload.get("RequestUUID")
        or payload.get("request_uuid")
        or ""
    )
    request_uuid = str(payload.get("RequestUUID") or payload.get("request_uuid") or "")
    try:
        duration_sec = float(payload.get("Duration") or payload.get("duration") or 0.0)
    except (TypeError, ValueError):
        duration_sec = 0.0
    if not math.isfinite(duration_sec) or duration_sec < 0:
        duration_sec = 0.0
    hangup_cause = str(payload.get("HangupCause") or payload.get("hangup_cause") or "normal")

    log_pstn("vobiz.hangup", call_uuid=call_uuid, request_uuid=request_uuid, duration=duration_sec, cause=hangup_cause)
    if call_uuid:
        await asyncio.to_thread(vobiz_call_registry.upsert,
            call_uuid,
            {
                "ended": True,
                "duration_sec": duration_sec,
                "hangup_cause": hangup_cause,
                "status": "completed",
            },
        )
    if request_uuid and request_uuid != call_uuid:
        await asyncio.to_thread(vobiz_call_registry.upsert,
            request_uuid,
            {
                "ended": True,
                "duration_sec": duration_sec,
                "hangup_cause": hangup_cause,
                "status": "completed",
            },
        )

    # Disconnect active bridge if still open
    from server.services.vobiz_pstn_bridge import active_vobiz_bridges

    bridge = active_vobiz_bridges.get(call_uuid) or (active_vobiz_bridges.get(request_uuid) if request_uuid else None)
    if not bridge and call_uuid:
        reg = await asyncio.to_thread(vobiz_call_registry.get, call_uuid)
        if reg:
            for k in (reg.get("aliased_to"), reg.get("outbound_id"), reg.get("call_uuid")):
                if k and str(k) in active_vobiz_bridges:
                    bridge = active_vobiz_bridges[str(k)]
                    break
    if bridge:
        asyncio.create_task(bridge._cleanup("call_hangup_notified"))

    # Callback Duration may include ringing. Only an explicit billsec field is
    # a billing clock; the CDR reconciler supplies authoritative talk time/cost.
    local = (await asyncio.to_thread(vobiz_call_registry.get, call_uuid)
        or await asyncio.to_thread(vobiz_call_registry.get, request_uuid) or {})
    # A final CallUUID can differ from the create-call RequestUUID. Preserve the
    # signed outbound tracking link when tokens have already been consumed.
    outbound_id = str(request.query_params.get("outbound_id") or "")
    if not local.get("admission_key") and outbound_id:
        tracked = await asyncio.to_thread(vobiz_call_registry.get, outbound_id) or {}
        local = {**tracked, **local}
    token_meta = await asyncio.to_thread(vobiz_stream_tokens.peek, str(request.query_params.get("token") or "")) or {}
    admission_tenant_id = (local.get("admission_tenant_id") or token_meta.get("admission_tenant_id")
        or local.get("tenant_id") or await _vobiz_callback_tenant_id(payload))
    if admission_tenant_id:
        from server.services.saas.call_admission import provider_event
        await provider_event(tenant_id=uuid.UUID(str(admission_tenant_id)),
            key=local.get("admission_key") or token_meta.get("admission_key"),
            carrier_ids=(call_uuid, request_uuid), status="ended")
    internal_id = (bridge.call_id if bridge else None) or local.get("internal_call_id")
    if internal_id:
        from server.call.billing_timing import mark_call_disconnected
        from server.call.call_ledger import call_ledger
        from server.services.vobiz_billing import nonnegative

        mark_call_disconnected(internal_id, payload.get("EndTime") or payload.get("end_time"))
        meta = call_ledger.read_meta(internal_id)
        meta["hangup_cause"] = hangup_cause
        meta["carrier_hangup_confirmed"] = True
        billsec = nonnegative(payload.get("billsec", payload.get("BillDuration")))
        if billsec is not None:
            meta["carrier_billable_duration_sec"] = int(billsec)
            meta["carrier_duration_source"] = "vobiz_callback"
        call_ledger.write_meta(internal_id, meta)
        from server.services.vobiz_recordings import schedule_recording_retrieval
        schedule_recording_retrieval(internal_id)

    return {"ok": True, "call_uuid": call_uuid}


@router.post("/api/vobiz/recording")
@router.get("/api/vobiz/recording")
async def vobiz_recording(request: Request):
    """Recording URL — receives audio recording file upon call completion."""
    payload = await _parse_vobiz_payload(request)
    await _verify_vobiz_request(request, payload)
    call_uuid = str(payload.get("CallUUID") or payload.get("call_uuid") or "")
    record_url = str(payload.get("RecordUrl") or payload.get("RecordFile") or payload.get("recording_url") or "")
    recording_id = str(payload.get("RecordingID") or payload.get("recording_id") or "")
    logger.info("[VOBIZ] recording callback call=%s has_recording=%s", call_uuid, bool(record_url))

    if call_uuid:
        local = await asyncio.to_thread(vobiz_call_registry.get, call_uuid) or {}
        if not local and payload.get("outbound_id"):
            local = await asyncio.to_thread(vobiz_call_registry.get, str(payload["outbound_id"])) or {}
        await asyncio.to_thread(vobiz_call_registry.upsert, call_uuid, {"recording_url": record_url, "recording_id": recording_id})
        internal_id = local.get("internal_call_id")
        if internal_id:
            from server.call.call_ledger import call_ledger
            from server.services.vobiz_recordings import schedule_recording_retrieval
            meta = call_ledger.read_meta(internal_id)
            meta["vobiz_recording_id"] = recording_id
            call_ledger.write_meta(internal_id, meta)
            schedule_recording_retrieval(internal_id)

    return {"ok": True}

