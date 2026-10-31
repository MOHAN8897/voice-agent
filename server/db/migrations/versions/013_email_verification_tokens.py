"""Email verification tokens (single-use)."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "013_email_verification"
down_revision: str | None = "012_razorpay_invoices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_verification_tokens",
        sa.Column("token_hash", sa.String(128), primary_key=True),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("email_verification_tokens")
