"""Tenant controls and clips for the technical-failure announcement.

Revision ID: 045_technical_fallback
Revises: 044_call_status_tags
Create Date: 2026-10-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "045_technical_fallback"
down_revision: str | None = "044_call_status_tags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "technical_fallback_promise_callback",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "agents",
        sa.Column(
            "technical_fallback_text",
            sa.String(length=255),
            nullable=False,
            server_default="",
        ),
    )
    op.create_table(
        "agent_fallback_clips",
        sa.Column("clip_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("variant", sa.String(length=24), nullable=False),
        sa.Column("pcm_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("sample_rate", sa.Integer(), nullable=False, server_default="8000"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.agent_id"]),
        sa.UniqueConstraint("agent_id", "language", "variant", name="uq_agent_fallback_clip"),
    )
    op.create_index("ix_agent_fallback_clips_tenant_id", "agent_fallback_clips", ["tenant_id"])
    op.create_index("ix_agent_fallback_clips_agent_id", "agent_fallback_clips", ["agent_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_fallback_clips_agent_id", table_name="agent_fallback_clips")
    op.drop_index("ix_agent_fallback_clips_tenant_id", table_name="agent_fallback_clips")
    op.drop_table("agent_fallback_clips")
    op.drop_column("agents", "technical_fallback_text")
    op.drop_column("agents", "technical_fallback_promise_callback")
