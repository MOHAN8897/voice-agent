"""Phase 3 calls table + Phase 1 architecture entity alignment."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003_phase3_calls"
down_revision: Union[str, None] = "002_phase2_brains"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("plan", sa.String(50), server_default="dev", nullable=False))
    op.add_column(
        "agents",
        sa.Column("environment", sa.String(50), server_default="development", nullable=False),
    )

    op.create_table(
        "calls",
        sa.Column("call_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.tenant_id"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agents.agent_id"),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(100), nullable=True),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("environment", sa.String(50), nullable=False),
        sa.Column("tier", sa.String(20), nullable=False),
        sa.Column("combination_id", sa.String(64), nullable=False),
        sa.Column("compiled_brain_version", sa.String(64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
        sa.Column("disposition", sa.String(50), nullable=True),
        sa.Column("finalization_status", sa.String(20), nullable=False),
        sa.Column("storage_path", sa.String(512), nullable=False),
        sa.Column("end_reason", sa.String(50), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_calls_tenant_started", "calls", ["tenant_id", "started_at"])
    op.create_index("idx_calls_agent", "calls", ["agent_id", "started_at"])
    op.create_index("idx_calls_session_active", "calls", ["session_id"])


def downgrade() -> None:
    op.drop_index("idx_calls_session_active", table_name="calls")
    op.drop_index("idx_calls_agent", table_name="calls")
    op.drop_index("idx_calls_tenant_started", table_name="calls")
    op.drop_table("calls")
    op.drop_column("agents", "environment")
    op.drop_column("tenants", "plan")
