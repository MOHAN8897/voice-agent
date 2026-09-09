"""Unified dev telephony routes — provider selection + handshake."""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from server.auth.dependencies import require_dev_session, require_permission
from server.auth.session import SessionData
from server.services.telephony import (
    active_telephony_provider,
    provider_enabled,
    telephony_guard_error,
    telephony_summary_async,
)

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
    inherit_test_studio_config: bool = Field(False, alias="inheritTestStudioConfig")

    model_config = {"populate_by_name": True}


class PstnStackValidateBody(BaseModel):
    tier: str | None = None
    language: str | None = None
    stack_override: dict[str, Any] | None = Field(None, alias="stackOverride")

    model_config = {"populate_by_name": True}


def _resolve_outbound_source_session(body: OutboundTestBody) -> tuple[str | None, bool]:
    """Dev panel inherits Test Studio config; validation scripts omit source and stay tier-only."""
    inherit = bool(body.inherit_test_studio_config)
    source = (body.source_session_id or "").strip() or None
    if inherit:
        return source or f"test-studio:{body.agent_id}", True
    if source == "test-studio":
        return source, True
    return source, False


def _outbound_pstn_context(body: OutboundTestBody) -> tuple[str, str, dict[str, Any] | None, list[str]]:
    """Validate/sanitize custom PSTN stack before dial. Tier-only → no override."""
    from server.services.pstn_stack import PstnStackValidationError, prepare_pstn_dial_stack

    from server.services.test_studio_config import merge_stack, saved_call_config

    source, _ = _resolve_outbound_source_session(body)
    saved = saved_call_config(source)
    tier = (body.tier or saved.get("tier") or "medium").strip()
    language = (body.language or saved.get("language") or "te-IN").strip()
    override = merge_stack(saved.get("stack_override"), body.stack_override)
    if not override:
        return tier, language, None, []
    try:
        normalized, adjustments = prepare_pstn_dial_stack(
            override, language=language, tier=tier
        )
    except PstnStackValidationError as e:
        raise e
    return tier, language, normalized, adjustments


def _outbound_prewarm_meta(
    body: OutboundTestBody,
    *,
    tier: str,
    language: str,
    source_session_id: str | None,
    inherit_config: bool,
    stack_override: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "agent_id": body.agent_id,
        "tier": tier,
        "language": language,
        "source_session_id": source_session_id,
        "inherit_test_studio_config": inherit_config,
        "stack_override": stack_override,
    }


async def _hangup_active_telnyx_to(client: Any, to_e164: str) -> None:
    from server.services.outbound_dial_guard import hangup_active_telnyx_to

    await hangup_active_telnyx_to(client, to_e164)


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

    if not provider_enabled(body.provider):  # type: ignore[arg-type]
        return {
            "ok": False,
            "error": {
                "code": "provider_disabled",
                "message": f"{body.provider.title()} is disabled in Environment. Enable it under Telephony toggles.",
            },
        }
    snap = dev_secrets_store.update({"telephony_provider": body.provider})
    return {"ok": True, "active_provider": body.provider, "applied_keys": snap.get("applied_keys")}


@router.post("/api/dev/telephony/handshake")
async def dev_telephony_handshake(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.read")
    provider = active_telephony_provider()
    guard = telephony_guard_error(provider)
    if guard:
        return {"ok": False, "error": guard, "provider": provider}
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
    from server.services.pstn_stack import PstnStackValidationError

    try:
        _outbound_pstn_context(body)
    except PstnStackValidationError as e:
        return {"ok": False, "error": str(e), "validation_errors": e.details}
    provider = active_telephony_provider()
    guard = telephony_guard_error(provider)
    if guard:
        return {"ok": False, "error": guard, "provider": provider}
    to_number = body.to_e164.strip()
    if not to_number:
        return {"ok": False, "error": "Destination number required"}
    from server.services.outbound_dial_guard import acquire_outbound_slot, release_outbound_slot

    if not await acquire_outbound_slot(provider, to_number):
        return {
            "ok": False,
            "error": "An outbound call to this number is already in progress. Wait for it to finish or hang up first.",
            "code": "dial_in_progress",
            "provider": provider,
        }
    try:
        if provider == "exotel":
            result = await _outbound_exotel(body)
        elif provider == "telnyx":
            result = await _outbound_telnyx(body, session)
        elif provider == "plivo":
            result = await _outbound_plivo(body, session)
        else:
            result = {"ok": False, "error": "unknown provider"}
        if not result.get("ok"):
            release_outbound_slot(provider, to_number)
        return result
    except Exception:
        release_outbound_slot(provider, to_number)
        raise


_PSTN_VALIDATE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_PSTN_VALIDATE_TTL_SEC = 30.0


@router.post("/api/dev/telephony/pstn-stack/validate")
async def dev_pstn_stack_validate(
    body: PstnStackValidateBody,
    session: SessionData = Depends(require_dev_session),
):
    """Preview PSTN stack normalization for dev panel (no dial)."""
    require_permission(session, "dev.stack.read")
    from server.services.pstn_stack import PstnStackValidationError, prepare_pstn_dial_stack

    tier = (body.tier or "medium").strip()
    language = (body.language or "te-IN").strip()
    cache_payload = {
        "tier": tier,
        "language": language,
        "stack_override": body.stack_override,
    }
    cache_key = hashlib.sha256(
        json.dumps(cache_payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    now = time.time()
    cached = _PSTN_VALIDATE_CACHE.get(cache_key)
    if cached and now - cached[0] < _PSTN_VALIDATE_TTL_SEC:
        return cached[1]

    if not body.stack_override:
        result = {"ok": True, "stackOverride": None, "adjustments": [], "tier": tier, "language": language}
        _PSTN_VALIDATE_CACHE[cache_key] = (now, result)
        return result
    try:
        normalized, adjustments = prepare_pstn_dial_stack(
            body.stack_override, language=language, tier=tier
        )
        result = {
            "ok": True,
            "stackOverride": normalized,
            "adjustments": adjustments,
            "tier": tier,
            "language": language,
        }
        _PSTN_VALIDATE_CACHE[cache_key] = (now, result)
        return result
    except PstnStackValidationError as e:
        result = {"ok": False, "error": str(e), "validation_errors": e.details}
        _PSTN_VALIDATE_CACHE[cache_key] = (now, result)
        return result


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

    from server.services.dev_secrets_store import dev_secrets_store

    if not exotel_enabled():
        return {"ok": False, "error": "Exotel is disabled in Environment"}
    urls = public_webhook_urls()
    if not urls.get("status_callback_url"):
        return {"ok": False, "error": "Set EXOTEL_WEBHOOK_BASE_URL (public tunnel URL)"}
    settings = get_settings()
    exophone = dev_secrets_store.effective("exotel_exophone", settings.exotel_exophone) or ""
    caller_id = (body.from_e164 or exophone or "").strip()
    to_number = body.to_e164.strip()
    if not caller_id:
        return {"ok": False, "error": "Set EXOTEL_EXOPHONE or fromE164"}
    tier, language, stack_override, stack_adjustments = _outbound_pstn_context(body)
    source_session_id, inherit_config = _resolve_outbound_source_session(body)
    from server.services.outbound_dial_guard import hangup_active_exotel_to

    await hangup_active_exotel_to(to_number)
    phone_assignments_store.assign(caller_id, body.agent_id)
    custom_field = f"agent:{body.agent_id};tier:{tier or 'medium'}"
    try:
        client = ExotelClient()
        stream_url = build_stream_ws_url(agent_id=body.agent_id, tier=tier)
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
                    "tier": tier,
                    "language": language,
                    "source_session_id": source_session_id,
                    "inherit_test_studio_config": inherit_config,
                    "stack_override": stack_override,
                    "stream_url": stream_url,
                    "last_event": "outbound-initiated",
                },
            )
        payload: dict[str, Any] = {
            "ok": True,
            "provider": "exotel",
            "call_sid": call_sid,
            "status": result.get("status"),
            "stream_url": stream_url,
        }
        if stack_adjustments:
            payload["stack_adjustments"] = stack_adjustments
        if call_sid:
            from server.services.pstn_prewarm import schedule_prewarm

            schedule_prewarm(
                "exotel",
                str(call_sid),
                _outbound_prewarm_meta(
                    body,
                    tier=tier or "medium",
                    language=language,
                    source_session_id=source_session_id,
                    inherit_config=inherit_config,
                    stack_override=stack_override,
                ),
            )
        return payload
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

    tier, language, stack_override, stack_adjustments = _outbound_pstn_context(body)
    source_session_id, inherit_config = _resolve_outbound_source_session(body)

    try:
        await agent_service.get_agent(body.agent_id)
    except Exception:
        return {"ok": False, "error": f"Agent not found: {body.agent_id}"}

    from server.services.production_canary import assert_canary_outbound_allowed

    canary_block = assert_canary_outbound_allowed(body.to_e164)
    if canary_block:
        return {"ok": False, "error": canary_block, "canary_blocked": True}

    client = TelnyxClient()
    token = telnyx_stream_tokens.create(
        agent_id=body.agent_id,
        tier=tier,
        source_session_id=source_session_id,
        inherit_test_studio_config=inherit_config,
        language=language,
        stack_override=stack_override,
        direction="outbound",
    )
    stream_url = client.build_stream_ws_url(token=token)
    if not stream_url.startswith("wss://"):
        return {"ok": False, "error": "Configure a public HTTPS API/tunnel URL before placing a PSTN call."}
    await _hangup_active_telnyx_to(client, body.to_e164)
    try:
        result = await client.create_outbound_call(
            to_e164=body.to_e164,
            from_e164=body.from_e164,
            stream_url=stream_url,
            client_state={
                "agent_id": body.agent_id,
                "tier": tier,
                "source_session_id": source_session_id,
                "inherit_test_studio_config": inherit_config,
                "language": language,
                "stack_override": stack_override,
                "direction": "outbound",
            },
        )
        call_control_id = str(result.get("call_control_id") or result.get("id") or "")
        mark(call_control_id)
        existing_call = telnyx_call_registry.get(call_control_id) or {}
        telnyx_call_registry.upsert(
            call_control_id,
            {
                "agent_id": body.agent_id,
                "tier": tier,
                "to": body.to_e164,
                "from": body.from_e164,
                "direction": "outbound",
                "status": existing_call.get("status") or "initiated",
                "language": language,
                "source_session_id": source_session_id,
                "inherit_test_studio_config": inherit_config,
                "stack_override": stack_override,
                "stream_url": stream_url,
                "stream_configured": True,
                "stream_started": True,
                "stream_state": existing_call.get("stream_state") or "pending_answer",
            },
        )
        if call_control_id:
            # Merge — do not replace. Replacing wiped source_session_id / stack_override /
            # language / inherit flags and could desync agent config from the media leg.
            existing = telnyx_stream_tokens.peek(token) or {}
            merged_meta = {
                **existing,
                "agent_id": body.agent_id,
                "tier": tier,
                "call_control_id": call_control_id,
            }
            telnyx_stream_tokens.put(token, **merged_meta)
        log_pstn(
            "dial.initiated",
            timer_key=call_control_id,
            control=call_control_id,
            to=body.to_e164,
            from_e164=body.from_e164,
            agent_id=body.agent_id,
            provider="telnyx",
            stream_url=stream_url.split("?", 1)[0],
            wire_codec=TELNYX_RTP_CODEC,
            wire_rate=TELNYX_RTP_SAMPLE_RATE,
            target_legs="self",
            wire_mode="rtp",
        )
        payload: dict[str, Any] = {
            "ok": True,
            "provider": "telnyx",
            "call_control_id": call_control_id,
            "stream_url": stream_url,
        }
        if stack_adjustments:
            payload["stack_adjustments"] = stack_adjustments
        if call_control_id:
            from server.services.pstn_prewarm import schedule_prewarm

            schedule_prewarm(
                "telnyx",
                call_control_id,
                _outbound_prewarm_meta(
                    body,
                    tier=tier or "medium",
                    language=language,
                    source_session_id=source_session_id,
                    inherit_config=inherit_config,
                    stack_override=stack_override,
                ),
            )
        return payload
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

    flow = pstn_media_flow.snapshot(call_id)
    if flow:
        from server.services.telnyx_pstn_bridge import active_telnyx_bridges
        from server.services.telnyx_client import telnyx_call_registry
        from server.realtime.manager import realtime_text_manager

        external_id = str(flow.get("external_id") or "")
        bridge = active_telnyx_bridges.get(external_id)
        row = telnyx_call_registry.get(external_id) or {}
        voice = bridge._voice if bridge else None
        realtime = realtime_text_manager.get(str(flow.get("call_id") or ""))
        flow["diagnostics"] = {
            "direction": row.get("direction"),
            "agent_id": bridge.agent_id if bridge else row.get("agent_id"),
            "phase": voice._phase if voice else ("ended" if not flow.get("active") else "connecting"),
            "turn_id": voice.current_turn_id if voice else None,
            "generation_id": voice.current_generation_id if voice else None,
            "stt": "streaming" if voice and voice._stt else "disconnected",
            "realtime": "ready" if realtime and realtime.is_ready else "disconnected",
            "model": realtime.model if realtime else None,
        }
    return {"ok": True, "flow": flow}


@router.post("/api/dev/telephony/media-flow/purge")
async def dev_telephony_purge(call_id: str, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.write")
    from server.services.telnyx_pstn_bridge import active_telnyx_bridges

    bridge = next((b for b in active_telnyx_bridges.values() if call_id in (b.call_id, b.call_control_id)), None)
    if bridge is None or bridge._voice is None:
        return {"ok": False, "error": "No active media session for this call"}
    await bridge._voice._commit_barge("")
    return {"ok": True, "detail": "Playback purged and generation cancelled"}


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


@router.post("/api/dev/telephony/hangup")
async def dev_telephony_hangup(
    call_control_id: str,
    session: SessionData = Depends(require_dev_session),
):
    """End an active Telnyx PSTN call (TEST 8 sequential cleanup)."""
    require_permission(session, "dev.stack.write")
    from server.services.telnyx_client import TelnyxApiError, TelnyxClient, telnyx_call_registry

    if not call_control_id.strip():
        return {"ok": False, "error": "call_control_id required"}
    client = TelnyxClient()
    try:
        await client.hangup(call_control_id.strip())
        telnyx_call_registry.upsert(
            call_control_id.strip(),
            {"status": "hangup", "last_event": "dev_hangup"},
        )
        return {"ok": True, "call_control_id": call_control_id.strip()}
    except TelnyxApiError as e:
        detail = (e.body or str(e))[:400]
        return {"ok": False, "error": detail, "status": e.status, "telnyx_error": detail}


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


@router.get("/api/dev/telephony/production-canary/checklist")
async def dev_production_canary_checklist(session: SessionData = Depends(require_dev_session)):
    """TEST 9.1 — deploy checklist for production canary."""
    require_permission(session, "dev.stack.read")
    from server.config.urls import public_api_base
    from server.services.production_canary import build_deploy_checklist
    from server.services.telnyx_client import TelnyxApiError, TelnyxClient
    from server.services.telnyx_provisioning import telnyx_setup_status

    telnyx_checklist: dict | None = None
    try:
        telnyx_checklist = await telnyx_setup_status(TelnyxClient())
    except TelnyxApiError:
        telnyx_checklist = None
    deploy = build_deploy_checklist(telnyx_checklist=telnyx_checklist)
    return {
        "ok": True,
        "public_api_base": public_api_base(),
        "deploy": deploy,
        "telnyx_checklist": telnyx_checklist,
    }


@router.get("/api/dev/telephony/production-canary/status")
async def dev_production_canary_status(
    hours: int = 48,
    session: SessionData = Depends(require_dev_session),
):
    """TEST 9.2–9.4 — canary window metrics and gate scoring."""
    require_permission(session, "dev.stack.read")
    from server.services.production_canary import score_canary_window
    from server.services.telnyx_client import telnyx_call_registry

    registry = telnyx_call_registry.list_recent(50)
    window = score_canary_window(registry_rows=registry, hours=max(1, min(hours, 168)))
    return {"ok": True, "canary": window}


@router.post("/api/dev/telephony/production-canary/seed-archives")
async def dev_production_canary_seed_archives(
    hours: int = 48,
    limit: int = 30,
    session: SessionData = Depends(require_dev_session),
):
    """Backfill canary log from recent PSTN call archives on this server."""
    require_permission(session, "dev.stack.write")
    from server.services.production_canary import seed_canary_from_archives

    seeded = seed_canary_from_archives(limit=max(1, min(limit, 100)), hours=max(1, min(hours, 168)))
    return {"ok": True, "seeded": seeded}


@router.get("/api/dev/telephony/production-launch/checklist")
async def dev_production_launch_checklist(session: SessionData = Depends(require_dev_session)):
    """TEST 10 — launch checklist (Telnyx, agent, observability, support, regression)."""
    require_permission(session, "dev.stack.read")
    from server.services.production_canary import score_canary_window
    from server.services.production_launch import build_launch_checklist
    from server.services.telnyx_client import TelnyxApiError, TelnyxClient, telnyx_call_registry
    from server.services.telnyx_provisioning import telnyx_setup_status

    telnyx_checklist: dict | None = None
    try:
        telnyx_checklist = await telnyx_setup_status(TelnyxClient())
    except TelnyxApiError:
        telnyx_checklist = None
    registry = telnyx_call_registry.list_recent(50)
    canary = score_canary_window(registry_rows=registry, hours=168)
    launch = build_launch_checklist(
        telnyx_checklist=telnyx_checklist,
        canary_overall=bool(canary.get("overall")),
    )
    return {"ok": True, "launch": launch, "canary_overall": canary.get("overall")}


@router.get("/api/dev/telephony/production-launch/slos")
async def dev_production_launch_slos(
    hours: int = 168,
    session: SessionData = Depends(require_dev_session),
):
    """TEST 10 — production SLO metrics and pass/fail gates."""
    require_permission(session, "dev.stack.read")
    from server.services.production_launch import compute_production_slos
    from server.services.telnyx_client import telnyx_call_registry

    registry = telnyx_call_registry.list_recent(100)
    slos = compute_production_slos(registry_rows=registry, hours=max(24, min(hours, 720)))
    return {"ok": True, "production": slos}


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

    tier, language, stack_override, stack_adjustments = _outbound_pstn_context(body)
    source_session_id, inherit_config = _resolve_outbound_source_session(body)
    client = PlivoClient()
    from server.services.outbound_dial_guard import hangup_active_plivo_to

    await hangup_active_plivo_to(body.to_e164)
    token = plivo_stream_tokens.create(agent_id=body.agent_id, tier=tier)
    base = public_api_base().rstrip("/")
    answer_url = f"{base}/api/plivo/answer?token={token}"
    try:
        result = await client.create_outbound_call(
            to_e164=body.to_e164,
            from_e164=body.from_e164,
            answer_url=answer_url,
        )
        request_uuid = str(result.get("request_uuid") or result.get("message") or "")
        plivo_stream_tokens.put(token, agent_id=body.agent_id, tier=tier, request_uuid=request_uuid)
        plivo_call_registry.upsert(
            request_uuid,
            {
                "agent_id": body.agent_id,
                "tier": tier,
                "to": body.to_e164,
                "direction": "outbound",
                "status": "initiated",
                "language": language,
                "source_session_id": source_session_id,
                "inherit_test_studio_config": inherit_config,
                "stack_override": stack_override,
            },
        )
        payload: dict[str, Any] = {
            "ok": True,
            "provider": "plivo",
            "call_uuid": request_uuid,
            "answer_url": answer_url,
        }
        if stack_adjustments:
            payload["stack_adjustments"] = stack_adjustments
        if request_uuid:
            from server.services.pstn_prewarm import schedule_prewarm

            schedule_prewarm(
                "plivo",
                request_uuid,
                _outbound_prewarm_meta(
                    body,
                    tier=tier or "medium",
                    language=language,
                    source_session_id=source_session_id,
                    inherit_config=inherit_config,
                    stack_override=stack_override,
                ),
            )
        return payload
    except PlivoApiError as e:
        return {"ok": False, "error": str(e), "status": e.status}
