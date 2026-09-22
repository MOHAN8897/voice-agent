"""Razorpay orders, invoices, INR wallet balance."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "012_razorpay_invoices"
down_revision: Union[str, None] = "011_saas_leads_billing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "billing_wallets",
        sa.Column("balance_inr_paise", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "billing_invoices",
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("invoice_number", sa.String(32), nullable=False),
        sa.Column("amount_inr_paise", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("razorpay_order_id", sa.String(64), nullable=True),
        sa.Column("razorpay_payment_id", sa.String(64), nullable=True),
        sa.Column("line_items", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("invoice_number", name="uq_invoice_number"),
    )
    op.create_table(
        "razorpay_orders",
        sa.Column("order_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("amount_inr_paise", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="created"),
        sa.Column("purpose", sa.String(40), nullable=False, server_default="wallet_topup"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("razorpay_orders")
    op.drop_table("billing_invoices")
    op.drop_column("billing_wallets", "balance_inr_paise")
