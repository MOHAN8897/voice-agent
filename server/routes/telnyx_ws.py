"""Telnyx media stream WebSocket."""
from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket

from server.services.pstn_debug import log_pstn
from server.services.telnyx_client import telnyx_call_registry, telnyx_stream_tokens
from server.services.telnyx_pstn_bridge import TelnyxPstnBridge

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/telnyx-stream")
async def telnyx_stream_ws(websocket: WebSocket):
    await websocket.accept()
    q = websocket.query_params
    token = q.get("token")
    token_meta = telnyx_stream_tokens.peek(token) if token else None
    if not token_meta:
        # A public media socket must prove possession of a server-issued token.
        # Falling back to an untrusted start payload would create billable sessions.
        log_pstn("stream.unauthorized", hint="Use Redis token mirrors for multiple workers")
        await websocket.close(code=1008, reason="Invalid or expired stream token")
        return
    # Optional recovery: query may carry call_control_id in some setups; else bridge
    # merges telnyx_call_registry on start using call_control_id from Telnyx.
    control_hint = q.get("call_control_id") or (token_meta or {}).get("call_control_id")
    registry_meta = telnyx_call_registry.get(str(control_hint)) if control_hint else None
    merged_meta = {**(registry_meta or {}), **(token_meta or {})}
    bridge = TelnyxPstnBridge(websocket)
    log_pstn(
        "ws.accept",
        ws_id=bridge.ws_id,
        agent_id=merged_meta.get("agent_id"),
        token_meta=bool(token_meta),
        registry_meta=bool(registry_meta),
    )
    await bridge.run(
        agent_id=merged_meta.get("agent_id"),
        tier=merged_meta.get("tier"),
        token_meta=merged_meta or None,
    )
