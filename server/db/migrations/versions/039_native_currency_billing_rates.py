"""Preserve native INR and precise USD prices for billing.

Revision ID: 039_native_billing_rates
Revises: 038_tenants_status_ck_expand
Create Date: 2026-10-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = "039_native_billing_rates"
down_revision: str | None = "038_tenants_status_ck_expand"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Historical rate rows stay nullable; application reads derive their legacy
    # values from USD cents and the version's FX rate without changing history.
    for name in (
        "pstn_rate_usd_micros_per_min",
        "web_agent_rate_usd_micros_per_min",
        "did_monthly_usd_micros",
        "pstn_rate_inr_paise_per_min",
        "web_agent_rate_inr_paise_per_min",
        "did_monthly_inr_paise",
    ):
        op.add_column("billing_rate_versions", sa.Column(name, sa.BigInteger(), nullable=True))

    # Existing call snapshots remain unchanged and continue using their cents
    # and FX values. New calls snapshot both native price representations.
    op.add_column("calls", sa.Column("applied_rate_usd_micros_per_min", sa.BigInteger(), nullable=True))
    op.add_column("calls", sa.Column("applied_rate_inr_paise_per_min", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("calls", "applied_rate_inr_paise_per_min")
    op.drop_column("calls", "applied_rate_usd_micros_per_min")
    for name in (
        "did_monthly_inr_paise",
        "web_agent_rate_inr_paise_per_min",
        "pstn_rate_inr_paise_per_min",
        "did_monthly_usd_micros",
        "web_agent_rate_usd_micros_per_min",
        "pstn_rate_usd_micros_per_min",
    ):
        op.drop_column("billing_rate_versions", name)
