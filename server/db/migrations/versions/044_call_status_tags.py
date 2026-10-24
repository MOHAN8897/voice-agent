"""Persist the post-call tag taxonomy on calls for history filtering.

Revision ID: 044_call_status_tags
Revises: 043_billing_gst_invoices_webhooks
Create Date: 2026-10-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "044_call_status_tags"
down_revision: str | None = "043_billing_gst_invoices_webhooks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "calls",
        sa.Column(
            "status_tags",
            postgresql.ARRAY(sa.String(length=48)),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
    )
    op.create_index(
        "ix_calls_status_tags",
        "calls",
        ["status_tags"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_calls_status_tags", table_name="calls")
    op.drop_column("calls", "status_tags")
