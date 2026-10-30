"""Language-switch callback items and remembered contact languages.

Revision ID: 050_language_switch_requests
Revises: 049_concurrency_channels
Create Date: 2026-10-30

* `language_switch_requests` — callers who asked to speak another language than
  the agent's pack. The tenant calls them back (one by one or as a campaign) in
  the requested language with the same agent; a successful callback marks the
  item done.
* `contact_language_preferences` — the language each contact asked for, so later
  calls by agents configured for it use that pack.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "050_language_switch_requests"
down_revision: str | None = "049_concurrency_channels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "language_switch_requests",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", pg.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False, server_default="language_switch"),
        sa.Column("original_call_id", pg.UUID(as_uuid=True), sa.ForeignKey("calls.call_id", ondelete="SET NULL"), nullable=True),
        sa.Column("phone_e164", sa.String(32), nullable=False),
        sa.Column("contact_name", sa.String(255), nullable=True),
        sa.Column("requested_language", sa.String(16), nullable=False),
        sa.Column("original_language", sa.String(16), nullable=False),
        sa.Column("request_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("last_dial_request_id", sa.String(64), nullable=True),
        sa.Column("campaign_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("callback_call_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("error", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "original_call_id", name="uq_language_switch_origin"),
    )
    op.create_index("ix_language_switch_status", "language_switch_requests", ["tenant_id", "status", "requested_language"])
    op.create_index("ix_language_switch_phone", "language_switch_requests", ["tenant_id", "phone_e164"])

    op.create_table(
        "contact_language_preferences",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", pg.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False),
        sa.Column("phone_e164", sa.String(32), nullable=False),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column("source", sa.String(24), nullable=False, server_default="caller_request"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "phone_e164", name="uq_contact_language_phone"),
    )


def downgrade() -> None:
    op.drop_table("contact_language_preferences")
    op.drop_index("ix_language_switch_phone", table_name="language_switch_requests")
    op.drop_index("ix_language_switch_status", table_name="language_switch_requests")
    op.drop_table("language_switch_requests")
