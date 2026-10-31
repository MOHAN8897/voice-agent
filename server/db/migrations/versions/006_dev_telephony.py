"""Dev PSTN test history and contacts — Postgres mirror for dev telephony store."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006_dev_telephony"
down_revision: Union[str, None] = "005_tier_stack"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dev_pstn_history",
        sa.Column("history_id", sa.String(length=64), primary_key=True),
        sa.Column("agent_id", sa.String(length=64), nullable=True),
        sa.Column("external_id", sa.String(length=128), nullable=True),
        sa.Column("internal_call_id", sa.String(length=64), nullable=True),
        sa.Column("placed_at", sa.String(length=40), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_dev_pstn_history_agent_id", "dev_pstn_history", ["agent_id"])
    op.create_index("ix_dev_pstn_history_external_id", "dev_pstn_history", ["external_id"])
    op.create_index("ix_dev_pstn_history_internal_call_id", "dev_pstn_history", ["internal_call_id"])

    op.create_table(
        "dev_pstn_contacts",
        sa.Column("contact_id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_dev_pstn_contacts_phone", "dev_pstn_contacts", ["phone"])


def downgrade() -> None:
    op.drop_index("ix_dev_pstn_contacts_phone", table_name="dev_pstn_contacts")
    op.drop_table("dev_pstn_contacts")
    op.drop_index("ix_dev_pstn_history_internal_call_id", table_name="dev_pstn_history")
    op.drop_index("ix_dev_pstn_history_external_id", table_name="dev_pstn_history")
    op.drop_index("ix_dev_pstn_history_agent_id", table_name="dev_pstn_history")
    op.drop_table("dev_pstn_history")
