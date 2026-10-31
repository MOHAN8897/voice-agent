"""Opt-in follow-up policies, durable jobs, and explainable lead assessments.

Revision ID: 047_durable_followups
Revises: 046_remember_me_sessions
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "047_durable_followups"
down_revision = "046_remember_me_sessions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("agent_followup_policies",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", pg.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", pg.UUID(as_uuid=True), sa.ForeignKey("agents.agent_id", ondelete="CASCADE"), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False), sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("authorized_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="SET NULL")),
        sa.Column("billing_tenant_id", pg.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="SET NULL")),
        sa.Column("authorized_at", sa.DateTime(timezone=True)), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "agent_id", name="uq_followup_policy_agent"))
    op.create_index("ix_agent_followup_policies_tenant_id", "agent_followup_policies", ["tenant_id"])
    op.create_table("followup_jobs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", pg.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", pg.UUID(as_uuid=True), sa.ForeignKey("agents.agent_id", ondelete="CASCADE"), nullable=False),
        sa.Column("origin_key", sa.String(120), nullable=False), sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False), sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False), sa.Column("reason", sa.String(120), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False), sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.String(36)), sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("control_id", sa.String(255)),
        sa.Column("authorized_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="SET NULL")),
        sa.Column("billing_tenant_id", pg.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "origin_key", name="uq_followup_origin"))
    op.create_index("ix_followup_jobs_tenant_id", "followup_jobs", ["tenant_id"])
    op.create_index("ix_followup_due", "followup_jobs", ["status", "due_at"])
    op.create_index("ix_followup_phone", "followup_jobs", ["tenant_id", "phone"])
    op.create_table("lead_assessments",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", pg.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False),
        sa.Column("lead_id", pg.UUID(as_uuid=True), sa.ForeignKey("leads.lead_id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_call_id", sa.String(36), nullable=False), sa.Column("assessment", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "lead_id", name="uq_lead_assessment"))
    op.create_index("ix_lead_assessments_tenant_id", "lead_assessments", ["tenant_id"])


def downgrade():
    op.drop_table("lead_assessments")
    op.drop_table("followup_jobs")
    op.drop_table("agent_followup_policies")
