"""Vobiz HTTP Webhook Handlers — Answer XML, Fallback, Hangup & Recording Callbacks."""
from __future__ import annotations

import asyncio
import logging
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
    content_type = request.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        try:
            return await request.json()
        except Exception:
            return {}
    # Form data or URL-encoded (standard VoiceXML webhooks)
    try:
        form = await request.form()
        return dict(form)
    except Exception:
        body = await request.body()
        try:
            import json
            return json.loads(body.decode("utf-8"))
        except Exception:
            return {}


def _build_vobiz_xml_response(stream_ws_url: str) -> Response:
    """Generate compliant VoiceXML instructing Vobiz to connect bidirectional WebSocket."""
    from xml.sax.saxutils import escape as xml_escape

    escaped_url = xml_escape(stream_ws_url.strip())
    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Stream bidirectional="true" keepCallAlive="true">{escaped_url}</Stream>
</Response>"""
    return Response(content=xml_content, media_type="application/xml")


@router.post("/api/vobiz/answer")
@router.get("/api/vobiz/answer")
async def vobiz_answer(request: Request):
    """Primary Answer URL — triggered when a call starts on Vobiz."""
    if request.method == "GET":
        return Response(content="<Response><Hangup /></Response>", media_type="application/xml")

    payload = await _parse_vobiz_payload(request)
    call_uuid = str(
        payload.get("CallUUID")
        or payload.get("call_uuid")
        or payload.get("CallId")
        or payload.get("call_id")
        or uuid.uuid4()
    )
    from_number = str(payload.get("From") or payload.get("caller") or "")
    to_number = str(payload.get("To") or payload.get("called") or "")
    direction = str(payload.get("Direction") or "inbound").lower()

    mark(call_uuid)
    log_pstn("vobiz.answer_requested", call_uuid=call_uuid, from_=from_number, to=to_number, direction=direction)

    # 1. Resolve agent & tenant (outbound uses from_number or registry; inbound uses to_number)
    agent_id: str | None = None
    tenant_id: str | None = None
    try:
        from server.services.saas.telephony_profile import profile_for_number
        local_reg = vobiz_call_registry.get(call_uuid) or {}
        agent_id = local_reg.get("agent_id")
        tenant_id = local_reg.get("tenant_id")

        lookup_num = from_number if direction == "outbound" else to_number
        if not agent_id and lookup_num:
            profile = await profile_for_number(lookup_num)
            if profile:
                agent_id = str(profile.get("agent_id") or "")
                tenant_id = str(profile.get("tenant_id") or "")

        if not agent_id:
            from server.db.connection import get_session_factory
            from server.db.models.entities import Agent
            from sqlalchemy import select

            factory = get_session_factory()
            if factory:
                async with factory() as session:
                    res = await session.execute(select(Agent).where(Agent.status == "active").limit(1))
                    ag = res.scalar_one_or_none()
                    if ag:
                        agent_id = str(ag.agent_id)
                        tenant_id = str(ag.tenant_id)
    except Exception as e:
        logger.warning("[VOBIZ] agent lookup failed: %s", e)

    # 2. Check wallet balance if inbound payment wall is enabled
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
            logger.warning("[VOBIZ] wallet balance check fallback: %s", e)

    # 3. Create stream security token
    token = vobiz_stream_tokens.create(
        call_uuid=call_uuid,
        from_number=from_number,
        to_number=to_number,
        agent_id=agent_id,
        tenant_id=tenant_id,
        direction=direction,
        provider="vobiz",
    )

    # 4. Construct secure WebSocket URL
    ws_base = ws_public_base()
    stream_ws_url = f"{ws_base}/ws/vobiz-stream?token={token}&call_uuid={call_uuid}"

    # Track in registry
    vobiz_call_registry.upsert(
        call_uuid,
        {
            "call_uuid": call_uuid,
            "from": from_number,
            "to": to_number,
            "direction": direction,
            "agent_id": agent_id,
            "status": "in-progress",
            "stream_url": stream_ws_url,
        },
    )

    return _build_vobiz_xml_response(stream_ws_url)


@router.post("/api/vobiz/fallback")
async def vobiz_fallback(request: Request):
    """Fallback Answer URL — used if the primary answer URL fails or times out."""
    payload = await _parse_vobiz_payload(request)
    call_uuid = str(payload.get("CallUUID") or payload.get("call_uuid") or "")
    log_pstn("vobiz.fallback_triggered", call_uuid=call_uuid, payload=payload)
    logger.error("[VOBIZ] Fallback Answer URL reached for call %s", call_uuid)

    fallback_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Speak>We are experiencing a temporary network delay. Please call back in a moment.</Speak>
    <Hangup />
</Response>"""
    return Response(content=fallback_xml, media_type="application/xml")


@router.post("/api/vobiz/hangup")
async def vobiz_hangup(request: Request):
    """Hangup URL — notified when the call finishes."""
    payload = await _parse_vobiz_payload(request)
    call_uuid = str(payload.get("CallUUID") or payload.get("call_uuid") or payload.get("CallId") or "")
    duration_sec = float(payload.get("Duration") or payload.get("duration") or 0.0)
    hangup_cause = str(payload.get("HangupCause") or payload.get("hangup_cause") or "normal")

    log_pstn("vobiz.hangup", call_uuid=call_uuid, duration=duration_sec, cause=hangup_cause)
    vobiz_call_registry.upsert(
        call_uuid,
        {
            "ended": True,
            "duration_sec": duration_sec,
            "hangup_cause": hangup_cause,
            "status": "completed",
        },
    )

    # Disconnect active bridge if still open
    from server.services.vobiz_pstn_bridge import active_vobiz_bridges
    bridge = active_vobiz_bridges.get(call_uuid)
    if bridge:
        asyncio.create_task(bridge._cleanup("call_hangup_notified"))

    return {"ok": True, "call_uuid": call_uuid}


@router.post("/api/vobiz/recording")
async def vobiz_recording(request: Request):
    """Recording URL — receives audio recording file upon call completion."""
    payload = await _parse_vobiz_payload(request)
    call_uuid = str(payload.get("CallUUID") or payload.get("call_uuid") or "")
    record_url = str(payload.get("RecordUrl") or payload.get("recording_url") or "")
    logger.info("[VOBIZ] recording saved call=%s url=%s", call_uuid, record_url)

    if call_uuid and record_url:
        vobiz_call_registry.upsert(call_uuid, {"recording_url": record_url})
        try:
            from server.call.call_ledger import call_ledger
            call_ledger.update_meta(call_uuid, {"recording_url": record_url, "recording_source": "vobiz"})
        except Exception:
            pass

    return {"ok": True}
