"""
Core entities — tenants, agents, tier_assignments, config_versions, calls.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Tenant(Base):
    __tablename__ = "tenants"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    plan: Mapped[str] = mapped_column(String(50), default="dev")
    status: Mapped[str] = mapped_column(String(30), default="active")
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    limits: Mapped[dict] = mapped_column(JSONB, default=dict)
    default_agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.agent_id"), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    billing_source: Mapped[str] = mapped_column(String(30), default="self_serve")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    default_agent: Mapped["Agent | None"] = relationship(
        foreign_keys=[default_agent_id],
        post_update=True,
    )
    agents: Mapped[list["Agent"]] = relationship(
        back_populates="tenant",
        foreign_keys="Agent.tenant_id",
    )
    calls: Mapped[list["Call"]] = relationship(back_populates="tenant")


class Agent(Base):
    __tablename__ = "agents"

    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="active")
    active_compiled_brain_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    default_tier: Mapped[str] = mapped_column(String(20), default="medium")
    languages: Mapped[list[str]] = mapped_column(ARRAY(String), default=["te-IN"])
    memory_schema: Mapped[str] = mapped_column(String(64), default="compact_v1")
    environment: Mapped[str] = mapped_column(String(50), default="development")
    voice_settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    recording_disclosure_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    recording_disclosure_text: Mapped[str] = mapped_column(
        String(255), default="This call may be recorded for quality and training purposes."
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    tenant: Mapped["Tenant"] = relationship(
        back_populates="agents",
        foreign_keys=[tenant_id],
    )
    calls: Mapped[list["Call"]] = relationship(back_populates="agent")


class TierAssignment(Base):
    __tablename__ = "tier_assignments"
    __table_args__ = (UniqueConstraint("environment", "tier", name="uq_tier_env"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    environment: Mapped[str] = mapped_column(String(50), nullable=False)
    tier: Mapped[str] = mapped_column(String(20), nullable=False)
    combination_id: Mapped[str] = mapped_column(String(64), nullable=False)
    stack_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class ConfigVersion(Base):
    __tablename__ = "config_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Call(Base):
    __tablename__ = "calls"

    call_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.agent_id"), nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    channel: Mapped[str] = mapped_column(String(20), default="browser")
    direction: Mapped[str] = mapped_column(String(20), default="inbound")
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    environment: Mapped[str] = mapped_column(String(50), default="development")
    tier: Mapped[str] = mapped_column(String(20), default="medium")
    combination_id: Mapped[str] = mapped_column(String(64), nullable=False)
    compiled_brain_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    disposition: Mapped[str | None] = mapped_column(String(50), nullable=True)
    finalization_status: Mapped[str] = mapped_column(String(20), default="pending")
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    end_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    #: Canonical status (server/call/call_status.py). Materialised so it can be
    #: filtered in SQL; NULL on rows written before the column existed, and
    #: derived on read for those.
    status: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    #: Browser practice sessions (channel="browser"). Not a real conversation:
    #: excluded from call rollups and never recorded. Live PSTN calls are false.
    is_test: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    tenant: Mapped["Tenant"] = relationship(back_populates="calls")
    agent: Mapped["Agent"] = relationship(back_populates="calls")


class CallAttempt(Base):
    """One ringing event, persisted even when the call never connects.

    A ``calls`` row only exists once media streams, so a caller who rings out and
    hangs up used to leave no trace at all. This table is the "attempt" half of the
    model: ``linked_call_id`` points at the ``calls`` row when the attempt became a
    real conversation, and is NULL while the attempt is missed/declined/voicemail.
    Written only from the carrier webhook, never on the answered path.
    """

    __tablename__ = "call_attempts"
    __table_args__ = (
        UniqueConstraint("provider_call_control_id", name="uq_call_attempt_control"),
    )

    attempt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.agent_id"), nullable=True)
    provider: Mapped[str] = mapped_column(String(30), default="telnyx")
    provider_call_control_id: Mapped[str] = mapped_column(String(255), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), default="inbound")
    from_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    linked_call_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("calls.call_id"), nullable=True)
    #: Canonical status (server/call/call_status.py).
    status: Mapped[str] = mapped_column(String(20), default="in_progress", index=True)
    #: Why the ingress decided what it decided: answered, inbound_disabled,
    #: after_hours_voicemail, after_hours_hangup, carrier_hangup, …
    policy_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    end_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CallCallback(Base):
    """A user- or system-initiated attempt to call a missed caller back.

    Owns idempotency (unique ``dial_request_id``) and the audit trail, and is the
    extension point for AI redial and scheduled callbacks.
    """

    __tablename__ = "call_callbacks"
    __table_args__ = (
        UniqueConstraint("dial_request_id", name="uq_call_callback_dial_request"),
    )

    callback_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    original_call_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("calls.call_id"), nullable=True)
    original_attempt_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("call_attempts.attempt_id"), nullable=True)
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    to_e164: Mapped[str] = mapped_column(String(32), nullable=False)
    from_e164: Mapped[str | None] = mapped_column(String(32), nullable=True)
    dial_request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    #: manual | ai_redial | scheduled — the reason the dial happened.
    mode: Mapped[str] = mapped_column(String(30), default="manual")
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    provider: Mapped[str | None] = mapped_column(String(30), nullable=True)
    provider_call_control_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
