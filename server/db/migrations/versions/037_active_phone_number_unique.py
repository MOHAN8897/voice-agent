"""Prevent duplicate active phone numbers during concurrent provisioning.

Revision ID: 037_active_phone_number_unique
Revises: 036_unvendor_legacy_columns
Create Date: 2026-10-14
"""
from alembic import op
import sqlalchemy as sa


revision = "037_active_phone_number_unique"
down_revision = "036_unvendor_legacy_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    duplicate = bind.execute(
        sa.text(
            "SELECT 1 FROM phone_numbers WHERE released_at IS NULL "
            "GROUP BY e164 HAVING count(*) > 1 LIMIT 1"
        )
    ).scalar_one_or_none()
    if duplicate:
        raise RuntimeError(
            "Resolve duplicate active phone number rows before applying migration 037"
        )
    op.create_index(
        "uq_phone_numbers_e164_active",
        "phone_numbers",
        ["e164"],
        unique=True,
        postgresql_where=sa.text("released_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_phone_numbers_e164_active", table_name="phone_numbers")
