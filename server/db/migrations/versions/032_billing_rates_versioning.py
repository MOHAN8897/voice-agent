"""Add billing_rate_versions table and snapshot columns to calls.

Revision ID: 032_billing_rates_versioning
Revises: 031_wallet_tx_reference_unique
Create Date: 2026-10-11
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "032_billing_rates_versioning"
down_revision: str | None = "031_wallet_tx_reference_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create billing_rate_versions table
    op.create_table(
        "billing_rate_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("pstn_rate_usd_cents_per_min", sa.Integer(), nullable=False),
        sa.Column("web_agent_rate_usd_cents_per_min", sa.Integer(), nullable=False),
        sa.Column("did_monthly_usd_cents", sa.Integer(), nullable=False),
        sa.Column("fx_rate_inr", sa.Numeric(10, 4), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_billing_rate_versions_version", "billing_rate_versions", ["version"], unique=True)
    op.create_index("ix_billing_rate_versions_effective_from", "billing_rate_versions", ["effective_from"])
    op.create_index("ix_billing_rate_versions_is_active", "billing_rate_versions", ["is_active"])

    # 2. Add rate snapshot columns to calls
    op.add_column("calls", sa.Column("applied_rate_usd_cents_per_min", sa.Integer(), nullable=True))
    op.add_column("calls", sa.Column("applied_fx_rate_inr", sa.Numeric(10, 4), nullable=True))
    op.add_column("calls", sa.Column("rate_version", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("calls", "rate_version")
    op.drop_column("calls", "applied_fx_rate_inr")
    op.drop_column("calls", "applied_rate_usd_cents_per_min")

    op.drop_index("ix_billing_rate_versions_is_active", table_name="billing_rate_versions")
    op.drop_index("ix_billing_rate_versions_effective_from", table_name="billing_rate_versions")
    op.drop_index("ix_billing_rate_versions_version", table_name="billing_rate_versions")
    op.drop_table("billing_rate_versions")
