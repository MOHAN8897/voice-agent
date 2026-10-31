"""Concurrent call channels: tenant subscriptions, ledger events and daily usage.

A "channel" is one simultaneous PSTN call. Every tenant gets the platform's
included channels for free; paid channels are a 30-day recurring subscription
(Vobiz renews its own concurrency capacity every 30 days), charged from the
prepaid wallet. Pricing itself is versioned in `config_versions`
(resource `concurrency_pricing` / `platform`).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from server.db.models.entities import Base, _utcnow


class TenantChannelSubscription(Base):
    """Paid concurrent channels a tenant holds for the current 30-day period."""

    __tablename__ = "tenant_channel_subscriptions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), primary_key=True
    )
    #: Paid channels in force now (on top of the included channels).
    paid_channels: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: Downgrade requested by the tenant; applied at the next renewal.
    pending_paid_channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: none | active | grace | lapsed
    status: Mapped[str] = mapped_column(String(16), default="none", nullable=False)
    #: Price per channel locked for the current period (paise / USD micros).
    price_inr_paise_per_channel: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    price_usd_micros_per_channel: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    #: config_versions.version of the concurrency price used for this period.
    pricing_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    grace_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_renewal_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Plain-language notice shown in the console (grace, lapse, downgrade).
    notice: Mapped[str | None] = mapped_column(String(400), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class TenantChannelEvent(Base):
    """Append-only history of channel changes, charges and capacity rejections."""

    __tablename__ = "tenant_channel_events"
    __table_args__ = (Index("ix_tenant_channel_events_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False
    )
    #: purchase | renewal | renewal_failed | downgrade_scheduled | downgrade_cancelled |
    #: downgrade_applied | lapsed | admin_grant
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    channels_before: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    channels_after: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    amount_inr_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: billing_wallet_transactions.reference_id of the charge, when there is one.
    reference_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pricing_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class TenantConcurrencyDaily(Base):
    """Per-day concurrency analytics: peak in use, admitted, rejected and queued."""

    __tablename__ = "tenant_concurrency_daily"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    peak_active: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    channel_cap: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    admitted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: Inbound / manual calls refused because every channel was busy.
    rejected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: Campaign dials deferred (re-queued) because every channel was busy.
    queued: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
