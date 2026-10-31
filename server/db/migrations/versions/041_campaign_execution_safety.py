"""Shared call admission and recoverable campaign execution leases.

Revision ID: 041_campaign_execution_safety
Revises: 040_vobiz_tenant_subaccounts
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "041_campaign_execution_safety"
down_revision = "040_vobiz_tenant_subaccounts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("campaigns", sa.Column("client_request_id", sa.String(64), nullable=True))
    op.add_column("campaigns", sa.Column("request_fingerprint", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_campaign_creation_request", "campaigns", ["tenant_id", "client_request_id"])
    op.add_column("campaign_runs", sa.Column("lease_owner", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("campaign_runs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_campaign_runs_recovery", "campaign_runs", ["status", "lease_expires_at"])
    op.create_index("ix_campaign_contacts_ready", "campaign_contacts", ["campaign_id", "status", "next_attempt_at"])
    op.create_table("pstn_dial_requests",
        sa.Column("request_key", sa.String(64), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("destination_hash", sa.String(64), nullable=True),
        sa.Column("provider", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("carrier_id", sa.String(128), nullable=True),
        sa.Column("call_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("response", postgresql.JSONB(), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("media_claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_pstn_dial_requests_active", "pstn_dial_requests", ["tenant_id", "status"])
    op.create_index("ix_pstn_dial_requests_carrier", "pstn_dial_requests", ["provider", "carrier_id"])


def downgrade():
    op.drop_constraint("uq_campaign_creation_request", "campaigns", type_="unique")
    op.drop_column("campaigns", "request_fingerprint")
    op.drop_column("campaigns", "client_request_id")
    op.drop_table("pstn_dial_requests")
    op.drop_index("ix_campaign_contacts_ready", table_name="campaign_contacts")
    op.drop_index("ix_campaign_runs_recovery", table_name="campaign_runs")
    op.drop_column("campaign_runs", "lease_expires_at")
    op.drop_column("campaign_runs", "lease_owner")
