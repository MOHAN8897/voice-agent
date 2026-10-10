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
        # A public media socket must prove possession of a valid server-issued token.
        # Tokenless connections are rejected to prevent unauthenticated access.
        log_pstn("vobiz.stream.unauthorized", hint="Missing or expired Vobiz stream token")
        await websocket.close(code=1008, reason="Invalid or expired stream token")
        return

    expected_call_uuid = str(token_meta.get("call_uuid") or "")
    param_call_uuid = q.get("call_uuid")
    call_uuid = param_call_uuid or expected_call_uuid
    registry_meta = vobiz_call_registry.get(str(call_uuid)) if call_uuid else None

    if param_call_uuid and expected_call_uuid and param_call_uuid != expected_call_uuid:
        aliased = (registry_meta or {}).get("aliased_to")
        outbound = (registry_meta or {}).get("outbound_id")
        if aliased != expected_call_uuid and outbound != expected_call_uuid:
            log_pstn("vobiz.stream.mismatch", hint="Query call_uuid does not match token metadata", call_uuid=param_call_uuid)
            await websocket.close(code=1008, reason="Call UUID mismatch")
            return

    effective_call_uuid = expected_call_uuid or call_uuid
    merged_meta = {**(registry_meta or {}), **token_meta}

    bridge = VobizPstnBridge(websocket)
    log_pstn(
        "vobiz.ws.accept",
        ws_id=bridge.ws_id,
        call_uuid=effective_call_uuid,
        agent_id=merged_meta.get("agent_id"),
    )

    try:
        await bridge.run(
            agent_id=merged_meta.get("agent_id"),
            tier=merged_meta.get("tier"),
            token_meta=merged_meta or None,
        )
    finally:
        if token and (not effective_call_uuid or (vobiz_call_registry.get(str(effective_call_uuid)) or {}).get("ended")):
            vobiz_stream_tokens.consume(token)
