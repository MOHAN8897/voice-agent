"""Customer support flow, configurable channels, and inquiry ticket queue.

Revision ID: 034_customer_support_flow
Revises: 033_tenant_deletion_flow
Create Date: 2026-10-13 19:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "034_customer_support_flow"
down_revision = "033_tenant_deletion_flow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. customer_support_configs table
    op.create_table(
        "customer_support_configs",
        sa.Column("config_key", sa.String(64), primary_key=True),
        sa.Column("support_email", sa.String(320), nullable=False, server_default="support@dialtact.com"),
        sa.Column("support_phone", sa.String(32), nullable=False, server_default="+1 (800) 555-0199"),
        sa.Column("business_hours", sa.String(128), nullable=False, server_default="Mon - Fri: 9:00 AM - 6:00 PM EST"),
        sa.Column("sla_response_time", sa.String(128), nullable=False, server_default="Within 2 hours for Priority, 24 hours Standard"),
        sa.Column("emergency_hotline", sa.String(32), nullable=True, server_default="+1 (800) 555-0100"),
        sa.Column("auto_reply_message", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # 2. support_inquiries table
    op.create_table(
        "support_inquiries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ticket_number", sa.String(32), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("company", sa.String(255), nullable=True),
        sa.Column("category", sa.String(64), nullable=False, server_default="technical_support"),
        sa.Column("priority", sa.String(32), nullable=False, server_default="normal"),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("admin_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_support_inquiries_ticket_number", "support_inquiries", ["ticket_number"], unique=True)
    op.create_index("ix_support_inquiries_email", "support_inquiries", ["email"])
    op.create_index("ix_support_inquiries_status", "support_inquiries", ["status"])
    op.create_index("ix_support_inquiries_created_at", "support_inquiries", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_support_inquiries_created_at", table_name="support_inquiries")
    op.drop_index("ix_support_inquiries_status", table_name="support_inquiries")
    op.drop_index("ix_support_inquiries_email", table_name="support_inquiries")
    op.drop_index("ix_support_inquiries_ticket_number", table_name="support_inquiries")
    op.drop_table("support_inquiries")
    op.drop_table("customer_support_configs")
