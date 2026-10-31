"""Concurrent call channels and the per-call voice profile pin.

Revision ID: 049_concurrency_channels
Revises: 048_razorpay_reconcile_round_robin
Create Date: 2026-10-30

* `calls.voice_profile_revision` pins the tier stack revision admitted with each
  call, next to the existing `rate_version` price pin, so an admin edit made
  while the call is live is visibly not the one it used.
* `tenant_channel_subscriptions` holds paid concurrent channels per tenant for a
  30-day period; `tenant_channel_events` is their history (charges, renewals,
  grace, lapse, downgrades); `tenant_concurrency_daily` feeds the Usage page
  (peak in use, rejected and queued calls per day).

Channel prices are versioned in the existing `config_versions` table
(resource `concurrency_pricing` / `platform`), so no pricing table is needed.
Charges use the existing wallet ledger with idempotent reference ids.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "049_concurrency_channels"
down_revision: str | None = "048_razorpay_reconcile_round_robin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calls", sa.Column("voice_profile_revision", sa.Integer(), nullable=True))

    op.create_table(
        "tenant_channel_subscriptions",
        sa.Column("tenant_id", pg.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("paid_channels", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pending_paid_channels", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="none"),
        sa.Column("price_inr_paise_per_channel", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("price_usd_micros_per_channel", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("pricing_version", sa.Integer(), nullable=True),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("grace_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_renewal_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notice", sa.String(400), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_tenant_channel_subscriptions_current_period_end",
        "tenant_channel_subscriptions",
        ["current_period_end"],
    )

    op.create_table(
        "tenant_channel_events",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", pg.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("channels_before", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("channels_after", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("amount_inr_paise", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("amount_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reference_id", sa.String(128), nullable=True),
        sa.Column("pricing_version", sa.Integer(), nullable=True),
        sa.Column("actor", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tenant_channel_events_tenant_created", "tenant_channel_events", ["tenant_id", "created_at"])

    op.create_table(
        "tenant_concurrency_daily",
        sa.Column("tenant_id", pg.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("peak_active", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("channel_cap", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("admitted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("queued", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("tenant_concurrency_daily")
    op.drop_index("ix_tenant_channel_events_tenant_created", table_name="tenant_channel_events")
    op.drop_table("tenant_channel_events")
    op.drop_index("ix_tenant_channel_subscriptions_current_period_end", table_name="tenant_channel_subscriptions")
    op.drop_table("tenant_channel_subscriptions")
    op.drop_column("calls", "voice_profile_revision")
