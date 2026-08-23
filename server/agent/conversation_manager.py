"""
Conversation manager — server/agent/conversation_manager.py
Session-based history, trim oldest, per-session TTL, char caps on stored turns.
"""
from __future__ import annotations

import threading
import time
import uuid

Message = dict  # {role: "user"|"assistant", content: str}

DEFAULT_MAX_ASSISTANT_CHARS = 120
DEFAULT_MAX_USER_CHARS = 300


class ConversationManager:
    def __init__(
        self,
        max_messages: int | None = None,
        ttl_seconds: int = 30 * 60,
        max_assistant_chars: int = DEFAULT_MAX_ASSISTANT_CHARS,
        max_user_chars: int = DEFAULT_MAX_USER_CHARS,
    ):
        self.max_messages = int(max_messages if max_messages is not None else 8)
        self.ttl_seconds = ttl_seconds
        self.max_assistant_chars = max_assistant_chars
        self.max_user_chars = max_user_chars
        self._store: dict[str, dict] = {}
        self._lock = threading.RLock()

    def _ensure(self, session_id: str) -> dict:
        now = time.time()
        with self._lock:
            stale = [k for k, v in self._store.items() if now - v["updatedAt"] > self.ttl_seconds]
            for k in stale:
                del self._store[k]
            if session_id not in self._store:
                self._store[session_id] = {"messages": [], "updatedAt": now, "turnCount": 0}
            return self._store[session_id]

    def _truncate_content(self, role: str, text: str) -> str:
        cap = self.max_assistant_chars if role == "assistant" else self.max_user_chars
        text = text.strip()
        if len(text) <= cap:
            return text
        return text[:cap] + "…"

    def get_history(self, session_id: str) -> list[Message]:
        sess = self._ensure(session_id)
        with self._lock:
            return list(sess["messages"])

    def get_context_for_brain(self, session_id: str, *, max_turns: int = 2) -> list[Message]:
        """Last N complete turns (user+assistant pairs) for brain input. Current transcript is separate."""
        history = self.get_history(session_id)
        if max_turns <= 0:
            return []
        cap = max_turns * 2
        return history[-cap:] if len(history) > cap else history

    def get_turn_number(self, session_id: str) -> int:
        """1-based turn number for the next brain request (before add_turn)."""
        sess = self._ensure(session_id)
        with self._lock:
            return int(sess.get("turnCount", 0)) + 1

    def get_completed_turns(self, session_id: str) -> int:
        """Number of completed user+assistant turns in session."""
        sess = self._ensure(session_id)
        with self._lock:
            return int(sess.get("turnCount", 0))

    def add_turn(self, session_id: str, user_text: str, assistant_text: str) -> None:
        sess = self._ensure(session_id)
        with self._lock:
            sess["messages"].append(
                {"role": "user", "content": self._truncate_content("user", user_text)}
            )
            sess["messages"].append(
                {"role": "assistant", "content": self._truncate_content("assistant", assistant_text)}
            )
            sess["turnCount"] = int(sess.get("turnCount", 0)) + 1
            sess["updatedAt"] = time.time()
            self._trim(sess)

    def add_user_only(self, session_id: str, user_text: str) -> None:
        sess = self._ensure(session_id)
        with self._lock:
            sess["messages"].append(
                {"role": "user", "content": self._truncate_content("user", user_text)}
            )
            sess["updatedAt"] = time.time()
            self._trim(sess)

    def _trim(self, sess: dict) -> None:
        msgs = sess["messages"]
        if len(msgs) > self.max_messages:
            sess["messages"] = msgs[-self.max_messages :]

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._store.pop(session_id, None)

    def stats(self) -> dict:
        with self._lock:
            return {
                "sessions": len(self._store),
                "total_messages": sum(len(v["messages"]) for v in self._store.values()),
            }

    def new_session_id(self) -> str:
        return str(uuid.uuid4())


conversation_manager = ConversationManager(max_messages=8)
