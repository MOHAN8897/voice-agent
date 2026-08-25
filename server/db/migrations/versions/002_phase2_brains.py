"""Phase 2 brain tables + agent workspace columns."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_phase2_brains"
down_revision: Union[str, None] = "001_phase1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("active_compiled_brain_version", sa.String(64), nullable=True))
    op.add_column("agents", sa.Column("default_tier", sa.String(20), server_default="medium", nullable=False))
    op.add_column("agents", sa.Column("languages", postgresql.ARRAY(sa.String()), server_default="{te-IN}", nullable=False))
    op.add_column("agents", sa.Column("memory_schema", sa.String(64), server_default="compact_v1", nullable=False))

    op.create_table(
        "platform_brain_versions",
        sa.Column("version_id", sa.String(64), primary_key=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "business_brain_sections",
        sa.Column("section_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agents.agent_id"), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "business_brain_versions",
        sa.Column("version_id", sa.String(64), primary_key=True),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agents.agent_id"), nullable=False),
        sa.Column("optimized_prompt", sa.Text(), nullable=False),
        sa.Column("optimizer_report", postgresql.JSONB(), nullable=False),
        sa.Column("source_checksum", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "compiled_brain_snapshots",
        sa.Column("compiled_version", sa.String(64), primary_key=True),
        sa.Column("platform_version", sa.String(64), nullable=False),
        sa.Column("business_version", sa.String(64), nullable=False),
        sa.Column("static_rules_version", sa.String(32), nullable=False),
        sa.Column("compiled_text", sa.Text(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("token_estimate", sa.Integer(), nullable=False),
        sa.Column("compiled_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("compiled_brain_snapshots")
    op.drop_table("business_brain_versions")
    op.drop_table("business_brain_sections")
    op.drop_table("platform_brain_versions")
    op.drop_column("agents", "memory_schema")
    op.drop_column("agents", "languages")
    op.drop_column("agents", "default_tier")
    op.drop_column("agents", "active_compiled_brain_version")
