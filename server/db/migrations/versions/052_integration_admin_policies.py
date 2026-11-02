"""Platform-admin control over which integrations workspaces may use.

Revision ID: 052_integration_admin_policies
Revises: 051_platform_admin_accounts
Create Date: 2026-11-02

* `platform_integration_settings` — one row per catalog app the platform admin
  has switched; no row means the app is on.
* `tenant_integration_overrides` — a per-workspace switch that wins over the
  platform one, so an app can be piloted for one workspace or withheld from one.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "052_integration_admin_policies"
down_revision: str | None = "051_platform_admin_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_integration_settings",
        sa.Column("app_name", sa.String(64), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "tenant_integration_overrides",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", pg.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False),
        sa.Column("app_name", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "app_name", name="uq_tenant_integration_overrides_tenant_app"),
    )


def downgrade() -> None:
    op.drop_table("tenant_integration_overrides")
    op.drop_table("platform_integration_settings")
