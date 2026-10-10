"""Add unique constraint on billing_wallet_transactions.reference_id (idempotency guard).

Without a DB-level unique constraint on reference_id, the application-level
scalar_one_or_none() duplicate check in billing_wallet_service.debit_wallet()
is not safe under concurrency: two simultaneous webhook retries with the same
reference_id can both pass the SELECT check before either commits, resulting in
a double-debit. The IntegrityError + rollback in the service relies on this
constraint being present to make the guard atomic.

NULLs: Postgres treats NULLs as distinct, so rows with reference_id=NULL (e.g.
manual top-ups) do not conflict with each other — only non-NULL duplicates are
rejected. This is the correct behaviour for this column's semantics.

Revision ID: 031_wallet_tx_reference_unique
Revises: 030_composio_integrations
Create Date: 2026-10-06
"""
from __future__ import annotations

from alembic import op

revision: str = "031_wallet_tx_reference_unique"
down_revision: str | None = "030_composio_integrations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add index first (fast lookups for the scalar_one_or_none() duplicate check)
    op.create_index(
        "ix_billing_wallet_tx_reference_id",
        "billing_wallet_transactions",
        ["reference_id"],
        unique=False,
    )
    # Add the unique constraint — NULLs are treated as distinct in Postgres
    # so this does not affect rows with reference_id IS NULL.
    op.create_unique_constraint(
        "uq_billing_wallet_tx_reference_id",
        "billing_wallet_transactions",
        ["reference_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_billing_wallet_tx_reference_id",
        "billing_wallet_transactions",
        type_="unique",
    )
    op.drop_index(
        "ix_billing_wallet_tx_reference_id",
        table_name="billing_wallet_transactions",
    )
