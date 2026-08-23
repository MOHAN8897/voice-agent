"""
Conversation manager — server/agent/conversation_manager.py
Session-based history, trim oldest, per-session TTL.
"""
from __future__ import annotations

import threading
import time
import uuid

Message = dict  # {role: "user"|"assistant", content: str}


class ConversationManager:
    def __init__(
        self,
        max_messages: int | None = None,
        ttl_seconds: int = 30 * 60,
    ):
        self.max_messages = int(max_messages if max_messages is not None else 12)
        self.ttl_seconds = ttl_seconds
        self._store: dict[str, dict] = {}  # sessionId -> {messages: List[Message], updatedAt: float}
        self._lock = threading.RLock()

    def _ensure(self, session_id: str) -> dict:
        now = time.time()
        with self._lock:
            # Evict stale
            stale = [k for k, v in self._store.items() if now - v["updatedAt"] > self.ttl_seconds]
            for k in stale:
                del self._store[k]
            if session_id not in self._store:
                self._store[session_id] = {"messages": [], "updatedAt": now}
            return self._store[session_id]

    def get_history(self, session_id: str) -> list[Message]:
        sess = self._ensure(session_id)
        with self._lock:
            return list(sess["messages"])

    def add_turn(self, session_id: str, user_text: str, assistant_text: str) -> None:
        sess = self._ensure(session_id)
        with self._lock:
            sess["messages"].append({"role": "user", "content": user_text})
            sess["messages"].append({"role": "assistant", "content": assistant_text})
            sess["updatedAt"] = time.time()
            self._trim(sess)

    def add_user_only(self, session_id: str, user_text: str) -> None:
        """If brain fails, still keep user turn for context."""
        sess = self._ensure(session_id)
        with self._lock:
            sess["messages"].append({"role": "user", "content": user_text})
            sess["updatedAt"] = time.time()
            self._trim(sess)

    def _trim(self, sess: dict) -> None:
        msgs = sess["messages"]
        if len(msgs) > self.max_messages:
            # Keep most recent max_messages
            sess["messages"] = msgs[-self.max_messages :]

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._store.pop(session_id, None)

    def stats(self) -> dict:
        with self._lock:
            return {"sessions": len(self._store), "total_messages": sum(len(v["messages"]) for v in self._store.values())}

    def new_session_id(self) -> str:
        return str(uuid.uuid4())


# Singleton — max_messages synced from env at app startup (see server/app.py lifespan)
conversation_manager = ConversationManager(max_messages=8)
