"""Stored platform-admin accounts for the admin portal (Roles & access)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from server.db.models.entities import Base, _utcnow


class PlatformAdminAccount(Base):
    """One person who can sign in to the admin portal.

    The env-configured DEV_PORTAL_USERNAME login is not stored here: it is the
    built-in break-glass super admin and is managed only by configuration.

    Secrets are never stored in the clear: `password_hash` is PBKDF2 and
    `invite_token_hash` is the SHA-256 of a one-time link token. `session_epoch`
    is embedded in every session cookie this account holds; bumping it ends all of
    them (sign out everywhere, suspension, password reset, removal).
    """

    __tablename__ = "platform_admin_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    #: `invited` | `active` | `suspended` | `removed`
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="invited")
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    session_epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    invite_token_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    #: `invite` (first password) or `reset` (admin-issued password reset)
    invite_purpose: Mapped[str | None] = mapped_column(String(20), nullable=True)
    invite_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invite_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sign_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sign_in_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
