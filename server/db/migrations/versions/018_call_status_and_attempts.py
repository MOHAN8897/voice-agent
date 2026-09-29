"""Canonical call status, inbound call attempts, and callback ledger.

Additive only: every new column/table is nullable or defaulted, and no existing row
is rewritten. Rows written before this migration keep working because
``server/call/call_status.py`` derives the status on read when the column is NULL.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "018_call_status_and_attempts"
down_revision: str | None = "017_number_purchase_assign_agent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calls", sa.Column("status", sa.String(20), nullable=True))
    op.create_index("ix_calls_status", "calls", ["status"])

    op.create_table(
        "call_attempts",
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agents.agent_id"), nullable=True),
        sa.Column("provider", sa.String(30), nullable=False, server_default="telnyx"),
        sa.Column("provider_call_control_id", sa.String(255), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False, server_default="inbound"),
        sa.Column("from_number", sa.String(32), nullable=True),
        sa.Column("to_number", sa.String(32), nullable=True),
        sa.Column("linked_call_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("calls.call_id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="in_progress"),
        sa.Column("policy_reason", sa.String(50), nullable=True),
        sa.Column("end_reason", sa.String(50), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("provider_call_control_id", name="uq_call_attempt_control"),
    )
    op.create_index("ix_call_attempts_tenant_id", "call_attempts", ["tenant_id"])
    op.create_index("ix_call_attempts_status", "call_attempts", ["status"])
    op.create_index("ix_call_attempts_started_at", "call_attempts", ["started_at"])

    op.create_table(
        "call_callbacks",
        sa.Column("callback_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("original_call_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("calls.call_id"), nullable=True),
        sa.Column("original_attempt_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("call_attempts.attempt_id"), nullable=True),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("to_e164", sa.String(32), nullable=False),
        sa.Column("from_e164", sa.String(32), nullable=True),
        sa.Column("dial_request_id", sa.String(64), nullable=False),
        sa.Column("mode", sa.String(30), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("provider", sa.String(30), nullable=True),
        sa.Column("provider_call_control_id", sa.String(255), nullable=True),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("dial_request_id", name="uq_call_callback_dial_request"),
    )
    op.create_index("ix_call_callbacks_tenant_id", "call_callbacks", ["tenant_id"])
    op.create_index("ix_call_callbacks_status", "call_callbacks", ["status"])


def downgrade() -> None:
    op.drop_index("ix_call_callbacks_status", table_name="call_callbacks")
    op.drop_index("ix_call_callbacks_tenant_id", table_name="call_callbacks")
    op.drop_table("call_callbacks")
    op.drop_index("ix_call_attempts_started_at", table_name="call_attempts")
    op.drop_index("ix_call_attempts_status", table_name="call_attempts")
    op.drop_index("ix_call_attempts_tenant_id", table_name="call_attempts")
    op.drop_table("call_attempts")
    op.drop_index("ix_calls_status", table_name="calls")
    op.drop_column("calls", "status")
