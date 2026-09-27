"""Per-user attribution on wallet ledger."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "016_usage_credits_user"
down_revision: str | None = "015_email_verification_otp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "billing_wallet_transactions",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_billing_wallet_tx_user",
        "billing_wallet_transactions",
        ["tenant_id", "user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_billing_wallet_tx_user", table_name="billing_wallet_transactions")
    op.drop_column("billing_wallet_transactions", "user_id")
