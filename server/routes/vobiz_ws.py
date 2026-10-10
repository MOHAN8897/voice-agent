"""Vobiz Media Stream WebSocket endpoint — handles real-time bidirectional audio."""
from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket

from server.services.pstn_debug import log_pstn
from server.services.vobiz_client import vobiz_call_registry, vobiz_stream_tokens
from server.services.vobiz_pstn_bridge import VobizPstnBridge

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/vobiz-stream")
async def vobiz_stream_ws(websocket: WebSocket):
    await websocket.accept()
    q = websocket.query_params
    token = q.get("token")
    token_meta = vobiz_stream_tokens.peek(token) if token else None

    if not token_meta:
        # A public media socket must prove possession of a server-issued token.
        # Falling back to an untrusted start payload would create unbillable/spoofed sessions.
        log_pstn("vobiz.stream.unauthorized", hint="Missing or expired Vobiz stream token")
        await websocket.close(code=1008, reason="Invalid or expired stream token")
        return

    call_uuid = q.get("call_uuid") or (token_meta or {}).get("call_uuid")
    registry_meta = vobiz_call_registry.get(str(call_uuid)) if call_uuid else None
    merged_meta = {**(registry_meta or {}), **(token_meta or {})}

    bridge = VobizPstnBridge(websocket)
    log_pstn(
        "vobiz.ws.accept",
        ws_id=bridge.ws_id,
        call_uuid=call_uuid,
        agent_id=merged_meta.get("agent_id"),
    )

    try:
        await bridge.run(
            agent_id=merged_meta.get("agent_id"),
            tier=merged_meta.get("tier"),
            token_meta=merged_meta or None,
        )
    finally:
        if token:
            vobiz_stream_tokens.consume(token)
