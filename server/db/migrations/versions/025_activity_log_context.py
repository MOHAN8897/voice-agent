"""Make audit_log a usable activity log.

The table already recorded admin mutations, but it could not answer the question
an operator actually asks: "what just happened, and did any of it fail?" Three
gaps, all closed here.

1. `source` / `actor_kind` — every existing row has `actor = 'admin'`, because only
   admin routes called the recorder. Subscriber actions (number purchases, wallet
   top-ups, KYC sessions, calls) were invisible. `source` separates the writer.

2. `outcome` / `severity` — a purchase that was refused and one that succeeded were
   indistinguishable rows. Debugging starts from the failures, and they need to be
   findable without reading every payload.

3. Request context — `request_id`, `ip`, `user_agent` let one user action be traced
   across the request that caused it, including retries.

Existing rows are backfilled as `admin` / `ok` / `info` so history stays readable.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "025_activity_log_context"
down_revision: str | None = "024_lead_agent_ownership"
branch_labels = None
depends_on = None

_COLUMNS = [
    ("source", sa.String(20), "admin"),
    ("outcome", sa.String(20), "ok"),
    ("severity", sa.String(20), "info"),
    ("request_id", sa.String(64), None),
    ("ip", sa.String(64), None),
    ("user_agent", sa.String(400), None),
]

#: One unfiltered table with no index on time is a full scan on every page load.
_INDEXES = [
    ("ix_audit_log_created_at", ["created_at"]),
    ("ix_audit_log_action", ["action"]),
    ("ix_audit_log_source", ["source"]),
    ("ix_audit_log_actor", ["actor"]),
]


def upgrade() -> None:
    for name, type_, default in _COLUMNS:
        op.add_column(
            "audit_log",
            sa.Column(name, type_, nullable=True, server_default=default),
        )
    for name, cols in _INDEXES:
        op.create_index(name, "audit_log", cols)
    # Existing rows predate these concepts; labelling them is more honest than NULL.
    op.execute(
        """
        UPDATE audit_log
           SET source = 'admin',
               outcome = 'ok',
               severity = 'info'
         WHERE source IS NULL
        """
    )
    op.execute("ALTER TABLE audit_log ALTER COLUMN source SET NOT NULL")


def downgrade() -> None:
    for name, _cols in reversed(_INDEXES):
        op.drop_index(name, table_name="audit_log")
    for name, _type, _default in reversed(_COLUMNS):
        op.drop_column("audit_log", name)