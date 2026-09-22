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

# Bounded stream start/retry — never infinite.
_STREAM_MAX_ATTEMPTS = 3
_STREAM_MAX_FAILURE_RETRIES = 3
_stream_op_locks: dict[str, asyncio.Lock] = {}
_stream_watchdogs: dict[str, asyncio.Task] = {}
_STREAM_CONNECT_TIMEOUT_S = 3.0


async def _start_answered_recording(call_control_id: str) -> None:
    """Recording must not sit on the streaming_start await path."""
    try:
        from server.services.telnyx_recordings import start_call_recording

        await start_call_recording(call_control_id)
    except Exception:
        logger.exception("[PSTN_STREAM] answered recording failed control=%s", call_control_id)


def _watch_stream_connect(call_control_id: str) -> None:
    previous = _stream_watchdogs.get(call_control_id)
    if previous and not previous.done():
        return

    async def watch() -> None:
        try:
            for _ in range(_STREAM_MAX_FAILURE_RETRIES):
                await asyncio.sleep(_STREAM_CONNECT_TIMEOUT_S)
                row = telnyx_call_registry.get(call_control_id) or {}
                if _call_ended(row) or row.get("stream_connected"):
                    return
                telnyx_call_registry.upsert(call_control_id, {
                    "stream_retry_count": int(row.get("stream_retry_count") or 0) + 1,
                    "stream_start_requested": False,
                })
                await _ensure_telnyx_streaming(call_control_id, reason="retry")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[PSTN_STREAM] connect watchdog failed control=%s", call_control_id)
        finally:
            _stream_watchdogs.pop(call_control_id, None)

    _stream_watchdogs[call_control_id] = asyncio.create_task(watch())

VOICE_CHECK_PHRASE = (
    "Telnyx voice check. This is a test message only. "
    "If you can hear this clearly, Telnyx audio to your phone is working. "
    "Signal test one. Signal test two. Signal test three."
)


def _stream_lock(call_control_id: str) -> asyncio.Lock:
    lock = _stream_op_locks.get(call_control_id)
    if lock is None:
        lock = asyncio.Lock()
        _stream_op_locks[call_control_id] = lock
    return lock


def _stream_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "stream_configured": bool(row.get("stream_configured") or row.get("stream_url")),
        "stream_start_requested": bool(row.get("stream_start_requested")),
        "stream_connected": bool(row.get("stream_connected")),
        "stream_failed": bool(row.get("stream_failed")),
        "stream_state": row.get("stream_state") or "unknown",
        "retry_count": int(row.get("stream_retry_count") or 0),
    }


def _call_ended(row: dict[str, Any]) -> bool:
    """True when the Telnyx leg is already hung up / failed — do not restart media."""
    if row.get("ended"):
        return True
    if row.get("hangup_cause") is not None:
        return True
    status = str(row.get("status") or "").lower()
    return status in {"hangup", "failed", "call.hangup", "call.failed"}


def _format_telnyx_err(exc: TelnyxApiError) -> str:
    detail = (exc.body or "").strip().replace("\n", " ")
    if detail:
        return f"{exc} {detail[:240]}"
    return str(exc)


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


async def _ensure_telnyx_streaming(
    call_control_id: str,
    *,
    reason: str = "answered",
) -> None:
    """Ensure bidirectional media is actually started — never treat stream_url alone as active.

    States (registry):
      stream_configured      — stream_url known (dial-time or built)
      stream_start_requested — start_streaming issued / in flight
      stream_connected       — Telnyx streaming.started or WS media start
      stream_failed          — last start/stream failed
      stream_retrying        — recovery in progress
    """
    if not call_control_id:
        return

    async with _stream_lock(call_control_id):
        row = telnyx_call_registry.get(call_control_id) or {}
        before = _stream_snapshot(row)
        if row.get("skip_stream") or row.get("voice_check"):
            return
        if _call_ended(row):
            log_pstn(
                "PSTN_STREAM",
                call_id=call_control_id,
                control=call_control_id,
                event="ensure_skip_ended",
                reason=reason,
                hangup_cause=row.get("hangup_cause"),
                status=row.get("status"),
                **before,
            )
            return

        # Already have a live media stream — do not restart.
        if row.get("stream_connected"):
            log_pstn(
                "PSTN_STREAM",
                call_id=call_control_id,
                control=call_control_id,
                event="ensure_skip_connected",
                reason=reason,
                **before,
            )
            return

        retry_count = int(row.get("stream_retry_count") or 0)
        if reason in ("streaming_failed", "retry") and retry_count >= _STREAM_MAX_FAILURE_RETRIES:
            telnyx_call_registry.upsert(
                call_control_id,
                {
                    "stream_failed": True,
                    "stream_connected": False,
                    "stream_state": "terminal_failed",
                    "status": "stream-error",
                    "last_event": "streaming_terminal_failed",
                },
            )
            after = _stream_snapshot(telnyx_call_registry.get(call_control_id) or {})
            log_pstn(
                "PSTN_STREAM",
                call_id=call_control_id,
                control=call_control_id,
                event="terminal_failed",
                reason=reason,
                before=before,
                after=after,
                retry_count=retry_count,
            )
            logger.error(
                "[PSTN_STREAM] terminal failure control=%s retries=%s — call has no usable media",
                call_control_id,
                retry_count,
            )
            try:
                await TelnyxClient().hangup(call_control_id)
            except Exception as exc:
                log_pstn("stream.terminal_hangup_failed", control=call_control_id, error=str(exc)[:160])
            return

        client = TelnyxClient()
        stream_url = str(row.get("stream_url") or "").strip()
        if not stream_url:
            token = telnyx_stream_tokens.create(
                agent_id=row.get("agent_id"),
                tier=row.get("tier"),
                call_control_id=call_control_id,
                direction=row.get("direction") or "inbound",
                source_session_id=row.get("source_session_id"),
                inherit_test_studio_config=row.get("inherit_test_studio_config", False),
                stack_override=row.get("stack_override"),
                language=row.get("language"),
            )
            stream_url = client.build_stream_ws_url(token=token)
        if not stream_url.startswith("wss://"):
            telnyx_call_registry.upsert(call_control_id, {"stream_failed": True, "stream_error": "Public WSS URL required"})
            raise ValueError("Telnyx requires a public HTTPS API/tunnel URL")

        telnyx_call_registry.upsert(
            call_control_id,
            {
                "stream_url": stream_url,
                "stream_configured": True,
                "stream_start_requested": True,
                "stream_failed": False,
                "stream_state": "retrying" if reason in ("streaming_failed", "retry") else "start_requested",
                "stream_retry_reason": reason,
            },
        )
        log_pstn(
            "PSTN_STREAM",
            call_id=call_control_id,
            control=call_control_id,
            event="start_requested",
            reason=reason,
            before=before,
            stream_url=stream_url.split("?", 1)[0],
            retry_count=retry_count,
        )

        last_err = ""
        for attempt in range(_STREAM_MAX_ATTEMPTS):
            live = telnyx_call_registry.get(call_control_id) or {}
            if _call_ended(live):
                log_pstn(
                    "PSTN_STREAM",
                    call_id=call_control_id,
                    control=call_control_id,
                    event="ensure_abort_ended",
                    reason=reason,
                    attempt=attempt + 1,
                    hangup_cause=live.get("hangup_cause"),
                )
                return
            if live.get("stream_connected"):
                return
            try:
                await client.start_streaming(
                    call_control_id, stream_url=stream_url, target_legs="both"
                )
                # A WS start or hangup can arrive while the HTTP request is pending.
                live = telnyx_call_registry.get(call_control_id) or {}
                if _call_ended(live) or live.get("stream_connected"):
                    return
                telnyx_call_registry.upsert(
                    call_control_id,
                    {
                        "stream_start_requested": True,
                        "stream_api_ok": True,
                        "stream_url": stream_url,
                        # NOT connected until streaming.started / WS start
                        "stream_failed": False,
                        "stream_state": "api_ok_awaiting_connect",
                        "last_event": "streaming_start",
                    },
                )
                after = _stream_snapshot(telnyx_call_registry.get(call_control_id) or {})
                log_pstn(
                    "PSTN_STREAM",
                    call_id=call_control_id,
                    control=call_control_id,
                    event="stream_start_requested",
                    reason=reason,
                    attempt=attempt + 1,
                    before=before,
                    after=after,
                    retry_count=retry_count,
                )
                _watch_stream_connect(call_control_id)
                return
            except TelnyxApiError as exc:
                last_err = _format_telnyx_err(exc)[:280]
                # 422 after hangup / dead leg — further retries are noise.
                if exc.status == 422 or _call_ended(telnyx_call_registry.get(call_control_id) or {}):
                    logger.warning(
                        "[PSTN_STREAM] start aborted control=%s attempt=%s reason=%s: %s",
                        call_control_id,
                        attempt + 1,
                        reason,
                        last_err,
                    )
                    log_pstn(
                        "PSTN_RETRY",
                        call_id=call_control_id,
                        control=call_control_id,
                        event="stream_start_aborted",
                        attempt=attempt + 1,
                        reason=reason,
                        error=last_err,
                        status=exc.status,
                    )
                    break
                logger.warning(
                    "[PSTN_STREAM] start failed control=%s attempt=%s reason=%s: %s",
                    call_control_id,
                    attempt + 1,
                    reason,
                    last_err,
                )
                log_pstn(
                    "PSTN_RETRY",
                    call_id=call_control_id,
                    control=call_control_id,
                    event="stream_start_attempt_failed",
                    attempt=attempt + 1,
                    reason=reason,
                    error=last_err,
                )
                await asyncio.sleep(0.35 * (2**attempt))
            except Exception as exc:
                # Transport / unexpected errors must not kill the answered webhook without retry.
                last_err = f"{exc.__class__.__name__}: {exc}"[:280]
                logger.warning(
                    "[PSTN_STREAM] start exception control=%s attempt=%s reason=%s: %s",
                    call_control_id,
                    attempt + 1,
                    reason,
                    last_err,
                )
                log_pstn(
                    "PSTN_RETRY",
                    call_id=call_control_id,
                    control=call_control_id,
                    event="stream_start_attempt_failed",
                    attempt=attempt + 1,
                    reason=reason,
                    error=last_err,
                )
                if _call_ended(telnyx_call_registry.get(call_control_id) or {}):
                    break
                await asyncio.sleep(0.35 * (2**attempt))

        current = telnyx_call_registry.get(call_control_id) or {}
        if current.get("stream_connected") or _call_ended(current):
            return

        new_retry = retry_count + 1
        telnyx_call_registry.upsert(
            call_control_id,
            {
                "stream_error": last_err,
                "stream_failed": True,
                "stream_connected": False,
                "stream_api_ok": False,
                "stream_state": "failed",
                "stream_retry_count": new_retry,
                "status": "stream-error",
                "last_event": "streaming_start_failed",
            },
        )
        after = _stream_snapshot(telnyx_call_registry.get(call_control_id) or {})
        log_pstn(
            "PSTN_STREAM",
            call_id=call_control_id,
            control=call_control_id,
            event="stream_failed",
            reason=reason,
            before=before,
            after=after,
            retry_count=new_retry,
            error=last_err,
        )


async def _answer_inbound(call_control_id: str) -> None:
    """Keep the webhook ACK fast; retries share a carrier idempotency command ID."""
    try:
        client = TelnyxClient()
        for attempt in range(3):
            row = telnyx_call_registry.get(call_control_id) or {}
            if _call_ended(row) or row.get("answered_handled"):
                return
            try:
                await client.answer(call_control_id)
                telnyx_call_registry.upsert(call_control_id, {"answer_api_ok": True, "answer_error": None})
                log_pstn("answer.accepted", control=call_control_id)
                return
            except TelnyxApiError as exc:
                retryable = exc.status is None or exc.status == 429 or exc.status >= 500
                if not retryable or attempt == 2:
                    raise
                await asyncio.sleep(0.25 * (2 ** attempt))
    except Exception as exc:
        telnyx_call_registry.upsert(call_control_id, {"answer_error": str(exc)[:200], "answer_failed": True})
        log_pstn("answer.failed", control=call_control_id, error=str(exc)[:200])
        logger.exception("[TELNYX] inbound answer failed control=%s", call_control_id)


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
    if call_control_id and (patch.get("direction") == "inbound" or (telnyx_call_registry.get(str(call_control_id)) or {}).get("direction") == "inbound"):
        existing = telnyx_call_registry.get(str(call_control_id)) or {}
        if not existing.get("agent_id"):
            from server.services.saas.inbound_routing import resolve_inbound_route

            route = await resolve_inbound_route(str(payload.get("to") or patch.get("to") or ""))
            if route is not None:
                telnyx_call_registry.upsert(
                    str(call_control_id),
                    {
                        "agent_id": str(route.agent_id),
                        "tier": route.tier,
                        "language": route.language,
                        "stack_override": route.stack_override,
                        "tenant_id": str(route.tenant_id),
                        "saas_inbound": True,
                    },
                )
            elif payload.get("to") or patch.get("to"):
                from server.services.saas.inbound_routing import _normalize_e164
                from server.db.connection import get_session_factory
                from server.db.models.phase5_models import PhoneNumber
                from sqlalchemy import select

                factory = get_session_factory()
                to_num = _normalize_e164(str(payload.get("to") or patch.get("to") or ""))
                if factory and to_num:
                    async with factory() as session:
                        owned = await session.execute(select(PhoneNumber).where(PhoneNumber.e164 == to_num))
                        if owned.scalar_one_or_none() is not None:

                            async def _hangup_unrouted() -> None:
                                try:
                                    await TelnyxClient().hangup(str(call_control_id))
                                except Exception:
                                    pass

                            asyncio.create_task(_hangup_unrouted(), name=f"saas-hangup-{str(call_control_id)[:20]}")
    if payload.get("client_state"):
        try:
            import base64
            import json

            meta = json.loads(base64.b64decode(str(payload["client_state"])).decode())
            if isinstance(meta, dict):
                existing = telnyx_call_registry.get(str(call_control_id)) or {}
                recovered = {k: meta[k] for k in (
                    "agent_id", "tier", "source_session_id", "inherit_test_studio_config",
                    "stack_override", "language", "direction",
                ) if meta.get(k) is not None and existing.get(k) is None}
                # Signed client_state describes the application dial leg; a
                # provider's incoming/outgoing view must not turn it into a new
                # inbound call and trigger a second answer path.
                if meta.get("direction") == "outbound":
                    recovered["direction"] = "outbound"
                telnyx_call_registry.upsert(str(call_control_id), recovered)
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
        row = telnyx_call_registry.get(str(call_control_id)) or {}
        if call_control_id and row.get("direction") == "inbound" and not _call_ended(row):
            claimed = await telnyx_call_registry.atomic_check_and_set(str(call_control_id), "answer_requested")
            if claimed:
                asyncio.create_task(_answer_inbound(str(call_control_id)), name=f"telnyx-answer-{str(call_control_id)[:24]}")
    elif event_type == "call.answered":
        if _call_ended(telnyx_call_registry.get(str(call_control_id)) or {}):
            return {"ok": True}
        # answered_handled only dedupes answer side-effects; streaming recovery stays
        # available via streaming.failed even after this claim.
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
            # Always verify/start media — dial-time stream_url is NOT proof of active stream.
            # Run off the webhook await path so Telnyx transport blips can retry without
            # stalling the answered ACK (and without holding the event loop on one request).
            cid = str(call_control_id)

            async def _bg_ensure() -> None:
                try:
                    await _ensure_telnyx_streaming(cid, reason="answered")
                    _watch_stream_connect(cid)
                except Exception:
                    logger.exception("[PSTN_STREAM] background ensure crashed control=%s", cid)
                    return
                asyncio.create_task(
                    _start_answered_recording(cid),
                    name=f"telnyx-record-{cid[:24]}",
                )

            asyncio.create_task(_bg_ensure(), name=f"telnyx-ensure-{cid[:24]}")
    elif event_type in ("streaming.started", "call.streaming.started"):
        live = telnyx_call_registry.get(str(call_control_id)) or {}
        if _call_ended(live):
            return {"ok": True}
        before = _stream_snapshot(live)
        telnyx_call_registry.upsert(
            str(call_control_id),
            {
                "stream_provider_started": True,
                "stream_started": True,  # legacy alias
                "stream_failed": False,
                "stream_state": "connected" if live.get("stream_connected") else "provider_started_awaiting_ws",
                "status": "streaming",
            },
        )
        after = _stream_snapshot(telnyx_call_registry.get(str(call_control_id)) or {})
        log_pstn(
            "PSTN_STREAM",
            call_id=call_control_id,
            control=call_control_id,
            event="stream_connected",
            before=before,
            after=after,
        )
        log_pstn("webhook.streaming_started", timer_key=str(call_control_id), control=call_control_id)
    elif event_type in ("streaming.failed", "call.streaming.failed", "streaming.stopped"):
        fail_reason = payload.get("failure_reason") or payload.get("reason") or event_type
        before_row = telnyx_call_registry.get(str(call_control_id)) or {}
        before = _stream_snapshot(before_row)
        reason_l = str(fail_reason).lower()
        is_stopped = str(event_type).endswith("stopped")
        hard_fail = (
            str(event_type).endswith("failed")
            or "fail" in reason_l
            or "error" in reason_l
            or reason_l in {"connection_failed", "streaming.failed"}
        )
        # Ring-time / hangup cleanup: do not restart. After answer, hard failures retry.
        if _call_ended(before_row) or not before_row.get("answered_handled"):
            normal_stop = True
        elif hard_fail:
            normal_stop = False
        else:
            # Clean streaming.stopped on a live answered call usually means natural end.
            normal_stop = True
        telnyx_call_registry.upsert(
            str(call_control_id),
            {
                "stream_connected": False,
                "stream_started": False,
                "stream_failed": not normal_stop,
                "stream_state": "stopped" if normal_stop else "failed",
                "stream_error": str(fail_reason)[:300],
                "status": (
                    before_row.get("status")
                    if _call_ended(before_row)
                    else ("stream-stopped" if normal_stop else "stream-error")
                ),
            },
        )
        log_pstn(
            "PSTN_STREAM",
            call_id=call_control_id,
            control=call_control_id,
            event="stream_stopped" if normal_stop else "stream_failed",
            reason=fail_reason,
            before=before,
            after=_stream_snapshot(telnyx_call_registry.get(str(call_control_id)) or {}),
            normal_stop=normal_stop,
            hard_fail=hard_fail,
        )
        if normal_stop:
            logger.info(
                "[TELNYX] streaming %s (no retry) %s reason=%s",
                "stopped" if is_stopped else "ignored",
                call_control_id,
                fail_reason,
            )
        else:
            logger.warning("[TELNYX] streaming failed %s %s", call_control_id, payload)
            row_now = telnyx_call_registry.get(str(call_control_id)) or {}
            if call_control_id and not row_now.get("skip_stream") and not _call_ended(row_now):
                await _ensure_telnyx_streaming(str(call_control_id), reason="streaming_failed")
    elif event_type in ("call.recording.saved", "recording.saved", "call.recording.saved.v1"):
        logger.info("[TELNYX] recording saved %s", payload.get("recording_urls"))
        from server.services.telnyx_recordings import ingest_recording_saved

        asyncio.create_task(
            ingest_recording_saved(str(call_control_id), payload if isinstance(payload, dict) else {}),
            name=f"telnyx-rec-{str(call_control_id)[:24]}",
        )
    elif event_type in ("call.hangup", "call.failed"):
        from server.services.pstn_prewarm import cancel_prewarm

        if call_control_id:
            hangup_cause = payload.get("hangup_cause") or payload.get("sip_hangup_cause")
            telnyx_call_registry.upsert(
                str(call_control_id),
                {
                    "ended": True,
                    "stream_connected": False,
                    "stream_state": "ended",
                    "hangup_cause": hangup_cause,
                    "status": "hangup" if event_type == "call.hangup" else "failed",
                },
            )
            await cancel_prewarm("telnyx", str(call_control_id))
            from server.services.telnyx_pstn_bridge import active_telnyx_bridges

            bridge = active_telnyx_bridges.get(str(call_control_id))
            if bridge:
                asyncio.create_task(bridge._cleanup("caller_disconnected"))
            watchdog = _stream_watchdogs.pop(str(call_control_id), None)
            if watchdog:
                watchdog.cancel()
            _stream_op_locks.pop(str(call_control_id), None)
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
