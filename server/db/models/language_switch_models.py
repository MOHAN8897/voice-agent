"""Callers who asked for another language, and each contact's remembered language."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from server.db.models.entities import Base, _utcnow


class LanguageSwitchRequest(Base):
    """A callback item of kind ``language_switch``: call this contact back in ``requested_language``.

    Kept apart from ``call_callbacks`` so installations without migration 050 keep
    their existing callback workflow intact; the dial itself still goes through the
    normal callback path (``call_callbacks`` audit row + subscriber outbound).
    """

    __tablename__ = "language_switch_requests"
    __table_args__ = (
        UniqueConstraint("tenant_id", "original_call_id", name="uq_language_switch_origin"),
        Index("ix_language_switch_status", "tenant_id", "status", "requested_language"),
        Index("ix_language_switch_phone", "tenant_id", "phone_e164"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), default="language_switch", nullable=False)
    original_call_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("calls.call_id", ondelete="SET NULL"), nullable=True)
    phone_e164: Mapped[str] = mapped_column(String(32), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    requested_language: Mapped[str] = mapped_column(String(16), nullable=False)
    original_language: Mapped[str] = mapped_column(String(16), nullable=False)
    request_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: pending | calling | done | dismissed
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    last_dial_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    callback_call_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ContactLanguagePreference(Base):
    """The language a contact asked for, reused for later calls by agents that speak it."""

    __tablename__ = "contact_language_preferences"
    __table_args__ = (UniqueConstraint("tenant_id", "phone_e164", name="uq_contact_language_phone"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False)
    phone_e164: Mapped[str] = mapped_column(String(32), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    #: caller_request | callback_completed
    source: Mapped[str] = mapped_column(String(24), default="caller_request", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
