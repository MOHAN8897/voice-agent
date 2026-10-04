"""Durable Job schema and helpers for asynchronous queue and worker processing."""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class DurableJob:
    """Standard contract for jobs processed by background workers (ARQ/Redis/in-memory)."""

    call_id: str
    tenant_id: str
    job_type: str  # "post_call_summary" | "recording_upload" | "composio_action"
    payload: dict[str, Any] = field(default_factory=dict)
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: JobStatus = JobStatus.PENDING
    attempt_count: int = 0
    max_attempts: int = 3
    created_at: str = field(default_factory=_utcnow_iso)
    next_retry_at: str = field(default_factory=_utcnow_iso)
    idempotency_key: str = ""
    error_message: str | None = None

    def __post_init__(self) -> None:
        if not self.idempotency_key:
            action = self.payload.get("action_name", "")
            suffix = f":{action}" if action else ""
            self.idempotency_key = f"{self.job_type}:{self.call_id}{suffix}"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DurableJob:
        copied = dict(data)
        if "status" in copied and isinstance(copied["status"], str):
            copied["status"] = JobStatus(copied["status"])
        return cls(**copied)

    def mark_failed(self, error: str, backoff_base_sec: float = 30.0) -> None:
        """Increment attempt count and compute next retry timestamp with exponential backoff."""
        self.attempt_count += 1
        self.error_message = error[:500]
        if self.attempt_count >= self.max_attempts:
            self.status = JobStatus.DEAD_LETTER
        else:
            self.status = JobStatus.FAILED
            delay_sec = backoff_base_sec * (2 ** (self.attempt_count - 1))
            now = datetime.now(timezone.utc).timestamp()
            retry_dt = datetime.fromtimestamp(now + delay_sec, tz=timezone.utc)
            self.next_retry_at = retry_dt.isoformat().replace("+00:00", "Z")

    def mark_completed(self) -> None:
        self.status = JobStatus.COMPLETED
        self.error_message = None
