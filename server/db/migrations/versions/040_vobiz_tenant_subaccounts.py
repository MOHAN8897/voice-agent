"""Persist tenant carrier subaccounts and provider-specific purchase checkpoints.

Revision ID: 040_vobiz_tenant_subaccounts
Revises: 039_native_billing_rates
Create Date: 2026-10-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "040_vobiz_tenant_subaccounts"
down_revision: str | None = "039_native_billing_rates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vobiz_subaccounts",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("auth_id", sa.String(length=80), nullable=True),
        sa.Column("encrypted_auth_token", sa.Text(), nullable=True),
        sa.Column("parent_auth_id", sa.String(80), nullable=True),
        sa.Column("account_enabled", sa.Boolean(), nullable=False),
        sa.Column("application_id", sa.String(80), nullable=True),
        sa.Column("kyc_session_id", sa.String(80), nullable=True),
        sa.Column("encrypted_kyc_url", sa.Text(), nullable=True),
        sa.Column("kyc_session_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("kyc_session_status", sa.String(32), nullable=True),
        sa.Column("business_type", sa.String(length=40), nullable=False),
        sa.Column("account_name", sa.String(length=255), nullable=False),
        sa.Column("account_email", sa.String(length=320), nullable=False),
        sa.Column("provisioning_status", sa.String(length=32), nullable=False),
        sa.Column("kyc_status", sa.String(length=32), nullable=False),
        sa.Column("kyc_calls_blocked", sa.Boolean(), nullable=False),
        sa.Column("verifications", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("last_status_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("auth_id", name="uq_vobiz_subaccounts_auth_id"),
    )
    op.add_column("number_purchases", sa.Column("provider", sa.String(length=30), nullable=True))
    op.add_column("number_purchases", sa.Column("carrier_number_id", sa.String(length=255), nullable=True))
    op.add_column("phone_numbers", sa.Column("vobiz_account_scope", sa.String(length=16), nullable=True))
    op.add_column("phone_numbers", sa.Column("vobiz_account_tenant_id", postgresql.UUID(as_uuid=True), nullable=True))


def downgrade() -> None:
    op.drop_column("phone_numbers", "vobiz_account_tenant_id")
    op.drop_column("phone_numbers", "vobiz_account_scope")
    op.drop_column("number_purchases", "carrier_number_id")
    op.drop_column("number_purchases", "provider")
    op.drop_table("vobiz_subaccounts")
