"""Browser web-agent WebSocket — same realtime_voice loop as PSTN."""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from server.auth.subscriber_dependencies import principal_from_verified_token
from server.services.saas.pstn_saas_stack import saas_stack_override_for_agent
from server.services.saas.tenant_guard import subscriber_workspace_tenant_id
from server.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)
router = APIRouter()
_web_agent_limiter = RateLimiter(max_requests=20, window_s=60)
_WEB_AGENT_SUBPROTOCOL = "dialtact-web-agent"
_WEB_AGENT_AUTH_PROTOCOL_PREFIX = "dialtact-auth."


def _ws_token(ws: WebSocket) -> str:
    offered_protocols = ws.scope.get("subprotocols") or []
    for protocol in offered_protocols:
        candidate = str(protocol or "").strip()
        if candidate.startswith(_WEB_AGENT_AUTH_PROTOCOL_PREFIX):
            token = candidate[len(_WEB_AGENT_AUTH_PROTOCOL_PREFIX):].strip()
            if token:
                return token
    q = ws.query_params.get("token") or ""
    if q.strip():
        return q.strip()
    auth = ws.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return ""


@router.websocket("/ws/web-agent")
async def web_agent_ws(websocket: WebSocket):
    offered_protocols = websocket.scope.get("subprotocols") or []
    selected_protocol = _WEB_AGENT_SUBPROTOCOL if _WEB_AGENT_SUBPROTOCOL in offered_protocols else None
    await websocket.accept(subprotocol=selected_protocol)
    token = _ws_token(websocket)
    agent_id = (websocket.query_params.get("agentId") or websocket.query_params.get("agent_id") or "").strip()
    if not token or not agent_id:
        await _send(websocket, {"type": "error", "code": "auth_error", "message": "Sign in and select an agent."})
        await websocket.close(code=1008)
        return
    try:
        principal = await principal_from_verified_token(token)
    except Exception as exc:
        detail = getattr(exc, "detail", None)
        message = "Invalid session"
        if isinstance(detail, dict):
            message = (detail.get("error") or {}).get("message") or message
        await _send(websocket, {"type": "error", "code": "auth_error", "message": message})
        await websocket.close(code=1008)
        return

    allowed, retry = _web_agent_limiter.allow(f"web:{principal.user_id}")
    if not allowed:
        await _send(
            websocket,
            {"type": "error", "code": "rate_limit", "message": "Too many test sessions.", "retryAfter": retry},
        )
        await websocket.close(code=1008)
        return

    from server.brain.agent_service import agent_service
    from server.services.saas.billing_wallet_service import assert_wallet_allows_usage

    workspace_tenant_id = str(subscriber_workspace_tenant_id(principal))
    try:
        agent = await agent_service.get_agent(agent_id, tenant_id=workspace_tenant_id)
    except Exception:
        await _send(websocket, {"type": "error", "code": "not_found", "message": "Agent not found."})
        await websocket.close(code=1008)
        return
    status = str(agent.get("status") or "").strip().lower()
    if status in {"disabled"}:
        from server.services.saas.session_failure_log import record_session_failure

        record_session_failure(
            channel="web_agent",
            code="agent_disabled",
            message="Agent is disabled",
            agent_id=agent_id,
            tenant_id=str(principal.tenant_id),
        )
        await _send(
            websocket,
            {
                "type": "error",
                "code": "agent_disabled",
                "message": "This agent is disabled.",
            },
        )
        await websocket.close(code=1008)
        return

    # If the compiled brain has not been published yet, auto-compile on first access
    if not agent.get("active_compiled_brain_version"):
        from server.brain.compiled_brain_service import compiled_brain_service
        try:
            active_snap = await compiled_brain_service.get_active_for_agent(agent_id)
            if active_snap and active_snap.get("compiled_version"):
                agent["active_compiled_brain_version"] = active_snap["compiled_version"]
            else:
                from server.brain.business_brain_store import business_brain_store
                draft = await business_brain_store.get_draft(agent_id)
                sections = (draft or {}).get("sections")
                if sections:
                    compiled = await compiled_brain_service.compile_draft(agent_id, sections)
                    if compiled and compiled.get("compiled_version"):
                        agent["active_compiled_brain_version"] = compiled["compiled_version"]
        except Exception as brain_err:
            logger.warning("[WEB_AGENT] Could not auto-compile brain for agent %s: %s", agent_id, brain_err)
    if not agent.get("active_compiled_brain_version"):
        await _send(
            websocket,
            {
                "type": "error",
                "code": "brain_not_published",
                "message": "Publish this agent's script before testing live voice.",
            },
        )
        await websocket.close(code=1008)
        return
    try:
        await assert_wallet_allows_usage(principal.tenant_id)
    except Exception as exc:
        detail = getattr(exc, "detail", None)
        message = "Add funds to your wallet before testing live voice."
        code = "insufficient_balance"
        if isinstance(detail, dict):
            err = detail.get("error") or {}
            message = err.get("message") or message
            code = err.get("code") or code
        await _send(websocket, {"type": "error", "code": code, "message": message})
        await websocket.close(code=1008)
        return

    import uuid

    req_lang = (websocket.query_params.get("language") or "").strip()
    if req_lang:
        from server.config.constants import normalize_supported_language
        norm_req_lang = normalize_supported_language(req_lang)
        # Resolve the entire profile for the requested language so recognition,
        # speech and catalog validation agree before any provider is opened.
        agent_for_voice = {**agent, "languages": [norm_req_lang]}
    else:
        agent_for_voice = agent
    session_id = f"web-agent-{principal.user_id}-{agent_id}-{uuid.uuid4().hex[:8]}"[:100]
    from server.call.call_lifecycle_service import call_lifecycle_service
    from server.services.pstn_voice_flow import create_pstn_voice_loop, is_realtime_e2e_stack

    call_id: str | None = None
    loop: Any = None
    closed = False
    end_reason = "user_stop"
    hangup_complete_sent = False
    from server.services.pstn_playback import EstimatedPlaybackTracker

    playback = EstimatedPlaybackTracker(frame_ms=20.0)
    sent_audio = False

    async def send_event(payload: dict) -> None:
        if closed:
            return
        await _send(websocket, payload)

    async def on_agent_wire(pcm: bytes) -> None:
        nonlocal sent_audio
        if closed or not pcm:
            return
        # The composed loop tracks its own 20 ms frames. The realtime loop
        # delegates transport accounting to this callback.
        if realtime_voice:
            playback.note_sent_frames((len(pcm) + 639) // 640)
        await websocket.send_bytes(pcm)
        if not sent_audio:
            sent_audio = True
            from server.call.billing_timing import mark_call_connected
            mark_call_connected(call_id)
            logger.info("[WEB_AGENT] first speaker frame call=%s bytes=%s", call_id, len(pcm))

    async def on_hangup_notice(stage: str, reason: str) -> None:
        nonlocal end_reason, hangup_complete_sent
        if stage == "initiated":
            end_reason = str(reason or "agent_hangup")
            await send_event(
                {
                    "type": "hangup_initiated",
                    "stage": stage,
                    "reason": end_reason,
                    "message": "Hangup initiated — the agent is ending the call.",
                }
            )
            return
        if stage != "complete" or hangup_complete_sent:
            return
        hangup_complete_sent = True
        await send_event(
            {
                "type": "hangup_complete",
                "stage": stage,
                "reason": str(reason or end_reason),
                "message": "The agent hung up. Session closed.",
            }
        )

    async def on_provider_hangup() -> None:
        await on_hangup_notice("complete", end_reason)
        try:
            await websocket.close(code=1000)
        except Exception:
            pass

    try:
        stack = await saas_stack_override_for_agent(agent_for_voice)
        if req_lang:
            stack["language"] = norm_req_lang
        lang = str(stack.get("language") or (agent_for_voice.get("languages") or ["te-IN"])[0] or "te-IN")
        realtime_voice = is_realtime_e2e_stack(stack)
        resolved_tier = (stack.get("_voice_stack_snapshot") or {}).get("tier") or agent_for_voice.get("default_tier")
        started = await call_lifecycle_service.start(
            agent_id=agent_id,
            tenant_id=workspace_tenant_id,
            session_id=session_id,
            channel="browser",
            direction="inbound",
            # A browser practice run, not a conversation: excluded from call
            # rollups and never archived to disk.
            is_test=True,
            language=str(lang),
            tier=str(resolved_tier) if resolved_tier else None,
            stack_override=stack,
            billed_user_id=str(principal.user_id),
        )
        call_id = started["call_id"]
        loop_kwargs = dict(
            session_id=started["session_id"],
            call_id=call_id,
            on_agent_wire=on_agent_wire,
            sample_rate=16000,
            tts_output_codec="linear16",
            stack_override=stack,
            playback=playback,
            is_agent_audio_active=playback.is_active,
        )
        if realtime_voice:
            loop_kwargs.update(tenant_id=workspace_tenant_id, agent_id=str(agent_id), channel="browser")
        loop = create_pstn_voice_loop(**loop_kwargs)
        if hasattr(loop, "set_hangup_notice_handler"):
            loop.set_hangup_notice_handler(on_hangup_notice)
        if hasattr(loop, "set_hangup_handler"):
            loop.set_hangup_handler(on_provider_hangup)
        async def clear_browser_audio() -> None:
            playback.clear()
            await send_event({"type": "clear_audio"})

        if hasattr(loop, "set_barge_handler"):
            loop.set_barge_handler(clear_browser_audio)
        if hasattr(loop, "set_error_handler"):
            async def notify_voice_error(message: str) -> None:
                nonlocal end_reason
                end_reason = "voice_turn_failed"
                await send_event({"type": "error", "code": "voice_turn_failed", "message": message})

            loop.set_error_handler(notify_voice_error)
        async def notify_ready() -> None:
            from server.call.billing_timing import mark_call_connected
            mark_call_connected(call_id)
            voice_label = "Live voice"
            if started.get("pipeline") == "composed_voice":
                snapshot = stack.get("_voice_stack_snapshot") or {}
                voice_label = {"low": "Economical", "medium": "Standard"}.get(
                    str(snapshot.get("tier") or agent.get("default_tier") or ""), "Selected voice"
                )
            await send_event({
                "type": "ready",
                "callId": call_id,
                "pipeline": started.get("pipeline"),
                "sampleRate": 16000,
                "voiceProvider": "Enterprise Voice Network",
                "voiceModel": voice_label,
            })

        await _drive_browser_voice(websocket, loop, notify_ready)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("[WEB_AGENT] session failed call=%s", call_id)
        from server.services.saas.voice_setup_errors import voice_setup_error

        setup_error = voice_setup_error(exc)
        raw_msg = str(exc)
        if setup_error:
            user_msg = setup_error["message"]
        elif "API key" in raw_msg or "denied access" in raw_msg or "quota" in raw_msg.lower():
            user_msg = "Voice provider connection failed. Please verify API configuration or try again."
        elif "timeout" in raw_msg.lower():
            user_msg = "Voice provider connection timed out. Please try again."
        else:
            user_msg = "Voice session could not be established. Please try again."
        try:
            from server.services.saas.session_failure_log import record_session_failure

            record_session_failure(
                channel="web_agent",
                code=setup_error["code"] if setup_error else "session_failed",
                message=user_msg,
                agent_id=agent_id,
                tenant_id=str(getattr(principal, "tenant_id", "") or ""),
                call_id=call_id,
                detail=str(exc),
            )
        except Exception:
            pass
        await send_event({"type": "error", "code": setup_error["code"] if setup_error else "session_failed", "message": user_msg})
    finally:
        closed = True
        from server.call.billing_timing import mark_call_disconnected
        mark_call_disconnected(call_id)
        if loop is not None:
            try:
                await loop.close()
            except Exception:
                pass
        if call_id:
            try:
                await call_lifecycle_service.end(call_id, reason=end_reason)
            except Exception:
                pass


async def _send(ws: WebSocket, payload: dict) -> None:
    try:
        await ws.send_json(payload)
    except Exception:
        return


async def _drive_browser_voice(
    websocket: WebSocket, loop, notify_ready: Callable[[], Awaitable[None]],
    *, startup_timeout: float = 60.0,
) -> None:
    """Receive mic/stop/disconnect while the provider and opening are starting."""
    startup = asyncio.create_task(asyncio.wait_for(loop.start_call(play_greeting=True), startup_timeout))
    receiving = asyncio.create_task(websocket.receive())
    first_microphone_frame = True
    try:
        while True:
            pending = {receiving}
            if startup is not None:
                pending.add(startup)
            done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            if receiving in done:
                message = receiving.result()
                if message.get("type") == "websocket.disconnect":
                    return
                data = message.get("bytes")
                if data:
                    if first_microphone_frame:
                        first_microphone_frame = False
                        logger.info("[WEB_AGENT] first microphone frame bytes=%s", len(data))
                    await loop.feed_user_pcm16(data)
                elif message.get("text"):
                    try:
                        payload = json.loads(message["text"])
                    except (TypeError, json.JSONDecodeError):
                        payload = {}
                    if isinstance(payload, dict) and payload.get("type") in {"end", "hangup", "stop"}:
                        return
                receiving = asyncio.create_task(websocket.receive())
            if startup is not None and startup in done:
                startup.result()
                startup = None
                await notify_ready()
    finally:
        tasks = [task for task in (startup, receiving) if task is not None]
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
