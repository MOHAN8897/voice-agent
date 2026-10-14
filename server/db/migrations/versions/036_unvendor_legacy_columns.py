"""Rename legacy vendor-named columns to neutral integration fields.

Revision ID: 036_unvendor_legacy_columns
Revises: 035_support_mail_ticket
Create Date: 2026-10-14
"""
import sqlalchemy as sa
from alembic import op

revision = "036_unvendor_legacy_columns"
down_revision = "035_support_mail_ticket"
branch_labels = None
depends_on = None


def _rename_column(table: str, old_name: str, new_name: str) -> None:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return
    names = {column["name"] for column in inspector.get_columns(table)}
    if old_name in names and new_name in names:
        raise RuntimeError(
            f"Cannot rename {table}.{old_name}: {table}.{new_name} already exists"
        )
    if old_name in names:
        op.alter_column(table, old_name, new_column_name=new_name)


def upgrade() -> None:
    _rename_column("phone_numbers", "plivo_number_id", "carrier_number_id")
    _rename_column("dial_attempts", "plivo_call_uuid", "carrier_call_uuid")
    _rename_column("tenant_integrations", "composio_connection_id", "connection_id")


def downgrade() -> None:
    _rename_column("tenant_integrations", "connection_id", "composio_connection_id")
    _rename_column("dial_attempts", "carrier_call_uuid", "plivo_call_uuid")
    _rename_column("phone_numbers", "carrier_number_id", "plivo_number_id")
