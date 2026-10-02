"""Phase 5 entities — campaigns, phone numbers, DNC, audit."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from server.db.models.entities import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuditLog(Base):
    """One row per notable action, from admins, subscribers and background jobs.

    The activity log is the answer to "what just happened, and did any of it
    fail", so a row carries its origin (`source`), its result (`outcome`), how bad
    it is (`severity`), and enough request context to trace one user action
    across the request that produced it.
    """

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    #: Who produced this row — `admin`, `subscriber`, `webhook` or `system`.
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="admin")
    #: `ok` or `error`. A refused purchase and a completed one are both here.
    outcome: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")
    #: `info`, `warning` or `error`. Lets the log open on what needs attention.
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="info")
    #: Correlates every row written while handling one HTTP request.
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(400), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class PhoneNumber(Base):
    __tablename__ = "phone_numbers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    e164: Mapped[str] = mapped_column(String(20), nullable=False)
    plivo_number_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    #: Set NULL on agent deletion: a number must return to the pool rather than
    #: keep pointing at an agent row that no longer exists.
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.agent_id", ondelete="SET NULL"), nullable=True
    )
    purchase_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    telnyx_number_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    billing_source: Mapped[str] = mapped_column(String(30), default="manual")
    inbound_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    outbound_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AgentTelephonyProfile(Base):
    """Operational phone configuration for one agent.

    Deliberately separate from the Business Brain: this is how the *telephone*
    behaves (does it ring, when, what does the caller hear, what happens at night),
    not how the *agent* thinks. A row is created lazily on first read so every
    existing agent keeps working with no profile and no migration backfill.
    """

    __tablename__ = "agent_telephony_profiles"
    __table_args__ = (UniqueConstraint("agent_id", name="uq_agent_telephony_profile_agent"),)

    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.agent_id"), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    #: Spoken by the agent as the opening line on inbound calls. Empty = derive
    #: from the compiled brain exactly as today.
    greeting_phrase: Mapped[str | None] = mapped_column(String(500), nullable=True)
    #: {"mon": [{"open": "09:00", "close": "18:00"}], ...}. Empty = always open.
    business_hours: Mapped[dict] = mapped_column(JSONB, default=dict)
    #: IANA zone the business hours are expressed in.
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    #: voicemail | hangup | transfer | always — what to do outside business hours.
    after_hours_action: Mapped[str] = mapped_column(String(30), default="voicemail")
    #: Required when after_hours_action == "transfer".
    transfer_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: When false the live inbound path does not answer this agent at all.
    inbound_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    #: When false outbound calls for this agent are refused before dialling.
    outbound_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class DncEntry(Base):
    __tablename__ = "dnc_list"
    __table_args__ = (UniqueConstraint("tenant_id", "phone_e164", name="uq_dnc_tenant_phone"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    phone_e164: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Campaign(Base):
    __tablename__ = "campaigns"

    campaign_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.agent_id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    schedule: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    retry_rules: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    concurrency: Mapped[int] = mapped_column(Integer, default=5)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CampaignContact(Base):
    __tablename__ = "campaign_contacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("campaigns.campaign_id"), nullable=False)
    phone_e164: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CampaignRun(Base):
    __tablename__ = "campaign_runs"

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("campaigns.campaign_id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="scheduled")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stats: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class DialAttempt(Base):
    __tablename__ = "dial_attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("campaigns.campaign_id"), nullable=False)
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("campaign_contacts.id"), nullable=False)
    call_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="queued")
    plivo_call_uuid: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
