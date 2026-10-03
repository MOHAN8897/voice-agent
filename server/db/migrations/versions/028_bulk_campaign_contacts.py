"""Add contact_lists, contacts, contact_import_templates, and campaign contact snapshot columns.

Revision ID: 028_bulk_campaign_contacts
Revises: 027_session_sliding_window
Create Date: 2026-10-03
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "028_bulk_campaign_contacts"
down_revision: str | None = "027_session_sliding_window"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    # 1. contact_lists table
    if not _has_table("contact_lists"):
        op.create_table(
            "contact_lists",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("total_contacts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_contact_lists_tenant_id", "contact_lists", ["tenant_id"])

    # 2. contacts table
    if not _has_table("contacts"):
        op.create_table(
            "contacts",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False),
            sa.Column("contact_list_id", UUID(as_uuid=True), sa.ForeignKey("contact_lists.id", ondelete="SET NULL"), nullable=True),
            sa.Column("phone", sa.String(30), nullable=False),
            sa.Column("first_name", sa.String(150), nullable=True),
            sa.Column("last_name", sa.String(150), nullable=True),
            sa.Column("full_name", sa.String(255), nullable=True),
            sa.Column("email", sa.String(255), nullable=True),
            sa.Column("company", sa.String(255), nullable=True),
            sa.Column("job_title", sa.String(255), nullable=True),
            sa.Column("country", sa.String(100), nullable=True),
            sa.Column("city", sa.String(100), nullable=True),
            sa.Column("state", sa.String(100), nullable=True),
            sa.Column("timezone", sa.String(100), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("custom_fields", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("raw_data", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("source", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_contacts_tenant_id", "contacts", ["tenant_id"])
        op.create_index("ix_contacts_contact_list_id", "contacts", ["contact_list_id"])
        op.create_index("ix_contacts_phone", "contacts", ["phone"])

    # 3. contact_import_templates table
    if not _has_table("contact_import_templates"):
        op.create_table(
            "contact_import_templates",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False),
            sa.Column("template_name", sa.String(255), nullable=False),
            sa.Column("source_headers", JSONB, nullable=False),
            sa.Column("mapping", JSONB, nullable=False),
            sa.Column("default_country", sa.String(10), nullable=False, server_default="US"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_contact_import_templates_tenant_id", "contact_import_templates", ["tenant_id"])

    # 4. campaign_contacts additions
    if not _has_column("campaign_contacts", "contact_id"):
        op.add_column("campaign_contacts", sa.Column("contact_id", UUID(as_uuid=True), sa.ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True))
    if not _has_column("campaign_contacts", "phone_snapshot"):
        op.add_column("campaign_contacts", sa.Column("phone_snapshot", sa.String(30), nullable=True))
    if not _has_column("campaign_contacts", "resolved_variables"):
        op.add_column("campaign_contacts", sa.Column("resolved_variables", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")))
    if not _has_column("campaign_contacts", "next_attempt_at"):
        op.add_column("campaign_contacts", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))

    # 5. campaigns additions
    if not _has_column("campaigns", "description"):
        op.add_column("campaigns", sa.Column("description", sa.Text(), nullable=True))
    if not _has_column("campaigns", "default_country"):
        op.add_column("campaigns", sa.Column("default_country", sa.String(10), nullable=False, server_default="US"))


def downgrade() -> None:
    if _has_column("campaigns", "default_country"):
        op.drop_column("campaigns", "default_country")
    if _has_column("campaigns", "description"):
        op.drop_column("campaigns", "description")
    if _has_column("campaign_contacts", "next_attempt_at"):
        op.drop_column("campaign_contacts", "next_attempt_at")
    if _has_column("campaign_contacts", "resolved_variables"):
        op.drop_column("campaign_contacts", "resolved_variables")
    if _has_column("campaign_contacts", "phone_snapshot"):
        op.drop_column("campaign_contacts", "phone_snapshot")
    if _has_column("campaign_contacts", "contact_id"):
        op.drop_column("campaign_contacts", "contact_id")
    if _has_table("contact_import_templates"):
        op.drop_table("contact_import_templates")
    if _has_table("contacts"):
        op.drop_table("contacts")
    if _has_table("contact_lists"):
        op.drop_table("contact_lists")
