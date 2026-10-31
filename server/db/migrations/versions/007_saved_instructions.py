"""Persist compiled agent briefs/scripts/brains across server reloads."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007_saved_instructions"
down_revision: Union[str, None] = "006_dev_telephony"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "saved_instructions",
        sa.Column("session_id", sa.String(length=120), primary_key=True),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_saved_instructions_agent_id", "saved_instructions", ["agent_id"])


def downgrade() -> None:
    op.drop_index("ix_saved_instructions_agent_id", table_name="saved_instructions")
    op.drop_table("saved_instructions")
