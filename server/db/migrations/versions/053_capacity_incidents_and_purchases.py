"""Capacity incidents and Vobiz capacity purchases.

Revision ID: 053_capacity_incidents_and_purchases
Revises: 052_integration_admin_policies
Create Date: 2026-11-04

* `capacity_incidents`: calls and purchases refused for lack of channels or
  dialling speed, one row per kind, workspace and minute (with a count), so the
  admin capacity page can show who was blocked and why.
* `vobiz_capacity_purchases`: concurrency / CPS bundles bought on the platform
  Vobiz account from the admin page. One row per click (unique request id), so a
  retry never buys twice.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "053_capacity_incidents_and_purchases"
down_revision: str | None = "052_integration_admin_policies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "capacity_incidents",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("tenant_key", sa.String(40), nullable=False),
        sa.Column("tenant_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("detail", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_capacity_incidents_created", "capacity_incidents", ["created_at"])
    op.create_table(
        "vobiz_capacity_purchases",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", sa.String(64), nullable=False, unique=True),
        sa.Column("resource_type", sa.String(24), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("quoted_monthly_cost", sa.String(32), nullable=True),
        sa.Column("monthly_cost", sa.String(32), nullable=True),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("vobiz_subscription_id", sa.String(128), nullable=True),
        sa.Column("next_billing_date", sa.String(40), nullable=True),
        sa.Column("error", sa.String(400), nullable=True),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("vobiz_capacity_purchases")
    op.drop_index("ix_capacity_incidents_created", table_name="capacity_incidents")
    op.drop_table("capacity_incidents")
