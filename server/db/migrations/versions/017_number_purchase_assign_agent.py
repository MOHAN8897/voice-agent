"""Persist intended agent binding on DID purchase (reserve → pay → provision → assign)."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "017_number_purchase_assign_agent"
down_revision: str | None = "016_usage_credits_user"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "number_purchases",
        sa.Column("assign_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("number_purchases", "assign_agent_id")
