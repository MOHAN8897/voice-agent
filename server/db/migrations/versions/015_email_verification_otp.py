"""Email verification OTP hash column."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "015_email_verification_otp"
down_revision: str | None = "014_wallet_ledger_reference"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "email_verification_tokens",
        sa.Column("otp_hash", sa.String(128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("email_verification_tokens", "otp_hash")
