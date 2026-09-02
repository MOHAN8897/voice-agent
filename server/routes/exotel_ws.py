"""Exotel AgentStream WebSocket — /ws/exotel-stream"""
from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from server.services.exotel_pstn_bridge import ExotelPstnBridge
from server.services.exotel_stream_tokens import exotel_stream_tokens

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws/exotel-stream")
async def exotel_stream_ws(websocket: WebSocket):
    token = websocket.query_params.get("token")
    agent_id = websocket.query_params.get("agentId") or websocket.query_params.get("agent_id")
    tier = websocket.query_params.get("tier")
    token_meta = exotel_stream_tokens.consume(token) if token else None
    if token and not token_meta and not agent_id:
        await websocket.close(code=4001)
        return

    await websocket.accept()
    bridge = ExotelPstnBridge(websocket)
    try:
        await bridge.run(agent_id=agent_id, tier=tier, token_meta=token_meta)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("[EXOTEL] ws error: %s", str(e)[:200])
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
