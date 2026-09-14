"""In-memory active-call registry — locked L1/L2 for the live path."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from server.providers.base import ResolvedStack


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class CallContext:
    call_id: str
    tenant_id: str
    agent_id: str
    session_id: str
    channel: str
    direction: str
    environment: str
    tier: str
    resolved_stack: ResolvedStack
    compiled_brain_version: str | None
    compiled_brain_text: str | None
    started_at: datetime
    storage_path: str
    status: str = "active"  # active | finalizing | complete | failed
    last_heartbeat: datetime = field(default_factory=_utcnow)
    ws_clients: int = 0
    end_reason: str | None = None
    agent_hangup_armed: bool = False
    barge_in_flight: bool = False
    slow_down_nudged: bool = False
    last_stt_partial_at: float = 0.0
    call_end_policy: dict[str, Any] | None = None
    callback_request_text: str = ""
    callback_close_phase: str = "idle"
    callback_name: str = ""
    callback_phone: str = ""
    callback_when: str = ""
    pipeline: str = "realtime_text"
    components: dict[str, str] = field(
        default_factory=lambda: {"ledger": "pending", "audio": "pending", "outcome": "pending"}
    )
    turns: list[dict[str, Any]] = field(default_factory=list)

    def heartbeat(self) -> None:
        self.last_heartbeat = _utcnow()

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "channel": self.channel,
            "direction": self.direction,
            "environment": self.environment,
            "tier": self.tier,
            "combination_id": self.resolved_stack.combination_id,
            "compiled_brain_version": self.compiled_brain_version,
            "started_at": self.started_at.isoformat(),
            "status": self.status,
            "storage_path": self.storage_path,
            "resolved_stack": self.resolved_stack.to_safe_dict(),
            "pipeline": self.pipeline,
        }


_CALLS: dict[str, CallContext] = {}
_BY_SESSION: dict[str, str] = {}


def put(ctx: CallContext) -> None:
    _CALLS[ctx.call_id] = ctx
    if ctx.session_id:
        _BY_SESSION[ctx.session_id] = ctx.call_id


def get(call_id: str) -> CallContext | None:
    return _CALLS.get(call_id)


def get_active_for_session(session_id: str) -> CallContext | None:
    cid = _BY_SESSION.get(session_id)
    if not cid:
        return None
    ctx = _CALLS.get(cid)
    if ctx and ctx.status == "active":
        return ctx
    return None


def count_active_for_agent(agent_id: str) -> int:
    return sum(1 for c in _CALLS.values() if c.agent_id == agent_id and c.status == "active")


def list_active() -> list[CallContext]:
    return [c for c in _CALLS.values() if c.status == "active"]


def drop_session_pointer(session_id: str, call_id: str) -> None:
    if _BY_SESSION.get(session_id) == call_id:
        _BY_SESSION.pop(session_id, None)


def clear_all() -> None:
    """Test helper."""
    _CALLS.clear()
    _BY_SESSION.clear()
