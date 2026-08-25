"""Plivo WebSocket stream — /ws/plivo-stream"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from server.routes.plivo import validate_stream_token
from server.services.plivo_stream import PlivoStreamSession, parse_plivo_event

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws/plivo-stream")
async def plivo_stream_ws(websocket: WebSocket):
    token = websocket.query_params.get("token")
    call_uuid = websocket.query_params.get("call_uuid")
    if not token or not validate_stream_token(token, call_uuid):
        await websocket.close(code=4001)
        return

    await websocket.accept()
    session = PlivoStreamSession(stream_id=call_uuid or "unknown")

    try:
        while True:
            raw = await websocket.receive_text()
            event = parse_plivo_event(raw)
            name = event.get("event") or event.get("name")

            if name == "start":
                session.handle_start(event)
                await websocket.send_text(json.dumps({"event": "connected", "streamId": session.stream_id}))
            elif name == "media":
                session.ingest_media(event)
            elif name == "stop":
                await websocket.send_text(json.dumps({"event": "stopped"}))
                break
            elif name == "clearAudio":
                await websocket.send_text(json.dumps(session.build_clear_audio()))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("plivo ws error: %s", str(e)[:200])
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
