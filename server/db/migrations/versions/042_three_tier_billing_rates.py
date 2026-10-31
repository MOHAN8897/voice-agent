"""Three-tier per-minute billing rates for PSTN voice stacks.

Revision ID: 042_three_tier_billing_rates
Revises: 041_campaign_execution_safety
Create Date: 2026-10-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = "042_three_tier_billing_rates"
down_revision: str | None = "041_campaign_execution_safety"
branch_labels = None
depends_on = None


_COLUMNS = (
    "pstn_low_rate_usd_micros_per_min",
    "pstn_low_rate_inr_paise_per_min",
    "pstn_medium_rate_usd_micros_per_min",
    "pstn_medium_rate_inr_paise_per_min",
    "pstn_premium_rate_usd_micros_per_min",
    "pstn_premium_rate_inr_paise_per_min",
)


def upgrade() -> None:
    # Add nullable per-tier rate columns; legacy rates remain intact in pstn_rate_*
    for name in _COLUMNS:
        op.add_column("billing_rate_versions", sa.Column(name, sa.BigInteger(), nullable=True))


def downgrade() -> None:
    for name in reversed(_COLUMNS):
        op.drop_column("billing_rate_versions", name)
