"""Identity verification state (Didit KYC) per subscriber user.

One row per user, latest session wins. `status` mirrors Didit's session status
literals exactly ("Not Started" | "In Progress" | "Awaiting User" | "In Review" |
"Approved" | "Declined" | "Resubmitted" | "Abandoned" | "Expired" | "Kyc
Expired") because those strings are the dispatch keys in the webhook handler.

Only the verified webhook writes `status`. The create-session response and the
browser callback are hints, never proof.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "021_kyc_verification"
down_revision: str | None = "020_call_is_test"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kyc_verifications",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.tenant_id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(30), nullable=False, server_default="Not Started"),
        sa.Column("didit_session_id", sa.String(64), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        # Full verified decision JSON, so a review can be explained later.
        sa.Column("decision", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_kyc_verifications_tenant_id", "kyc_verifications", ["tenant_id"])
    # The webhook is the only writer of status and it is not idempotent by session,
    # so a repeated delivery must not find a second row to race with.
    op.create_index(
        "uq_kyc_verifications_session_id",
        "kyc_verifications",
        ["didit_session_id"],
        unique=True,
        postgresql_where=sa.text("didit_session_id is not null"),
    )


def downgrade() -> None:
    op.drop_index("uq_kyc_verifications_session_id", table_name="kyc_verifications")
    op.drop_index("ix_kyc_verifications_tenant_id", table_name="kyc_verifications")
    op.drop_table("kyc_verifications")