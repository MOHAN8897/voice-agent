"""Durable, tenant-authorized follow-ups and explainable outcome assessments."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from server.db.models.entities import Base, _utcnow


class AgentFollowUpPolicy(Base):
    __tablename__ = "agent_followup_policies"
    __table_args__ = (UniqueConstraint("tenant_id", "agent_id", name="uq_followup_policy_agent"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.agent_id", ondelete="CASCADE"))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    authorized_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    billing_tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id", ondelete="SET NULL"), nullable=True)
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class FollowUpJob(Base):
    __tablename__ = "followup_jobs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "origin_key", name="uq_followup_origin"),
        Index("ix_followup_due", "status", "due_at"),
        Index("ix_followup_phone", "tenant_id", "phone"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.agent_id", ondelete="CASCADE"))
    origin_key: Mapped[str] = mapped_column(String(120))
    source_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(24))
    phone: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), default="needs_review")
    reason: Mapped[str] = mapped_column(String(120), default="approval_required")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    control_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    authorized_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    billing_tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class LeadAssessment(Base):
    __tablename__ = "lead_assessments"
    __table_args__ = (UniqueConstraint("tenant_id", "lead_id", name="uq_lead_assessment"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), index=True)
    lead_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("leads.lead_id", ondelete="CASCADE"))
    source_call_id: Mapped[str] = mapped_column(String(36))
    assessment: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
