"""Operational telephony configuration per agent (greeting, hours, after-hours, toggles).

Kept out of the Business Brain on purpose. Rows are created lazily, so agents that
predate this migration keep running with no profile and today's exact behaviour.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "019_agent_telephony_profiles"
down_revision: str | None = "018_call_status_and_attempts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_telephony_profiles",
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agents.agent_id"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("greeting_phrase", sa.String(500), nullable=True),
        sa.Column("business_hours", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Kolkata"),
        sa.Column("after_hours_action", sa.String(30), nullable=False, server_default="voicemail"),
        sa.Column("transfer_number", sa.String(32), nullable=True),
        sa.Column("inbound_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("outbound_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("agent_id", name="uq_agent_telephony_profile_agent"),
    )
    op.create_index("ix_agent_telephony_profiles_tenant_id", "agent_telephony_profiles", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_telephony_profiles_tenant_id", table_name="agent_telephony_profiles")
    op.drop_table("agent_telephony_profiles")
