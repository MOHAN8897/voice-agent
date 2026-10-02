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


def _ws_token(ws: WebSocket) -> str:
    q = ws.query_params.get("token") or ""
    if q.strip():
        return q.strip()
    auth = ws.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return ""


@router.websocket("/ws/web-agent")
async def web_agent_ws(websocket: WebSocket):
    await websocket.accept()
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
    if status in {"paused", "inactive", "disabled"}:
        from server.services.saas.session_failure_log import record_session_failure

        record_session_failure(
            channel="web_agent",
            code="agent_paused",
            message="Agent is paused",
            agent_id=agent_id,
            tenant_id=str(principal.tenant_id),
        )
        await _send(
            websocket,
            {
                "type": "error",
                "code": "agent_paused",
                "message": "This agent is paused. Switch it to Live in Settings before testing.",
            },
        )
        await websocket.close(code=1008)
        return
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

    stack = await saas_stack_override_for_agent(agent)
    lang = str(stack.get("language") or (agent.get("languages") or ["te-IN"])[0] or "te-IN")
    session_id = f"web-agent-{principal.user_id}-{agent_id}"[:100]
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
        )
        loop.set_hangup_notice_handler(on_hangup_notice)
        loop.set_hangup_handler(on_provider_hangup)
        await loop.start_call(play_greeting=True)
        llm = stack.get("llm") if isinstance(stack.get("llm"), dict) else {}
        await send_event(
            {
                "type": "ready",
                "callId": call_id,
                "pipeline": started.get("pipeline"),
                "sampleRate": 16000,
                "voiceProvider": str(llm.get("provider") or "openai"),
                "voiceModel": str(llm.get("model") or ""),
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
        try:
            from server.services.saas.session_failure_log import record_session_failure

            record_session_failure(
                channel="web_agent",
                code="session_failed",
                message="Voice session failed.",
                agent_id=agent_id,
                tenant_id=str(getattr(principal, "tenant_id", "") or ""),
                call_id=call_id,
                detail=str(exc),
            )
        except Exception:
            pass
        await send_event({"type": "error", "code": "session_failed", "message": "Voice session failed."})
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
