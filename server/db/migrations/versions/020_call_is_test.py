"""Flag browser practice sessions as tests so they stop counting as real calls.

A web-agent test session creates the same `calls` row as a live PSTN call, so it
inflated call counts, success rates and average duration in the console and was
archived like a real conversation. `is_test` marks the row; recording and the
real-call rollups both read it.

Defaults to false, so every row written before this migration keeps behaving as
a real call.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "020_call_is_test"
down_revision: str | None = "019_agent_telephony_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "calls",
        sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Partial index: the rollups always filter on is_test, and real calls are the
    # overwhelmingly common row, so a full index would be mostly dead weight.
    op.create_index(
        "ix_calls_is_test",
        "calls",
        ["is_test"],
        postgresql_where=sa.text("is_test = true"),
    )


def downgrade() -> None:
    op.drop_index("ix_calls_is_test", table_name="calls")
    op.drop_column("calls", "is_test")