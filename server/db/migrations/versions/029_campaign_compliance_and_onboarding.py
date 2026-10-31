"""Add campaign compliance attestation, agent recording disclosure, normalized onboarding surveys, and audit-preserved DND columns.

Revision ID: 029_compliance_and_onboarding
Revises: 028_bulk_campaign_contacts
Create Date: 2026-10-04
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "029_compliance_and_onboarding"
down_revision: str | None = "028_bulk_campaign_contacts"
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


def _has_index(table: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return index_name in {idx["name"] for idx in inspector.get_indexes(table)}


def upgrade() -> None:
    # 1. campaigns table legal attestation columns
    if _has_table("campaigns"):
        if not _has_column("campaigns", "consent_confirmed"):
            op.add_column(
                "campaigns",
                sa.Column("consent_confirmed", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
            )
        if not _has_column("campaigns", "consent_attestation_version"):
            op.add_column(
                "campaigns",
                sa.Column("consent_attestation_version", sa.String(32), nullable=False, server_default="2026-10-v1"),
            )
        if not _has_column("campaigns", "attested_by_user_id"):
            op.add_column(
                "campaigns",
                sa.Column(
                    "attested_by_user_id",
                    UUID(as_uuid=True),
                    sa.ForeignKey("users.user_id", ondelete="SET NULL"),
                    nullable=True,
                ),
            )
        if not _has_column("campaigns", "attested_at"):
            op.add_column("campaigns", sa.Column("attested_at", sa.DateTime(timezone=True), nullable=True))
        if not _has_column("campaigns", "attested_ip"):
            op.add_column("campaigns", sa.Column("attested_ip", sa.String(64), nullable=True))
        if not _has_column("campaigns", "attested_user_agent"):
            op.add_column("campaigns", sa.Column("attested_user_agent", sa.String(255), nullable=True))

    # 2. agents table recording disclosure columns
    if _has_table("agents"):
        if not _has_column("agents", "recording_disclosure_enabled"):
            op.add_column(
                "agents",
                sa.Column(
                    "recording_disclosure_enabled",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("FALSE"),
                ),
            )
        if not _has_column("agents", "recording_disclosure_text"):
            op.add_column(
                "agents",
                sa.Column(
                    "recording_disclosure_text",
                    sa.String(255),
                    nullable=False,
                    server_default="This call may be recorded for quality and training purposes.",
                ),
            )

    # 3. Normalized user_onboarding_surveys table
    if not _has_table("user_onboarding_surveys"):
        op.create_table(
            "user_onboarding_surveys",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "user_id",
                UUID(as_uuid=True),
                sa.ForeignKey("users.user_id", ondelete="CASCADE"),
                nullable=False,
                unique=True,
            ),
            sa.Column(
                "tenant_id",
                UUID(as_uuid=True),
                sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("role", sa.String(64), nullable=False),
            sa.Column("referral_source", sa.String(64), nullable=False),
            sa.Column("primary_use_case", sa.String(64), nullable=False),
            sa.Column("estimated_monthly_minutes", sa.String(32), nullable=False),
            sa.Column(
                "terms_and_telephony_accepted",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("FALSE"),
            ),
            sa.Column("terms_version", sa.String(32), nullable=False, server_default="2026-10-v1"),
            sa.Column("acceptable_use_version", sa.String(32), nullable=False, server_default="2026-10-v1"),
            sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_user_onboarding_surveys_user_id", "user_onboarding_surveys", ["user_id"])
        op.create_index("ix_user_onboarding_surveys_tenant_id", "user_onboarding_surveys", ["tenant_id"])

    # 4. dnc_list table soft-deactivation and audit columns
    if _has_table("dnc_list"):
        if not _has_column("dnc_list", "active"):
            op.add_column(
                "dnc_list",
                sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
            )
        if not _has_column("dnc_list", "source"):
            op.add_column(
                "dnc_list",
                sa.Column("source", sa.String(64), nullable=False, server_default="manual"),
            )
        if not _has_column("dnc_list", "added_by_user_id"):
            op.add_column(
                "dnc_list",
                sa.Column(
                    "added_by_user_id",
                    UUID(as_uuid=True),
                    sa.ForeignKey("users.user_id", ondelete="SET NULL"),
                    nullable=True,
                ),
            )
        if not _has_column("dnc_list", "removed_at"):
            op.add_column("dnc_list", sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True))
        if not _has_column("dnc_list", "removed_by_user_id"):
            op.add_column(
                "dnc_list",
                sa.Column(
                    "removed_by_user_id",
                    UUID(as_uuid=True),
                    sa.ForeignKey("users.user_id", ondelete="SET NULL"),
                    nullable=True,
                ),
            )
        if not _has_column("dnc_list", "removal_reason"):
            op.add_column("dnc_list", sa.Column("removal_reason", sa.String(255), nullable=True))
        if not _has_column("dnc_list", "reconsent_confirmed"):
            op.add_column(
                "dnc_list",
                sa.Column("reconsent_confirmed", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
            )
        if not _has_index("dnc_list", "ix_dnc_list_active"):
            op.create_index("ix_dnc_list_active", "dnc_list", ["active"])


def downgrade() -> None:
    # 4. dnc_list
    if _has_table("dnc_list"):
        if _has_index("dnc_list", "ix_dnc_list_active"):
            op.drop_index("ix_dnc_list_active", table_name="dnc_list")
        if _has_column("dnc_list", "reconsent_confirmed"):
            op.drop_column("dnc_list", "reconsent_confirmed")
        if _has_column("dnc_list", "removal_reason"):
            op.drop_column("dnc_list", "removal_reason")
        if _has_column("dnc_list", "removed_by_user_id"):
            op.drop_column("dnc_list", "removed_by_user_id")
        if _has_column("dnc_list", "removed_at"):
            op.drop_column("dnc_list", "removed_at")
        if _has_column("dnc_list", "added_by_user_id"):
            op.drop_column("dnc_list", "added_by_user_id")
        if _has_column("dnc_list", "source"):
            op.drop_column("dnc_list", "source")
        if _has_column("dnc_list", "active"):
            op.drop_column("dnc_list", "active")

    # 3. user_onboarding_surveys
    if _has_table("user_onboarding_surveys"):
        op.drop_table("user_onboarding_surveys")

    # 2. agents
    if _has_table("agents"):
        if _has_column("agents", "recording_disclosure_text"):
            op.drop_column("agents", "recording_disclosure_text")
        if _has_column("agents", "recording_disclosure_enabled"):
            op.drop_column("agents", "recording_disclosure_enabled")

    # 1. campaigns
    if _has_table("campaigns"):
        if _has_column("campaigns", "attested_user_agent"):
            op.drop_column("campaigns", "attested_user_agent")
        if _has_column("campaigns", "attested_ip"):
            op.drop_column("campaigns", "attested_ip")
        if _has_column("campaigns", "attested_at"):
            op.drop_column("campaigns", "attested_at")
        if _has_column("campaigns", "attested_by_user_id"):
            op.drop_column("campaigns", "attested_by_user_id")
        if _has_column("campaigns", "consent_attestation_version"):
            op.drop_column("campaigns", "consent_attestation_version")
        if _has_column("campaigns", "consent_confirmed"):
            op.drop_column("campaigns", "consent_confirmed")
