"""Unified dev telephony routes — provider selection + handshake."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from server.auth.dependencies import require_dev_session, require_permission
from server.auth.session import SessionData
from server.services.telephony import active_telephony_provider, telephony_summary_async

router = APIRouter()


class SetProviderBody(BaseModel):
    provider: str = Field(..., pattern="^(exotel|telnyx|plivo)$")


class VoiceCheckBody(BaseModel):
    to_e164: str = Field(..., alias="toE164")
    from_e164: str | None = Field(None, alias="fromE164")

    model_config = {"populate_by_name": True}


class OutboundTestBody(BaseModel):
    to_e164: str = Field(..., alias="toE164")
    from_e164: str | None = Field(None, alias="fromE164")
    agent_id: str = Field(..., alias="agentId")
    tier: str | None = None
    language: str | None = None
    source_session_id: str | None = Field(None, alias="sourceSessionId")
    stack_override: dict[str, Any] | None = Field(None, alias="stackOverride")

    model_config = {"populate_by_name": True}


@router.get("/api/dev/telephony/status")
async def dev_telephony_status(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.read")
    return await telephony_summary_async()


@router.patch("/api/dev/telephony/provider")
async def dev_set_telephony_provider(
    body: SetProviderBody,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.stack.write")
    from server.services.dev_secrets_store import dev_secrets_store

    snap = dev_secrets_store.update({"telephony_provider": body.provider})
    return {"ok": True, "active_provider": body.provider, "applied_keys": snap.get("applied_keys")}


@router.post("/api/dev/telephony/handshake")
async def dev_telephony_handshake(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.read")
    provider = active_telephony_provider()
    if provider == "exotel":
        from server.services.exotel_client import ExotelClient, cached_handshake

        client = ExotelClient()
        return await cached_handshake(client)
    if provider == "telnyx":
        from server.services.telnyx_client import TelnyxClient

        return await TelnyxClient().handshake()
    if provider == "plivo":
        from server.services.plivo_client import PlivoClient

        return await PlivoClient().handshake()
    return {"ok": False, "error": "unknown provider"}


@router.post("/api/dev/telephony/outbound")
async def dev_telephony_outbound(
    body: OutboundTestBody,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.stack.write")
    provider = active_telephony_provider()
    if provider == "exotel":
        return await _outbound_exotel(body)
    if provider == "telnyx":
        return await _outbound_telnyx(body, session)
    if provider == "plivo":
        return await _outbound_plivo(body, session)
    return {"ok": False, "error": "unknown provider"}


async def _outbound_exotel(body: OutboundTestBody) -> dict[str, Any]:
    from server.config.env import get_settings
    from server.services.exotel_call_registry import exotel_call_registry
    from server.services.exotel_client import (
        ExotelApiError,
        ExotelClient,
        ExotelConfigError,
        build_stream_ws_url,
        exotel_enabled,
        public_webhook_urls,
    )
    from server.services.phone_assignments_store import phone_assignments_store

    if not exotel_enabled():
        return {"ok": False, "error": "ENABLE_EXOTEL is false"}
    urls = public_webhook_urls()
    if not urls.get("status_callback_url"):
        return {"ok": False, "error": "Set EXOTEL_WEBHOOK_BASE_URL (public tunnel URL)"}
    settings = get_settings()
    caller_id = (body.from_e164 or settings.exotel_exophone or "").strip()
    to_number = body.to_e164.strip()
    if not caller_id:
        return {"ok": False, "error": "Set EXOTEL_EXOPHONE or fromE164"}
    if not to_number:
        return {"ok": False, "error": "Destination number required"}
    phone_assignments_store.assign(caller_id, body.agent_id)
    custom_field = f"agent:{body.agent_id};tier:{body.tier or 'medium'}"
    try:
        client = ExotelClient()
        stream_url = build_stream_ws_url(agent_id=body.agent_id, tier=body.tier)
        if not stream_url:
            return {"ok": False, "error": "Cannot build WSS stream URL"}
        result = await client.connect_voice_ai(
            to_number=to_number,
            caller_id=caller_id,
            stream_url=stream_url,
            status_callback=urls["status_callback_url"],
            custom_field=custom_field,
        )
        call_sid = result.get("call_sid")
        if call_sid:
            exotel_call_registry.upsert(
                str(call_sid),
                {
                    "status": result.get("status") or "queued",
                    "from": caller_id,
                    "to": to_number,
                    "direction": "outbound-api",
                    "agent_id": body.agent_id,
                    "tier": body.tier,
                    "language": body.language,
                    "source_session_id": body.source_session_id,
                    "stack_override": body.stack_override,
                    "stream_url": stream_url,
                    "last_event": "outbound-initiated",
                },
            )
        return {
            "ok": True,
            "provider": "exotel",
            "call_sid": call_sid,
            "status": result.get("status"),
            "stream_url": stream_url,
        }
    except ExotelConfigError as e:
        return {"ok": False, "error": str(e)}
    except ExotelApiError as e:
        return {"ok": False, "error": str(e), "status": e.status_code}


async def _outbound_telnyx(body: OutboundTestBody, session: SessionData) -> dict[str, Any]:
    from server.brain.agent_service import agent_service
    from server.services.pstn_debug import log_pstn, mark
    from server.services.telnyx_client import (
        TelnyxApiError,
        TelnyxClient,
        TELNYX_RTP_CODEC,
        TELNYX_RTP_SAMPLE_RATE,
        telnyx_call_registry,
        telnyx_stream_tokens,
    )

    try:
        await agent_service.get_agent(body.agent_id)
    except Exception:
        return {"ok": False, "error": f"Agent not found: {body.agent_id}"}

    client = TelnyxClient()
    token = telnyx_stream_tokens.create(
        agent_id=body.agent_id,
        tier=body.tier,
        source_session_id=body.source_session_id,
        language=body.language,
        stack_override=body.stack_override,
        direction="outbound",
    )
    stream_url = client.build_stream_ws_url(token=token)
    try:
        result = await client.create_outbound_call(
            to_e164=body.to_e164,
            from_e164=body.from_e164,
            stream_url=stream_url,
            client_state={
                "agent_id": body.agent_id,
                "tier": body.tier,
                "source_session_id": body.source_session_id,
                "language": body.language,
                "direction": "outbound",
            },
        )
        call_control_id = str(result.get("call_control_id") or result.get("id") or "")
        mark(call_control_id)
        telnyx_call_registry.upsert(
            call_control_id,
            {
                "agent_id": body.agent_id,
                "tier": body.tier,
                "to": body.to_e164,
                "from": body.from_e164,
                "direction": "outbound",
                "status": "initiated",
                "language": body.language,
                "source_session_id": body.source_session_id,
                "stack_override": body.stack_override,
                "stream_url": stream_url,
                "stream_started": True,
            },
        )
        log_pstn(
            "dial.initiated",
            timer_key=call_control_id,
            control=call_control_id,
            to=body.to_e164,
            from_e164=body.from_e164,
            agent_id=body.agent_id,
            provider="telnyx",
            stream_url=stream_url,
            wire_codec=TELNYX_RTP_CODEC,
            wire_rate=TELNYX_RTP_SAMPLE_RATE,
            target_legs="self",
            wire_mode="rtp",
        )
        return {"ok": True, "provider": "telnyx", "call_control_id": call_control_id, "stream_url": stream_url}
    except TelnyxApiError as e:
        detail = (e.body or str(e))[:400]
        return {"ok": False, "error": detail, "status": e.status, "telnyx_error": detail}


@router.get("/api/dev/telephony/calls")
async def dev_telephony_calls(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.read")
    provider = active_telephony_provider()
    if provider == "exotel":
        from server.services.exotel_call_registry import exotel_call_registry

        rows = exotel_call_registry.list_recent(30)
        return {"ok": True, "provider": provider, "calls": rows}
    if provider == "telnyx":
        from server.services.telnyx_client import telnyx_call_registry

        rows = telnyx_call_registry.list_recent(30)
        return {"ok": True, "provider": provider, "calls": rows}
    if provider == "plivo":
        from server.services.plivo_client import plivo_call_registry

        rows = plivo_call_registry.list_recent(30)
        return {"ok": True, "provider": provider, "calls": rows}
    return {"ok": True, "provider": provider, "calls": []}


@router.get("/api/dev/telephony/media-flow")
async def dev_telephony_media_flow(
    call_id: str | None = None,
    session: SessionData = Depends(require_dev_session),
):
    """Latest actual media telemetry; never claims handset audibility."""
    require_permission(session, "dev.stack.read")
    from server.services.pstn_media_flow import pstn_media_flow

    return {"ok": True, "flow": pstn_media_flow.snapshot(call_id)}


@router.post("/api/dev/telephony/media-flow/test-codec")
async def dev_telephony_test_codec(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.write")
    from server.services.audio_transcode import (
        alaw_to_pcm16,
        convert_g711,
        pcm16_to_alaw,
        pcm16_to_mulaw,
    )

    pcm = b"\x00\x00" * 160
    pcmu = pcm16_to_mulaw(pcm, 8000)
    pcma = pcm16_to_alaw(pcm, 8000)
    round_trip = convert_g711(convert_g711(pcmu, "PCMU", "PCMA"), "PCMA", "PCMU")
    return {
        "ok": len(pcmu) == len(pcma) == len(round_trip) == 160 and len(alaw_to_pcm16(pcma, 8000)) == 320,
        "paths": {
            "PCM16_to_PCMU": len(pcmu),
            "PCM16_to_PCMA": len(pcma),
            "PCMU_to_PCMA_to_PCMU": len(round_trip),
        },
        "frame_duration_ms": 20,
    }


@router.post("/api/dev/telephony/media-flow/test-audio")
async def dev_telephony_test_audio(
    call_id: str | None = None,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.stack.write")
    from server.services.telnyx_pstn_bridge import active_telnyx_bridges

    bridge = active_telnyx_bridges.get(call_id or "")
    if not bridge and active_telnyx_bridges:
        bridge = next(reversed(active_telnyx_bridges.values()))
    if not bridge:
        return {"ok": False, "error": "No active Telnyx media stream"}
    import asyncio

    asyncio.create_task(bridge.test_agent_audio())
    return {
        "ok": True,
        "detail": (
            "Playing: “Signal test one. Signal test two. Signal test three.” "
            "then Telugu “నమస్కారం, ఇది ఏజెంట్ ఆడియో పరీక్ష.”"
        ),
    }


@router.post("/api/dev/telephony/voice-check")
async def dev_telephony_voice_check(
    body: VoiceCheckBody,
    session: SessionData = Depends(require_dev_session),
):
    """
    Isolation test: dial with NO media stream / NO agent.
    On answer, Telnyx native speak plays a fixed English test phrase.
    """
    require_permission(session, "dev.stack.write")
    from server.routes.telnyx import VOICE_CHECK_PHRASE
    from server.services.pstn_debug import log_pstn, mark
    from server.services.telnyx_client import TelnyxApiError, TelnyxClient, telnyx_call_registry

    client = TelnyxClient()
    try:
        result = await client.create_simple_outbound_call(
            to_e164=body.to_e164,
            from_e164=body.from_e164,
            client_state={"voice_check": True},
        )
        call_control_id = str(result.get("call_control_id") or result.get("id") or "")
        mark(call_control_id)
        telnyx_call_registry.upsert(
            call_control_id,
            {
                "voice_check": True,
                "to": body.to_e164,
                "from": body.from_e164,
                "direction": "outbound",
                "status": "initiated",
                "skip_stream": True,
            },
        )
        log_pstn(
            "voice_check.dial",
            timer_key=call_control_id,
            control=call_control_id,
            to=body.to_e164,
            from_e164=body.from_e164,
        )
        return {
            "ok": True,
            "provider": "telnyx",
            "call_control_id": call_control_id,
            "mode": "telnyx_speak_only",
            "phrase": VOICE_CHECK_PHRASE,
            "instructions": (
                "Answer the phone. You should hear the English test phrase within a few seconds. "
                "No agent, no WebSocket audio — Telnyx speak API only."
            ),
        }
    except TelnyxApiError as e:
        detail = (e.body or str(e))[:400]
        return {"ok": False, "error": detail, "status": e.status, "telnyx_error": detail}


@router.post("/api/dev/telephony/media-flow/test-telnyx-speak")
async def dev_telephony_test_telnyx_speak(
    call_id: str | None = None,
    session: SessionData = Depends(require_dev_session),
):
    """Play Telnyx native TTS on the call — bypasses our WebSocket audio entirely."""
    require_permission(session, "dev.stack.write")
    from server.services.telnyx_client import TelnyxClient
    from server.services.telnyx_pstn_bridge import active_telnyx_bridges

    bridge = active_telnyx_bridges.get(call_id or "")
    if not bridge and active_telnyx_bridges:
        bridge = next(reversed(active_telnyx_bridges.values()))
    control = bridge.call_control_id if bridge else call_id
    if not control:
        return {"ok": False, "error": "No active Telnyx call"}
    phrase = "Telnyx speak test. You should hear this sentence clearly."
    try:
        await TelnyxClient().speak(control, phrase, language="en-US", voice="female")
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}
    return {"ok": True, "detail": phrase}


@router.post("/api/dev/telephony/telnyx/setup")
async def dev_telnyx_setup(session: SessionData = Depends(require_dev_session)):
    """Apply standard Mission Control settings (webhook, OVP, recording, connection)."""
    require_permission(session, "dev.stack.write")
    from server.services.telnyx_client import TelnyxApiError, TelnyxClient
    from server.services.telnyx_provisioning import run_standard_setup

    try:
        return await run_standard_setup(TelnyxClient())
    except TelnyxApiError as e:
        return {"ok": False, "error": str(e), "status": e.status, "body": e.body}


@router.get("/api/dev/telephony/telnyx/checklist")
async def dev_telnyx_checklist(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.read")
    from server.services.telnyx_client import TelnyxApiError, TelnyxClient
    from server.services.telnyx_provisioning import telnyx_setup_status

    try:
        checklist = await telnyx_setup_status(TelnyxClient())
        return {"ok": True, "checklist": checklist}
    except TelnyxApiError as e:
        return {"ok": False, "error": str(e), "status": e.status}


class VerifyNumberBody(BaseModel):
    phone_number: str = Field(..., alias="phoneNumber")
    method: str = "sms"

    model_config = {"populate_by_name": True}


class ConfirmVerifyBody(BaseModel):
    phone_number: str = Field(..., alias="phoneNumber")
    code: str

    model_config = {"populate_by_name": True}


@router.post("/api/dev/telephony/telnyx/verify-number")
async def dev_telnyx_verify_number(
    body: VerifyNumberBody,
    session: SessionData = Depends(require_dev_session),
):
    """Start SMS/call verification for trial outbound to non-whitelisted destinations."""
    require_permission(session, "dev.stack.write")
    from server.config.urls import public_api_base
    from server.services.telnyx_client import TelnyxApiError, TelnyxClient

    webhook = f"{public_api_base().rstrip('/')}/api/telnyx/webhook"
    try:
        result = await TelnyxClient().request_number_verification(
            body.phone_number.strip(),
            method=body.method if body.method in ("sms", "call") else "sms",
            verification_webhook_url=webhook,
        )
        return {"ok": True, "verification": result}
    except TelnyxApiError as e:
        return {"ok": False, "error": str(e), "status": e.status, "body": e.body}


@router.post("/api/dev/telephony/telnyx/verify-number/confirm")
async def dev_telnyx_confirm_verify(
    body: ConfirmVerifyBody,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.stack.write")
    from server.services.telnyx_client import TelnyxApiError, TelnyxClient

    try:
        result = await TelnyxClient().confirm_number_verification(body.phone_number.strip(), body.code.strip())
        return {"ok": True, "verified": result}
    except TelnyxApiError as e:
        return {"ok": False, "error": str(e), "status": e.status, "body": e.body}


@router.post("/api/dev/telephony/telnyx/numbers/search")
async def dev_telnyx_search_numbers(
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.stack.read")
    from server.services.telnyx_client import TelnyxClient

    client = TelnyxClient()
    numbers = await client.search_available_numbers(country="IN", limit=5)
    return {"ok": True, "numbers": numbers}


@router.post("/api/dev/telephony/telnyx/numbers/order")
async def dev_telnyx_order_number(
    body: dict[str, str],
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.stack.write")
    phone = (body.get("phone_number") or body.get("e164") or "").strip()
    if not phone:
        return {"ok": False, "error": "phone_number required"}
    from server.services.telnyx_client import TelnyxApiError, TelnyxClient
    from server.services.telnyx_provisioning import provision_ordered_number

    try:
        result = await provision_ordered_number(TelnyxClient(), phone)
        return {"ok": True, **result}
    except TelnyxApiError as e:
        return {"ok": False, "error": str(e), "status": e.status, "body": e.body}


async def _outbound_plivo(body: OutboundTestBody, session: SessionData) -> dict[str, Any]:
    from server.config.urls import public_api_base
    from server.services.plivo_client import PlivoApiError, PlivoClient, plivo_call_registry, plivo_stream_tokens

    client = PlivoClient()
    token = plivo_stream_tokens.create(agent_id=body.agent_id, tier=body.tier)
    base = public_api_base().rstrip("/")
    answer_url = f"{base}/api/plivo/answer?token={token}"
    try:
        result = await client.create_outbound_call(
            to_e164=body.to_e164,
            from_e164=body.from_e164,
            answer_url=answer_url,
        )
        request_uuid = str(result.get("request_uuid") or result.get("message") or "")
        plivo_call_registry.upsert(
            request_uuid,
            {
                "agent_id": body.agent_id,
                "tier": body.tier,
                "to": body.to_e164,
                "direction": "outbound",
                "status": "initiated",
                "language": body.language,
                "source_session_id": body.source_session_id,
                "stack_override": body.stack_override,
            },
        )
        return {"ok": True, "provider": "plivo", "call_uuid": request_uuid, "answer_url": answer_url}
    except PlivoApiError as e:
        return {"ok": False, "error": str(e), "status": e.status}
