"""Plivo answer URL + stream WebSocket."""
from __future__ import annotations

from fastapi import APIRouter, Request, WebSocket, Response

from server.config.urls import public_api_base
from server.services.plivo_client import plivo_stream_tokens, PlivoClient
from server.services.plivo_pstn_bridge import PlivoPstnBridge

router = APIRouter()


@router.get("/api/plivo/answer")
async def plivo_answer(request: Request):
    token = request.query_params.get("token")
    if not token:
        token = plivo_stream_tokens.create()
    base = public_api_base().rstrip("/")
    ws = base.replace("https://", "wss://").replace("http://", "ws://")
    stream_url = f"{ws}/ws/plivo-stream?token={token}"
    client = PlivoClient()
    xml = client.answer_xml(stream_url)
    return Response(content=xml, media_type="application/xml")


@router.websocket("/ws/plivo-stream")
async def plivo_stream_ws(websocket: WebSocket):
    await websocket.accept()
    q = websocket.query_params
    token = q.get("token")
    token_meta = plivo_stream_tokens.consume(token) if token else None
    bridge = PlivoPstnBridge(websocket)
    await bridge.run(
        agent_id=q.get("agent_id") or (token_meta or {}).get("agent_id"),
        tier=q.get("tier") or (token_meta or {}).get("tier"),
        token_meta=token_meta,
    )
