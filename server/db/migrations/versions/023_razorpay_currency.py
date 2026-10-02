"""Record the currency a Razorpay payment was actually charged in.

International top-ups are billed in the customer's currency but settle in INR,
so an invoice that only stores the rupee figure cannot be reconciled against the
Razorpay dashboard. These columns keep both, plus the settled INR amount.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "023_razorpay_currency"
down_revision: str | None = "022_reservation_e164_unique"
branch_labels = None
depends_on = None


def _add(table: str, columns: list[tuple[str, sa.Column]]) -> None:
    for name, col in columns:
        op.add_column(table, sa.Column(name, col.type, nullable=col.nullable, server_default=col.server_default))


def upgrade() -> None:
    _add(
        "razorpay_orders",
        [
            ("currency", sa.Column("currency", sa.String(8), nullable=False, server_default="INR")),
            ("amount_minor", sa.Column("amount_minor", sa.Integer(), nullable=True)),
        ],
    )
    _add(
        "billing_invoices",
        [
            ("currency", sa.Column("currency", sa.String(8), nullable=False, server_default="INR")),
            ("amount_minor", sa.Column("amount_minor", sa.Integer(), nullable=True)),
        ],
    )
    op.create_index("ix_billing_invoices_currency", "billing_invoices", ["currency"])


def downgrade() -> None:
    op.drop_index("ix_billing_invoices_currency", table_name="billing_invoices")
    for table in ("billing_invoices", "razorpay_orders"):
        for name in ("amount_minor", "currency"):
            op.drop_column(table, name)