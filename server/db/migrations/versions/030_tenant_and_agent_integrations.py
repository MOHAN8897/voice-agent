"""Add tenant_integrations, agent_integrations, tool_executions, and oauth_states.

Revision ID: 030_tenant_and_agent_integrations
Revises: 029_compliance_and_onboarding
Create Date: 2026-10-04
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision: str = "030_composio_integrations"
down_revision: str | None = "029_compliance_and_onboarding"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def _has_index(table: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return index_name in {idx["name"] for idx in inspector.get_indexes(table)}


def upgrade() -> None:
    # 1. tenant_integrations
    if not _has_table("tenant_integrations"):
        op.create_table(
            "tenant_integrations",
            sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False),
            sa.Column("app_name", sa.String(64), nullable=False),
            sa.Column("composio_connection_id", sa.String(128), nullable=False),
            sa.Column("account_identifier", sa.String(255), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
            sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "app_name", name="uq_tenant_integrations_tenant_app"),
        )
    if not _has_index("tenant_integrations", "idx_tenant_integrations_tenant"):
        op.create_index("idx_tenant_integrations_tenant", "tenant_integrations", ["tenant_id"])

    # 2. agent_integrations
    if not _has_table("agent_integrations"):
        op.create_table(
            "agent_integrations",
            sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("agents.agent_id", ondelete="CASCADE"), nullable=False),
            sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False),
            sa.Column("app_name", sa.String(64), nullable=False),
            sa.Column("action_whitelist", ARRAY(sa.String), nullable=False, server_default=sa.text("'{}'::text[]")),
            sa.Column("timing_mode", sa.String(16), nullable=False, server_default="in_call"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("agent_id", "app_name", name="uq_agent_integrations_agent_app"),
        )
    if not _has_index("agent_integrations", "idx_agent_integrations_agent"):
        op.create_index("idx_agent_integrations_agent", "agent_integrations", ["agent_id"])
    if not _has_index("agent_integrations", "idx_agent_integrations_timing"):
        op.create_index("idx_agent_integrations_timing", "agent_integrations", ["timing_mode", "enabled"])

    # 3. tool_executions
    if not _has_table("tool_executions"):
        op.create_table(
            "tool_executions",
            sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False),
            sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("agents.agent_id", ondelete="CASCADE"), nullable=False),
            sa.Column("call_id", sa.String(64), nullable=False),
            sa.Column("action", sa.String(128), nullable=False),
            sa.Column("action_type", sa.String(16), nullable=False, server_default="read"),
            sa.Column("idempotency_key", sa.String(255), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="initiated"),
            sa.Column("parameters", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("result", JSONB, nullable=True),
            sa.Column("external_reference", sa.String(255), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_tool_executions_tenant_idempotency"),
        )
    if not _has_index("tool_executions", "idx_tool_executions_call"):
        op.create_index("idx_tool_executions_call", "tool_executions", ["call_id"])
    if not _has_index("tool_executions", "idx_tool_executions_status"):
        op.create_index("idx_tool_executions_status", "tool_executions", ["status"])

    # 4. oauth_states
    if not _has_table("oauth_states"):
        op.create_table(
            "oauth_states",
            sa.Column("state", sa.String(128), primary_key=True),
            sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", UUID(as_uuid=True), nullable=False),
            sa.Column("app_name", sa.String(64), nullable=False),
            sa.Column("redirect_uri", sa.Text(), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    if not _has_index("oauth_states", "idx_oauth_states_expiry"):
        op.create_index("idx_oauth_states_expiry", "oauth_states", ["expires_at"])


def downgrade() -> None:
    if _has_table("oauth_states"):
        op.drop_table("oauth_states")
    if _has_table("tool_executions"):
        op.drop_table("tool_executions")
    if _has_table("agent_integrations"):
        op.drop_table("agent_integrations")
    if _has_table("tenant_integrations"):
        op.drop_table("tenant_integrations")
