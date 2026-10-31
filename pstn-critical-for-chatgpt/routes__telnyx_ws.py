"""Telnyx media stream WebSocket."""
from __future__ import annotations

from fastapi import APIRouter, WebSocket

from server.services.pstn_debug import log_pstn
from server.services.telnyx_client import telnyx_stream_tokens
from server.services.telnyx_pstn_bridge import TelnyxPstnBridge

router = APIRouter()


@router.websocket("/ws/telnyx-stream")
async def telnyx_stream_ws(websocket: WebSocket):
    await websocket.accept()
    q = websocket.query_params
    token = q.get("token")
    token_meta = telnyx_stream_tokens.peek(token) if token else None
    bridge = TelnyxPstnBridge(websocket)
    log_pstn(
        "ws.accept",
        ws_id=bridge.ws_id,
        agent_id=q.get("agent_id") or (token_meta or {}).get("agent_id"),
    )
    await bridge.run(
        agent_id=q.get("agent_id") or (token_meta or {}).get("agent_id"),
        tier=q.get("tier") or (token_meta or {}).get("tier"),
        token_meta=token_meta,
    )
