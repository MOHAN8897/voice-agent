"""Social media links, mail/SMTP configuration, tenant tracking, and ticket maintenance.

Revision ID: 035_support_social_mail_and_ticket_management
Revises: 034_customer_support_flow
Create Date: 2026-10-13 20:45:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "035_support_social_mail_and_ticket_management"
down_revision = "034_customer_support_flow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Expand customer_support_configs with social URLs and SMTP gateway settings
    op.add_column("customer_support_configs", sa.Column("twitter_url", sa.String(512), nullable=True, server_default="https://x.com/dialtact"))
    op.add_column("customer_support_configs", sa.Column("linkedin_url", sa.String(512), nullable=True, server_default="https://linkedin.com/company/dialtact"))
    op.add_column("customer_support_configs", sa.Column("github_url", sa.String(512), nullable=True, server_default="https://github.com/dialtact"))
    op.add_column("customer_support_configs", sa.Column("youtube_url", sa.String(512), nullable=True, server_default="https://youtube.com/@dialtact"))
    op.add_column("customer_support_configs", sa.Column("discord_url", sa.String(512), nullable=True, server_default="https://discord.gg/dialtact"))

    op.add_column("customer_support_configs", sa.Column("smtp_host", sa.String(255), nullable=True))
    op.add_column("customer_support_configs", sa.Column("smtp_port", sa.Integer(), nullable=True, server_default="587"))
    op.add_column("customer_support_configs", sa.Column("smtp_username", sa.String(255), nullable=True))
    op.add_column("customer_support_configs", sa.Column("smtp_password", sa.String(255), nullable=True))
    op.add_column("customer_support_configs", sa.Column("smtp_use_tls", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("customer_support_configs", sa.Column("sender_email", sa.String(320), nullable=True, server_default="support@dialtact.com"))
    op.add_column("customer_support_configs", sa.Column("sender_name", sa.String(128), nullable=True, server_default="Dialtact Support Desk"))
    op.add_column("customer_support_configs", sa.Column("notify_customer_on_ticket", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("customer_support_configs", sa.Column("notify_admin_on_ticket", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("customer_support_configs", sa.Column("admin_alert_email", sa.String(320), nullable=True, server_default="support@dialtact.com"))

    # 2. Expand support_inquiries with tenant tracking, assignment, resolution notes, and customer conversation timeline
    op.add_column("support_inquiries", sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("support_inquiries", sa.Column("assigned_to", sa.String(255), nullable=True))
    op.add_column("support_inquiries", sa.Column("resolution_notes", sa.Text(), nullable=True))
    op.add_column("support_inquiries", sa.Column("customer_replies", sa.JSON(), nullable=True, server_default="[]"))
    op.add_column("support_inquiries", sa.Column("tags", sa.JSON(), nullable=True, server_default="[]"))

    op.create_index("ix_support_inquiries_tenant_id", "support_inquiries", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_support_inquiries_tenant_id", table_name="support_inquiries")
    op.drop_column("support_inquiries", "tags")
    op.drop_column("support_inquiries", "customer_replies")
    op.drop_column("support_inquiries", "resolution_notes")
    op.drop_column("support_inquiries", "assigned_to")
    op.drop_column("support_inquiries", "tenant_id")

    op.drop_column("customer_support_configs", "admin_alert_email")
    op.drop_column("customer_support_configs", "notify_admin_on_ticket")
    op.drop_column("customer_support_configs", "notify_customer_on_ticket")
    op.drop_column("customer_support_configs", "sender_name")
    op.drop_column("customer_support_configs", "sender_email")
    op.drop_column("customer_support_configs", "smtp_use_tls")
    op.drop_column("customer_support_configs", "smtp_password")
    op.drop_column("customer_support_configs", "smtp_username")
    op.drop_column("customer_support_configs", "smtp_port")
    op.drop_column("customer_support_configs", "smtp_host")

    op.drop_column("customer_support_configs", "discord_url")
    op.drop_column("customer_support_configs", "youtube_url")
    op.drop_column("customer_support_configs", "github_url")
    op.drop_column("customer_support_configs", "linkedin_url")
    op.drop_column("customer_support_configs", "twitter_url")
