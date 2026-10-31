"""Expand ck_tenants_status constraint to support deleted, cancelled, suspended, quarantined, past_due.

Revision ID: 038_tenants_status_ck_expand
Revises: 037_active_phone_number_unique
Create Date: 2026-10-14
"""
from alembic import op
import sqlalchemy as sa


revision = "038_tenants_status_ck_expand"
down_revision = "037_active_phone_number_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_tenants_status", "tenants", type_="check")
    op.create_check_constraint(
        "ck_tenants_status",
        "tenants",
        "status IN ('active', 'quarantined', 'deleting', 'deleted', 'suspended', 'cancelled', 'past_due')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_tenants_status", "tenants", type_="check")
    op.create_check_constraint(
        "ck_tenants_status",
        "tenants",
        "status IN ('active', 'quarantined', 'deleting', 'deleted')",
    )
