"""Tenant deletion flow, teardown stages, and export jobs.

Revision ID: 033_tenant_deletion_flow
Revises: 032_billing_rates_versioning
Create Date: 2026-10-13 15:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "033_tenant_deletion_flow"
down_revision = "032_billing_rates_versioning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Update tenants table — new deletion lifecycle columns
    op.add_column("tenants", sa.Column("deleted_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("tenants", sa.Column("deletion_reason", sa.String(255), nullable=True))
    op.add_column("tenants", sa.Column("scheduled_purge_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tenants", sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tenants", sa.Column("legal_hold", sa.Boolean(), server_default="false", nullable=False))

    # Check constraint on tenants.status (quarantined + deleting added to existing active/deleted)
    op.create_check_constraint(
        "ck_tenants_status",
        "tenants",
        "status IN ('active', 'quarantined', 'deleting', 'deleted')",
    )

    # 2. Update tenant_teardown_jobs table — stage machine + distributed locking
    op.add_column(
        "tenant_teardown_jobs",
        sa.Column("stage", sa.String(50), server_default="queued", nullable=False),
    )
    op.add_column(
        "tenant_teardown_jobs",
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("tenant_teardown_jobs", sa.Column("locked_by", sa.String(64), nullable=True))
    op.add_column(
        "tenant_teardown_jobs",
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )
    # nullable=True to allow backfilling existing rows without a default
    op.add_column("tenant_teardown_jobs", sa.Column("idempotency_key", sa.String(128), nullable=True))
    op.add_column(
        "tenant_teardown_jobs",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Partial unique index: enforce one active teardown job per tenant
    op.create_index(
        "uq_tenant_teardown_active",
        "tenant_teardown_jobs",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )

    # 3. Create tenant_export_jobs table
    op.create_table(
        "tenant_export_jobs",
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(30), server_default="queued", nullable=False),
        sa.Column("download_url", sa.String(512), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_tenant_export_jobs_tenant_created",
        "tenant_export_jobs",
        ["tenant_id", "created_at"],
    )
    op.create_index("ix_tenant_export_jobs_user_id", "tenant_export_jobs", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_tenant_export_jobs_user_id", table_name="tenant_export_jobs")
    op.drop_index("ix_tenant_export_jobs_tenant_created", table_name="tenant_export_jobs")
    op.drop_table("tenant_export_jobs")

    op.drop_index("uq_tenant_teardown_active", table_name="tenant_teardown_jobs")
    op.drop_column("tenant_teardown_jobs", "completed_at")
    op.drop_column("tenant_teardown_jobs", "idempotency_key")
    op.drop_column("tenant_teardown_jobs", "locked_until")
    op.drop_column("tenant_teardown_jobs", "locked_by")
    op.drop_column("tenant_teardown_jobs", "attempts")
    op.drop_column("tenant_teardown_jobs", "stage")

    op.drop_constraint("ck_tenants_status", "tenants", type_="check")
    op.drop_column("tenants", "legal_hold")
    op.drop_column("tenants", "restored_at")
    op.drop_column("tenants", "scheduled_purge_at")
    op.drop_column("tenants", "deletion_reason")
    op.drop_column("tenants", "deleted_by_user_id")
