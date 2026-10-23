"""GST invoicing, payment lifecycle, webhook inbox and refunds.

Revision ID: 043_billing_gst_invoices_webhooks
Revises: 042_three_tier_billing_rates
Create Date: 2026-10-23

Adds the statutory pieces the wallet ledger was missing: a buyer billing
profile (place of supply / GSTIN), operator-owned GST configuration, invoice
tax and legal snapshots, order lifecycle/failure details, a durable webhook
inbox, refunds and GST credit notes.

Existing invoices keep their numbers and are backfilled as untaxed supplies so
no historical document changes meaning.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "043_billing_gst_invoices_webhooks"
down_revision: str | None = "042_three_tier_billing_rates"
branch_labels = None
depends_on = None


_INVOICE_COLUMNS = (
    ("taxable_minor", sa.BigInteger(), "0"),
    ("tax_minor", sa.BigInteger(), "0"),
    ("taxable_inr_paise", sa.BigInteger(), "0"),
    ("tax_inr_paise", sa.BigInteger(), "0"),
    ("cgst_inr_paise", sa.BigInteger(), "0"),
    ("sgst_inr_paise", sa.BigInteger(), "0"),
    ("igst_inr_paise", sa.BigInteger(), "0"),
    ("tax_rate_bps", sa.Integer(), "0"),
    ("tax_kind", sa.String(20), "'none'"),
    ("sac_code", sa.String(12), None),
    ("place_of_supply", sa.String(120), None),
    ("place_of_supply_code", sa.String(4), None),
    ("customer_gstin", sa.String(15), None),
    ("fy", sa.String(7), None),
    ("sequence", sa.Integer(), None),
    ("payment_method", sa.String(40), None),
)

_ORDER_COLUMNS = (
    ("gross_minor", sa.BigInteger(), None),
    ("taxable_minor", sa.BigInteger(), None),
    ("tax_minor", sa.BigInteger(), None),
    ("tax_rate_bps", sa.Integer(), "0"),
    ("tax_kind", sa.String(20), "'none'"),
    ("place_of_supply", sa.String(120), None),
    ("place_of_supply_code", sa.String(4), None),
    ("payment_id", sa.String(64), None),
    ("payment_method", sa.String(40), None),
    ("failure_code", sa.String(80), None),
    ("failure_reason", sa.Text(), None),
    ("base_amount_inr_paise", sa.BigInteger(), None),
    ("fee_minor", sa.BigInteger(), None),
    ("tax_on_fee_minor", sa.BigInteger(), None),
    ("settlement_id", sa.String(64), None),
)


def upgrade() -> None:
    for name, column_type, default in _INVOICE_COLUMNS:
        kwargs = {"nullable": default is None}
        if default is not None:
            kwargs["server_default"] = sa.text(default)
        op.add_column("billing_invoices", sa.Column(name, column_type, **kwargs))

    op.add_column(
        "billing_invoices",
        sa.Column("supplier_snapshot", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "billing_invoices",
        sa.Column("buyer_snapshot", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "billing_invoices",
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Legacy rows were single-line, untaxed top-ups. Backfill the split so
    # reports can treat old and new invoices uniformly without inventing tax.
    op.execute(
        "UPDATE billing_invoices SET taxable_minor = COALESCE(amount_minor, 0), "
        "taxable_inr_paise = amount_inr_paise WHERE taxable_inr_paise = 0"
    )
    op.create_index(
        "ix_billing_invoices_tenant_created",
        "billing_invoices",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_billing_invoices_payment_id",
        "billing_invoices",
        ["razorpay_payment_id"],
        unique=True,
    )

    for name, column_type, default in _ORDER_COLUMNS:
        kwargs = {"nullable": default is None}
        if default is not None:
            kwargs["server_default"] = sa.text(default)
        op.add_column("razorpay_orders", sa.Column(name, column_type, **kwargs))
    op.add_column(
        "razorpay_orders",
        sa.Column("buyer_snapshot", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "razorpay_orders",
        sa.Column("supplier_snapshot", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column("razorpay_orders", sa.Column("sac_code", sa.String(12), nullable=True))
    op.add_column("razorpay_orders", sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("razorpay_orders", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("razorpay_orders", sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "UPDATE razorpay_orders SET gross_minor = amount_minor, taxable_minor = amount_minor "
        "WHERE gross_minor IS NULL"
    )
    op.create_index("ix_razorpay_orders_status_created", "razorpay_orders", ["status", "created_at"])
    op.create_index("ix_razorpay_orders_tenant_created", "razorpay_orders", ["tenant_id", "created_at"])
    op.create_index("ix_razorpay_orders_payment_id", "razorpay_orders", ["payment_id"], unique=True)

    op.create_table(
        "tenant_billing_profiles",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("legal_name", sa.String(255), nullable=True),
        sa.Column("gstin", sa.String(15), nullable=True),
        sa.Column("billing_email", sa.String(320), nullable=True),
        sa.Column("address_line1", sa.String(255), nullable=True),
        sa.Column("address_line2", sa.String(255), nullable=True),
        sa.Column("city", sa.String(120), nullable=True),
        sa.Column("state_name", sa.String(120), nullable=True),
        sa.Column("state_code", sa.String(4), nullable=True),
        sa.Column("postal_code", sa.String(12), nullable=True),
        sa.Column("country_code", sa.String(2), nullable=False, server_default=sa.text("'IN'")),
        sa.Column("customer_type", sa.String(20), nullable=False, server_default=sa.text("'individual'")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "platform_tax_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("legal_name", sa.String(255), nullable=False, server_default=sa.text("''")),
        sa.Column("trade_name", sa.String(255), nullable=False, server_default=sa.text("''")),
        sa.Column("gstin", sa.String(15), nullable=True),
        sa.Column("pan", sa.String(10), nullable=True),
        sa.Column("address_line1", sa.String(255), nullable=False, server_default=sa.text("''")),
        sa.Column("address_line2", sa.String(255), nullable=False, server_default=sa.text("''")),
        sa.Column("city", sa.String(120), nullable=False, server_default=sa.text("''")),
        sa.Column("state_name", sa.String(120), nullable=False, server_default=sa.text("''")),
        sa.Column("state_code", sa.String(4), nullable=False, server_default=sa.text("''")),
        sa.Column("postal_code", sa.String(12), nullable=False, server_default=sa.text("''")),
        sa.Column("country_code", sa.String(2), nullable=False, server_default=sa.text("'IN'")),
        sa.Column("support_email", sa.String(320), nullable=False, server_default=sa.text("''")),
        sa.Column("support_phone", sa.String(40), nullable=False, server_default=sa.text("''")),
        sa.Column("sac_code", sa.String(12), nullable=False, server_default=sa.text("'998413'")),
        sa.Column("default_rate_bps", sa.Integer(), nullable=False, server_default=sa.text("1800")),
        sa.Column("price_includes_tax", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("export_zero_rated", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("invoice_prefix", sa.String(4), nullable=False, server_default=sa.text("'INV'")),
        sa.Column("credit_note_prefix", sa.String(4), nullable=False, server_default=sa.text("'CN'")),
        sa.Column("lut_number", sa.String(32), nullable=True),
        sa.Column("invoice_terms", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.execute("INSERT INTO platform_tax_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING")

    op.create_table(
        "invoice_sequences",
        sa.Column("kind", sa.String(4), primary_key=True),
        sa.Column("fy", sa.String(7), primary_key=True),
        sa.Column("last_number", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "razorpay_webhook_events",
        sa.Column("event_id", sa.String(128), primary_key=True),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'processing'")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_razorpay_webhook_events_status", "razorpay_webhook_events", ["status", "received_at"])

    op.create_table(
        "razorpay_refunds",
        sa.Column("refund_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("payment_id", sa.String(64), nullable=False),
        sa.Column("order_id", sa.String(64), nullable=True),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default=sa.text("'INR'")),
        sa.Column("credit_inr_paise", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("tax_inr_paise", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'processed'")),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_razorpay_refunds_payment_id", "razorpay_refunds", ["payment_id"])
    op.create_index("ix_razorpay_refunds_order_id", "razorpay_refunds", ["order_id"])
    op.create_index("ix_razorpay_refunds_tenant_created", "razorpay_refunds", ["tenant_id", "created_at"])

    op.create_table(
        "credit_notes",
        sa.Column("credit_note_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("billing_invoices.invoice_id"), nullable=False),
        sa.Column("invoice_number", sa.String(32), nullable=False),
        sa.Column("credit_note_number", sa.String(32), nullable=False),
        sa.Column("razorpay_refund_id", sa.String(64), nullable=True, unique=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default=sa.text("'INR'")),
        sa.Column("gross_inr_paise", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("taxable_inr_paise", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("tax_inr_paise", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("cgst_inr_paise", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("sgst_inr_paise", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("igst_inr_paise", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("tax_rate_bps", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("tax_kind", sa.String(20), nullable=False, server_default=sa.text("'none'")),
        sa.Column("fy", sa.String(7), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=True),
        sa.Column("supplier_snapshot", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("buyer_snapshot", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'issued'")),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("credit_note_number", name="uq_credit_note_number"),
    )
    op.create_index("ix_credit_notes_tenant_created", "credit_notes", ["tenant_id", "created_at"])
    op.create_index("ix_credit_notes_invoice_id", "credit_notes", ["invoice_id"])


def downgrade() -> None:
    op.drop_table("credit_notes")
    op.drop_table("razorpay_refunds")
    op.drop_table("razorpay_webhook_events")
    op.drop_table("invoice_sequences")
    op.drop_table("platform_tax_settings")
    op.drop_table("tenant_billing_profiles")

    op.drop_index("ix_razorpay_orders_payment_id", table_name="razorpay_orders")
    op.drop_index("ix_razorpay_orders_tenant_created", table_name="razorpay_orders")
    op.drop_index("ix_razorpay_orders_status_created", table_name="razorpay_orders")
    for name in reversed(_ORDER_COLUMNS):
        op.drop_column("razorpay_orders", name[0])
    op.drop_column("razorpay_orders", "buyer_snapshot")
    op.drop_column("razorpay_orders", "supplier_snapshot")
    op.drop_column("razorpay_orders", "sac_code")
    op.drop_column("razorpay_orders", "paid_at")
    op.drop_column("razorpay_orders", "expires_at")
    op.drop_column("razorpay_orders", "settled_at")

    op.drop_index("ix_billing_invoices_payment_id", table_name="billing_invoices")
    op.drop_index("ix_billing_invoices_tenant_created", table_name="billing_invoices")
    for name in reversed(_INVOICE_COLUMNS):
        op.drop_column("billing_invoices", name[0])
    op.drop_column("billing_invoices", "supplier_snapshot")
    op.drop_column("billing_invoices", "buyer_snapshot")
    op.drop_column("billing_invoices", "paid_at")
