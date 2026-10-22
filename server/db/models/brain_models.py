"""
Brain ORM models — Phase 2.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from server.db.models.entities import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PlatformBrainVersion(Base):
    __tablename__ = "platform_brain_versions"

    version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | active | archived
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class BusinessBrainSection(Base):
    __tablename__ = "business_brain_sections"

    section_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.agent_id"), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    order: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class BusinessBrainVersion(Base):
    __tablename__ = "business_brain_versions"

    version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.agent_id"), nullable=False)
    optimized_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    optimizer_report: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    source_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | published
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SavedInstruction(Base):
    """Per-session compiled brief/script/brain — survives server reloads."""

    __tablename__ = "saved_instructions"

    session_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class SavedRuntime(Base):
    """Per-session Fine-tune runtime overrides — survives server reloads."""

    __tablename__ = "saved_runtime"

    session_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class CompiledBrainSnapshot(Base):
    __tablename__ = "compiled_brain_snapshots"

    compiled_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    platform_version: Mapped[str] = mapped_column(String(64), nullable=False)
    business_version: Mapped[str] = mapped_column(String(64), nullable=False)
    static_rules_version: Mapped[str] = mapped_column(String(32), nullable=False)
    compiled_text: Mapped[str] = mapped_column(Text, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    token_estimate: Mapped[int] = mapped_column(Integer, default=0)
    compiled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
