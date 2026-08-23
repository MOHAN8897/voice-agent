"""
Session state machine — server/session/session_state.py
IDLE → LISTENING → PROCESSING_STT → THINKING → GENERATING_TTS → PLAYING → IDLE
"""
from __future__ import annotations

from enum import Enum


class SessionState(str, Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    PROCESSING_STT = "PROCESSING_STT"
    THINKING = "THINKING"
    GENERATING_TTS = "GENERATING_TTS"
    PLAYING = "PLAYING"
    ERROR = "ERROR"
    INTERRUPTED = "INTERRUPTED"


# UI labels per state
UI_LABELS: dict[SessionState, str] = {
    SessionState.IDLE: "Ready",
    SessionState.LISTENING: "Listening…",
    SessionState.PROCESSING_STT: "Understanding…",
    SessionState.THINKING: "Thinking…",
    SessionState.GENERATING_TTS: "Speaking…",
    SessionState.PLAYING: "Speaking…",
    SessionState.ERROR: "Error",
    SessionState.INTERRUPTED: "Interrupted",
}

# Allowed transitions (for validation)
ALLOWED_TRANSITIONS: dict[SessionState, set[SessionState]] = {
    SessionState.IDLE: {SessionState.LISTENING, SessionState.ERROR},
    SessionState.LISTENING: {SessionState.PROCESSING_STT, SessionState.IDLE, SessionState.ERROR},
    SessionState.PROCESSING_STT: {SessionState.THINKING, SessionState.ERROR, SessionState.IDLE},
    SessionState.THINKING: {SessionState.GENERATING_TTS, SessionState.PLAYING, SessionState.ERROR, SessionState.IDLE},
    SessionState.GENERATING_TTS: {SessionState.PLAYING, SessionState.ERROR, SessionState.IDLE},
    SessionState.PLAYING: {SessionState.IDLE, SessionState.INTERRUPTED, SessionState.ERROR, SessionState.LISTENING},
    SessionState.ERROR: {SessionState.IDLE},
    SessionState.INTERRUPTED: {SessionState.LISTENING, SessionState.IDLE},
}
