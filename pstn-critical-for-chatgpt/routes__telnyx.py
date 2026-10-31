"""Telnyx webhook + status."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from server.config.env import get_settings
from server.services.pstn_debug import log_pstn, mark
from server.services.telnyx_client import TelnyxApiError, TelnyxClient, telnyx_call_registry, telnyx_stream_tokens
from server.services.telnyx_webhook_verify import TelnyxSignatureError, parse_verified_webhook_json

logger = logging.getLogger(__name__)
router = APIRouter()


VOICE_CHECK_PHRASE = (
    "Telnyx voice check. This is a test message only. "
    "If you can hear this clearly, Telnyx audio to your phone is working. "
    "Signal test one. Signal test two. Signal test three."
)


async def _run_voice_check(call_control_id: str) -> None:
    """Telnyx native speak — no WebSocket, no agent, no Sarvam TTS."""
    client = TelnyxClient()
    try:
        await client.speak(
            call_control_id,
            VOICE_CHECK_PHRASE,
            language="en-US",
            voice="female",
        )
        telnyx_call_registry.upsert(
            call_control_id,
            {
                "voice_check_speak_sent": True,
                "voice_check_phrase": VOICE_CHECK_PHRASE,
                "last_event": "voice_check_speak",
            },
        )
        log_pstn(
            "voice_check.speak",
            timer_key=call_control_id,
            control=call_control_id,
            chars=len(VOICE_CHECK_PHRASE),
        )
    except TelnyxApiError as exc:
        telnyx_call_registry.upsert(
            call_control_id,
            {
                "voice_check_speak_sent": False,
                "voice_check_error": str(exc)[:300],
                "last_event": "voice_check_speak_failed",
            },
        )
        logger.warning("[TELNYX] voice_check speak failed %s: %s", call_control_id, str(exc)[:200])


async def _ensure_telnyx_streaming(call_control_id: str) -> None:
    """Start bidirectional stream when call is answered (only if dial-time stream is missing)."""
    if not call_control_id:
        return
    row = telnyx_call_registry.get(call_control_id) or {}
    if row.get("skip_stream") or row.get("voice_check"):
        return
    if row.get("stream_started"):
        return
    # Outbound dials pass stream_url on POST /calls — Telnyx starts streaming on answer.
    if row.get("stream_url"):
        return

    client = TelnyxClient()
    stream_url = str(row.get("stream_url") or "")
    if not stream_url:
        token = telnyx_stream_tokens.create(agent_id=row.get("agent_id"), tier=row.get("tier"))
        stream_url = client.build_stream_ws_url(token=token)

    last_err = ""
    for attempt in range(3):
        try:
            await client.start_streaming(call_control_id, stream_url=stream_url)
            telnyx_call_registry.upsert(
                call_control_id,
                {"stream_started": True, "stream_url": stream_url, "last_event": "streaming_start"},
            )
            log_pstn(
                "stream.ensure",
                timer_key=call_control_id,
                control=call_control_id,
                stream_url=stream_url,
                attempt=attempt + 1,
            )
            return
        except TelnyxApiError as exc:
            last_err = str(exc)[:200]
            logger.warning(
                "[TELNYX] streaming_start failed %s attempt=%s: %s",
                call_control_id,
                attempt + 1,
                last_err,
            )
            await asyncio.sleep(0.35 * (2**attempt))
    telnyx_call_registry.upsert(
        call_control_id,
        {"stream_error": last_err, "last_event": "streaming_start_failed"},
    )


@router.post("/api/telnyx/webhook")
@router.get("/api/telnyx/webhook")
async def telnyx_webhook(request: Request):
    settings = get_settings()
    if request.method == "GET":
        return {"ok": True}

    raw = await request.body()
    try:
        require_key = str(settings.app_environment or "").lower() in {"production", "staging"}
        body = parse_verified_webhook_json(
            payload=raw,
            headers=request.headers,
            public_key=settings.telnyx_public_key,
            require_key=require_key,
        )
    except TelnyxSignatureError as exc:
        logger.warning("[TELNYX] webhook rejected: %s", str(exc)[:200])
        raise HTTPException(status_code=403, detail="invalid telnyx signature") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid webhook json") from exc

    data = body.get("data") or body
    payload = data.get("payload") or data
    event_type = data.get("event_type") or payload.get("event_type") or ""
    call_control_id = payload.get("call_control_id") or payload.get("call_session_id") or ""
    patch: dict[str, Any] = {
        "last_event": event_type,
    }
    if event_type:
        patch["status"] = event_type.replace("call.", "")
    if payload.get("from"):
        patch["from"] = payload.get("from")
    if payload.get("to"):
        patch["to"] = payload.get("to")
    if payload.get("direction"):
        existing = telnyx_call_registry.get(str(call_control_id)) or {}
        if not existing.get("direction") or existing.get("direction") in ("incoming", "outgoing"):
            raw_dir = str(payload.get("direction") or "").lower()
            if raw_dir in ("outbound", "outgoing"):
                patch["direction"] = "outbound"
            elif raw_dir in ("inbound", "incoming") and not existing.get("inherit_test_studio_config"):
                patch["direction"] = "inbound"
    if payload.get("recording_urls"):
        patch["recording_urls"] = payload.get("recording_urls")
    for key in ("hangup_cause", "hangup_source", "sip_hangup_cause", "sip_response_code", "call_duration"):
        if payload.get(key) is not None:
            patch[key] = payload.get(key)
    if call_control_id:
        telnyx_call_registry.upsert(str(call_control_id), patch)
    if payload.get("client_state"):
        try:
            import base64
            import json

            meta = json.loads(base64.b64decode(str(payload["client_state"])).decode())
            if meta.get("voice_check"):
                telnyx_call_registry.upsert(
                    str(call_control_id),
                    {"voice_check": True, "skip_stream": True},
                )
        except Exception:
            pass
    if event_type == "call.initiated":
        mark(str(call_control_id))
        log_pstn("webhook.initiated", timer_key=str(call_control_id), control=call_control_id)
    elif event_type == "call.answered":
        claimed = await telnyx_call_registry.atomic_check_and_set(
            str(call_control_id), "answered_handled", True
        )
        if not claimed:
            logger.info("[TELNYX] duplicate call.answered ignored %s", call_control_id)
            return {"ok": True}
        log_pstn("webhook.answered", timer_key=str(call_control_id), control=call_control_id)
        row = telnyx_call_registry.get(str(call_control_id)) or {}
        if row.get("voice_check"):
            await _run_voice_check(str(call_control_id))
        else:
            await _ensure_telnyx_streaming(str(call_control_id))
    elif event_type in ("streaming.started", "call.streaming.started"):
        telnyx_call_registry.upsert(str(call_control_id), {"stream_started": True})
        log_pstn("webhook.streaming_started", timer_key=str(call_control_id), control=call_control_id)
    elif event_type in ("streaming.failed", "call.streaming.failed"):
        log_pstn(
            "webhook.streaming_failed",
            timer_key=str(call_control_id),
            control=call_control_id,
            reason=payload.get("failure_reason") or payload.get("reason"),
        )
        logger.warning("[TELNYX] streaming failed %s %s", call_control_id, payload)
    elif event_type == "call.recording.saved":
        logger.info("[TELNYX] recording saved %s", payload.get("recording_urls"))
    elif event_type in ("call.hangup", "call.failed"):
        from server.services.pstn_prewarm import cancel_prewarm

        if call_control_id:
            await cancel_prewarm("telnyx", str(call_control_id))
        log_pstn(
            f"webhook.{event_type.split('.', 1)[-1]}",
            timer_key=str(call_control_id),
            control=call_control_id,
            cause=payload.get("hangup_cause") or payload.get("sip_hangup_cause"),
            sip=payload.get("sip_response_code"),
        )
        logger.warning(
            "[TELNYX] %s %s cause=%s sip=%s",
            event_type,
            call_control_id,
            payload.get("hangup_cause") or payload.get("sip_hangup_cause"),
            payload.get("sip_response_code"),
        )
    elif event_type:
        log_pstn(f"webhook.{event_type}", control=call_control_id)
    logger.info("[TELNYX] webhook %s %s", event_type, call_control_id)
    return {"ok": True}
