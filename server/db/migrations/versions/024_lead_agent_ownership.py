"""Agent ownership for leads, and a self-healing number pool.

Two defects share this migration because they are both consequences of the same
omission: nothing recorded which agent a lead or a phone number belonged to.

1. `leads.agent_id` — leads were tenant-wide with no owner, so every agent
   workspace had to fall back to the shared pipeline. The post-call LLM outcome
   (disposition + summary) had nowhere to land.

2. `phone_numbers.agent_id` — deleting an agent left the number pointing at a
   row that no longer existed (or at an archived agent), so the pool rendered it
   as "(assigned elsewhere)" and disabled it. The FK becomes ON DELETE SET NULL
   as a database-level guarantee, and the backfill repairs rows already orphaned
   by the old behaviour.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "024_lead_agent_ownership"
down_revision: str | None = "023_razorpay_currency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Leads gain an owner. Nullable so pre-existing leads stay visible rather
    #    than silently disappearing from the workspace they already appeared in.
    op.add_column(
        "leads",
        sa.Column("agent_id", sa.String(36), nullable=True),
    )
    op.create_index("ix_leads_agent_id", "leads", ["agent_id"])
    op.create_index("ix_leads_tenant_agent", "leads", ["tenant_id", "agent_id"])
    # The column is agent_id text to match Agent.agent_id's textual UUID usage
    # elsewhere; backfill nothing, since no historical attribution exists.

    # 2. A deleted agent must not take its number hostage.
    op.execute(
        """
        DELETE FROM phone_numbers
         WHERE released_at IS NOT NULL
           AND agent_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE phone_numbers
           SET agent_id = NULL
         WHERE agent_id IS NOT NULL
           AND NOT EXISTS (
                 SELECT 1 FROM agents a WHERE a.agent_id = phone_numbers.agent_id
           )
        """
    )
    op.execute(
        """
        UPDATE phone_numbers
           SET agent_id = NULL
         WHERE agent_id IS NOT NULL
           AND EXISTS (
                 SELECT 1 FROM agents a
                  WHERE a.agent_id = phone_numbers.agent_id
                    AND a.status <> 'active'
           )
        """
    )

    inspector = sa.inspect(bind)
    fks = inspector.get_foreign_keys("phone_numbers")
    for fk in fks:
        if fk.get("referred_table") == "agents" and "agent_id" in (fk.get("constrained_columns") or []):
            op.drop_constraint(fk["name"], "phone_numbers", type_="foreignkey")
            op.create_foreign_key(
                fk["name"],
                "phone_numbers",
                "agents",
                ["agent_id"],
                ["agent_id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for fk in inspector.get_foreign_keys("phone_numbers"):
        if fk.get("referred_table") == "agents" and "agent_id" in (fk.get("constrained_columns") or []):
            op.drop_constraint(fk["name"], "phone_numbers", type_="foreignkey")
            op.create_foreign_key(
                fk["name"], "phone_numbers", "agents", ["agent_id"], ["agent_id"]
            )
    op.drop_index("ix_leads_tenant_agent", table_name="leads")
    op.drop_index("ix_leads_agent_id", table_name="leads")
    op.drop_column("leads", "agent_id")