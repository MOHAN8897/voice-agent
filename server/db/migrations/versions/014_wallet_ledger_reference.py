"""Wallet ledger reference id + INR debit amounts on transactions."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "014_wallet_ledger_reference"
down_revision: str | None = "013_email_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "billing_wallet_transactions",
        sa.Column("reference_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "billing_wallet_transactions",
        sa.Column("amount_inr_paise", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "uq_billing_wallet_tx_reference",
        "billing_wallet_transactions",
        ["reference_id"],
        unique=True,
        postgresql_where=sa.text("reference_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_billing_wallet_tx_reference", table_name="billing_wallet_transactions")
    op.drop_column("billing_wallet_transactions", "amount_inr_paise")
    op.drop_column("billing_wallet_transactions", "reference_id")
