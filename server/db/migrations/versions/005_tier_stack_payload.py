"""Add stack_payload to tier_assignments for DB-driven L1 resolution."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005_tier_stack"
down_revision: Union[str, None] = "004_phase5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tier_assignments",
        sa.Column("stack_payload", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tier_assignments", "stack_payload")
