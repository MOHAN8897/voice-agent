"""Round-robin Razorpay order reconciliation.

Revision ID: 048_razorpay_reconcile_round_robin
Revises: 047_durable_followups
Create Date: 2026-10-30

`last_reconciled_at` records when the reconciliation worker last asked Razorpay
about an order. The worker picks orders by it (NULLS FIRST), so abandoned
checkouts no longer starve newer ones, and expired orders are re-checked for
late captures at most once per interval.

Disputes are recorded in the activity log and lost chargebacks in the existing
refund/credit-note tables, and payment settings use `config_versions`, so no
other schema change is needed.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = "048_razorpay_reconcile_round_robin"
down_revision: str | None = "047_durable_followups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "razorpay_orders",
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Both lanes filter by status and age, then order by last check.
    op.create_index(
        "ix_razorpay_orders_status_reconcile",
        "razorpay_orders",
        ["status", "last_reconciled_at", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_razorpay_orders_status_reconcile", table_name="razorpay_orders")
    op.drop_column("razorpay_orders", "last_reconciled_at")
