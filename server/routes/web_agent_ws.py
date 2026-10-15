"""Browser web-agent WebSocket — same realtime_voice loop as PSTN."""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from server.auth.subscriber_dependencies import principal_from_verified_token
from server.services.saas.pstn_saas_stack import saas_stack_override_for_agent
from server.services.saas.tenant_guard import subscriber_workspace_tenant_id
from server.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)
router = APIRouter()
_web_agent_limiter = RateLimiter(max_requests=20, window_s=60)
_WEB_AGENT_SUBPROTOCOL = "voxly-web-agent"
_WEB_AGENT_AUTH_PROTOCOL_PREFIX = "voxly-auth."


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
        except Exception as brain_err:
            logger.warning("[WEB_AGENT] Could not auto-compile brain for agent %s: %s", agent_id, brain_err)
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

    stack = await saas_stack_override_for_agent(agent)
    req_lang = (websocket.query_params.get("language") or "").strip()
    if req_lang:
        from server.config.constants import normalize_supported_language
        norm_req_lang = normalize_supported_language(req_lang)
        stack["language"] = norm_req_lang
        lang = norm_req_lang
    else:
        lang = str(stack.get("language") or (agent.get("languages") or ["te-IN"])[0] or "te-IN")
    session_id = f"web-agent-{principal.user_id}-{agent_id}-{uuid.uuid4().hex[:8]}"[:100]
    from server.call.call_lifecycle_service import call_lifecycle_service
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    call_id: str | None = None
    loop: PstnRealtimeVoiceLoop | None = None
    closed = False
    end_reason = "user_stop"
    hangup_complete_sent = False

    async def send_event(payload: dict) -> None:
        if closed:
            return
        await _send(websocket, payload)

    async def on_agent_wire(pcm: bytes) -> None:
        if closed or not pcm:
            return
        try:
            await websocket.send_bytes(pcm)
        except Exception:
            pass

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
        started = await call_lifecycle_service.start(
            agent_id=agent_id,
            session_id=session_id,
            channel="browser",
            direction="inbound",
            # A browser practice run, not a conversation: excluded from call
            # rollups and never archived to disk.
            is_test=True,
            language=str(lang),
            stack_override=stack,
            billed_user_id=str(principal.user_id),
        )
        call_id = started["call_id"]
        loop = PstnRealtimeVoiceLoop(
            session_id=started["session_id"],
            call_id=call_id,
            on_agent_wire=on_agent_wire,
            sample_rate=16000,
            tts_output_codec="linear16",
            stack_override=stack,
            tenant_id=workspace_tenant_id,
            agent_id=str(agent_id),
            channel="browser",
        )
        loop.set_hangup_notice_handler(on_hangup_notice)
        loop.set_hangup_handler(on_provider_hangup)
        await loop.start_call(play_greeting=True)
        llm = stack.get("llm") if isinstance(stack.get("llm"), dict) else {}
        connected_adapter = getattr(loop, "_adapter", None)
        active_provider = getattr(loop, "_llm_provider", None) or (
            "gemini"
            if connected_adapter and connected_adapter.__class__.__name__ == "GeminiLiveVoiceAdapter"
            else "openai"
        )
        active_model = getattr(connected_adapter, "model", None) or str(llm.get("model") or "")
        await send_event(
            {
                "type": "ready",
                "callId": call_id,
                "pipeline": started.get("pipeline"),
                "sampleRate": 16000,
                "voiceProvider": active_provider,
                "voiceModel": active_model,
            }
        )

        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            data = message.get("bytes")
            if data:
                await loop.feed_user_pcm16(data)
                continue
            text = message.get("text")
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            kind = str(payload.get("type") or "")
            if kind in {"end", "hangup", "stop"}:
                end_reason = "user_stop"
                if loop:
                    await loop.close()
                break
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("[WEB_AGENT] session failed call=%s", call_id)
        raw_msg = str(exc)
        if "API key" in raw_msg or "denied access" in raw_msg or "quota" in raw_msg.lower():
            user_msg = "Voice provider connection failed. Please verify API configuration or try again."
        elif "timeout" in raw_msg.lower():
            user_msg = "Voice provider connection timed out. Please try again."
        else:
            user_msg = "Voice session could not be established. Please try again."
        try:
            from server.services.saas.session_failure_log import record_session_failure

            record_session_failure(
                channel="web_agent",
                code="session_failed",
                message=user_msg,
                agent_id=agent_id,
                tenant_id=str(getattr(principal, "tenant_id", "") or ""),
                call_id=call_id,
                detail=str(exc),
            )
        except Exception:
            pass
        await send_event({"type": "error", "code": "session_failed", "message": user_msg})
    finally:
        closed = True
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
