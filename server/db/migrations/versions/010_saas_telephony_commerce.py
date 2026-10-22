"""SaaS telephony commerce — purchases, reservations, provision jobs, contacts."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "010_saas_telephony"
down_revision: Union[str, None] = "009_saas_identity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "number_catalog",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("country_code", sa.String(8), nullable=False),
        sa.Column("number_type", sa.String(40), nullable=False),
        sa.Column("stripe_price_id", sa.String(255), nullable=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "number_purchases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("e164", sa.String(20), nullable=False),
        sa.Column("country_code", sa.String(8), nullable=False, server_default="IN"),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("stripe_checkout_session_id", sa.String(255), nullable=True),
        sa.Column("stripe_payment_intent_id", sa.String(255), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(255), nullable=True),
        sa.Column("phone_number_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_number_purchases_tenant_status", "number_purchases", ["tenant_id", "status"])
    op.create_index("ix_number_purchases_stripe_session", "number_purchases", ["stripe_checkout_session_id"], unique=True)

    op.create_table(
        "number_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("e164", sa.String(20), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("purchase_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("number_purchases.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_number_reservations_e164", "number_reservations", ["e164"])

    op.create_table(
        "provision_jobs",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("purchase_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("number_purchases.id"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("purchase_id", name="uq_provision_job_purchase"),
    )
    op.create_index("ix_provision_jobs_status", "provision_jobs", ["status"])

    op.create_table(
        "stripe_webhook_events",
        sa.Column("event_id", sa.String(255), primary_key=True),
        sa.Column("type", sa.String(120), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "telephony_contacts",
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.add_column(
        "phone_numbers",
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agents.agent_id"), nullable=True),
    )
    op.add_column("phone_numbers", sa.Column("purchase_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("phone_numbers", sa.Column("telnyx_number_id", sa.String(100), nullable=True))
    op.add_column("phone_numbers", sa.Column("billing_source", sa.String(30), nullable=False, server_default="manual"))
    op.add_column("phone_numbers", sa.Column("inbound_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("phone_numbers", sa.Column("outbound_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("phone_numbers", sa.Column("stripe_subscription_id", sa.String(255), nullable=True))
    op.add_column("phone_numbers", sa.Column("released_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_phone_numbers_e164", "phone_numbers", ["e164"], unique=True)

    op.add_column("agents", sa.Column("voice_settings", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))


def downgrade() -> None:
    op.drop_column("agents", "voice_settings")
    op.drop_index("ix_phone_numbers_e164", table_name="phone_numbers")
    op.drop_column("phone_numbers", "released_at")
    op.drop_column("phone_numbers", "stripe_subscription_id")
    op.drop_column("phone_numbers", "outbound_enabled")
    op.drop_column("phone_numbers", "inbound_enabled")
    op.drop_column("phone_numbers", "billing_source")
    op.drop_column("phone_numbers", "telnyx_number_id")
    op.drop_column("phone_numbers", "purchase_id")
    op.drop_column("phone_numbers", "agent_id")
    op.drop_table("telephony_contacts")
    op.drop_table("stripe_webhook_events")
    op.drop_table("provision_jobs")
    op.drop_table("number_reservations")
    op.drop_table("number_purchases")
    op.drop_table("number_catalog")
