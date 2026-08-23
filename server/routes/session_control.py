"""
Session control — server/routes/session_control.py
POST /api/session/interrupt → barge-in: client signals it stopped playback, server clears transient state
Also handles history clear (moved from brain.py for cohesion)
"""
from __future__ import annotations

from fastapi import APIRouter

from server.agent.conversation_manager import conversation_manager
from server.utils.metrics import metrics

router = APIRouter()


@router.post("/api/session/interrupt")
async def interrupt_session(body: dict):
    """
    Barge-in signal from client: user started speaking while agent was speaking.
    Body: {sessionId}
    For Phase 5 MVP, this is a no-op server-side except logging + metric; real barge-in is client-side:
      - client stops HTMLAudioElement immediately (<150ms target)
      - aborts any in-flight fetch via AbortController
      - optionally clears pending TTS queue
    Server records interrupt for metrics.
    """
    session_id = body.get("sessionId", "default")
    # Could also clear some transient state if we held streaming buffers
    metrics.record_error("session", "barge_in")
    return {"ok": True, "sessionId": session_id, "state": "INTERRUPTED", "message": "Barge-in acknowledged — client should have flushed audio and aborted brain/TTS fetch."}


@router.get("/api/session/history")
async def get_history(sessionId: str = "default"):
    history = conversation_manager.get_history(sessionId)
    return {"sessionId": sessionId, "messages": history, "count": len(history)}
