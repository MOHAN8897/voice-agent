"""Make an in-flight number reservation exclusive per E.164.

`ix_number_reservations_e164` was a plain non-unique index, so two concurrent
buyers of the same DID both passed the "already reserved?" check and both
inserted. The unique constraint turns the loser into an IntegrityError at the
database level instead of a silently double-sold number.

Expired rows are cleared before each insert (the purchase path deletes its own
reservation), so the constraint never blocks a legitimate retry.
"""
from __future__ import annotations

from alembic import op

revision: str = "022_reservation_e164_unique"
down_revision: str | None = "021_kyc_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Reservations whose TTL elapsed are dead rows; the unique index would make
    # them block the number forever.
    op.execute("DELETE FROM number_reservations WHERE expires_at <= now()")
    op.create_index(
        "uq_number_reservations_e164_live",
        "number_reservations",
        ["e164"],
        unique=True,
    )


def downgrade() -> None:
    op.execute("DELETE FROM number_reservations")
    op.create_index("ix_number_reservations_e164", "number_reservations", ["e164"])