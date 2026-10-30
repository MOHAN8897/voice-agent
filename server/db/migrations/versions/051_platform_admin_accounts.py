"""Stored platform-admin accounts for the admin portal.

Revision ID: 051_platform_admin_accounts
Revises: 050_language_switch_requests
Create Date: 2026-10-30

* `platform_admin_accounts` — people who can sign in to the admin portal, with a
  role, a status (invited / active / suspended / removed), a PBKDF2 password hash,
  a hashed one-time invite/reset token with an expiry, and a session epoch that
  revokes every session the account holds when bumped. The env-configured
  DEV_PORTAL_USERNAME login is not stored and keeps working unchanged.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "051_platform_admin_accounts"
down_revision: str | None = "050_language_switch_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_admin_accounts",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("role", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="invited"),
        sa.Column("password_hash", sa.String(512), nullable=False, server_default=""),
        sa.Column("session_epoch", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("invite_token_hash", sa.String(128), nullable=True),
        sa.Column("invite_purpose", sa.String(20), nullable=True),
        sa.Column("invite_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invite_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sign_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sign_in_ip", sa.String(64), nullable=True),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status_reason", sa.String(500), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("username", name="uq_platform_admin_username"),
        sa.UniqueConstraint("email", name="uq_platform_admin_email"),
    )
    op.create_index("ix_platform_admin_status", "platform_admin_accounts", ["status", "role"])
    op.create_index("ix_platform_admin_invite_token", "platform_admin_accounts", ["invite_token_hash"])


def downgrade() -> None:
    op.drop_index("ix_platform_admin_invite_token", table_name="platform_admin_accounts")
    op.drop_index("ix_platform_admin_status", table_name="platform_admin_accounts")
    op.drop_table("platform_admin_accounts")
