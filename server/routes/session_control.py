"""
Session control — barge-in: stop playback, reconcile history to what the caller heard.
"""
from __future__ import annotations

from fastapi import APIRouter

from server.agent.conversation_manager import conversation_manager
from server.call import call_context
from server.utils.metrics import metrics

router = APIRouter()


@router.post("/api/session/interrupt")
async def interrupt_session(body: dict):
    """
    Barge-in from browser (or PSTN loop): caller committed an interrupt.
    Body: {sessionId, callId?, heardText?}
    """
    session_id = str(body.get("sessionId") or "default")
    call_id = str(body.get("callId") or "").strip() or None
    heard = str(body.get("heardText") or "")
    conversation_manager.note_barge(session_id, heard)
    if call_id:
        ctx = call_context.get(call_id)
        if ctx:
            ctx.barge_in_flight = True
            ctx.agent_hangup_armed = False
    else:
        ctx = call_context.get_active_for_session(session_id)
        if ctx:
            ctx.barge_in_flight = True
            ctx.agent_hangup_armed = False
    metrics.record_error("session", "barge_in")
    return {"ok": True, "sessionId": session_id, "state": "INTERRUPTED"}


@router.get("/api/session/history")
async def get_history(sessionId: str = "default"):
    history = conversation_manager.get_history(sessionId)
    return {"sessionId": sessionId, "messages": history, "count": len(history)}
