"""Sliding-window session enforcement on refresh tokens.

Audit finding: `JWT_REFRESH_TTL_DAYS=30` plus a client that silently re-refreshed on
every 401 meant one unattended tab could keep a session alive for 30 continuous days
with no re-authentication — an operator who walked away from an unlocked console came
back to a still-authenticated session.

Two columns make the policy enforceable server-side rather than only in the browser:

  * `last_active_at`       — when this token was last presented. A refresh older than
                             `SESSION_IDLE_TIMEOUT_MINUTES` is refused.
  * `absolute_expires_at`  — hard ceiling for one sign-in (`SESSION_ABSOLUTE_MAX_HOURS`),
                             independent of activity, so a machine held open by a
                             script still has to re-authenticate periodically.

Existing rows are backfilled from `created_at` so a token minted before this
migration is judged from its own age instead of looking infinitely active.

Safe to re-run: the ADD COLUMN guards are idempotent and the backfill only fills
columns that are NULL.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "027_session_sliding_window"
down_revision: str | None = "026_backfill_browser_test_calls"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    if not _has_column("refresh_tokens", "last_active_at"):
        op.add_column(
            "refresh_tokens",
            sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        )
    if not _has_column("refresh_tokens", "absolute_expires_at"):
        op.add_column(
            "refresh_tokens",
            sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=True),
        )

    # A token minted before this migration was created at created_at, so that is the
    # honest floor for its activity window.
    op.execute(
        """
        UPDATE refresh_tokens
           SET last_active_at = created_at
         WHERE last_active_at IS NULL
        """
    )
    # Absolute ceiling defaults to the token's own 30-day expiry so the migration
    # cannot shorten (or lengthen) any session that was already issued.
    op.execute(
        """
        UPDATE refresh_tokens
           SET absolute_expires_at = expires_at
         WHERE absolute_expires_at IS NULL
        """
    )
    op.execute(
        "ALTER TABLE refresh_tokens ALTER COLUMN last_active_at SET NOT NULL"
    )
    op.execute(
        "ALTER TABLE refresh_tokens ALTER COLUMN absolute_expires_at SET NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_refresh_tokens_user_active "
        "ON refresh_tokens (user_id, last_active_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_refresh_tokens_user_active")
    if _has_column("refresh_tokens", "absolute_expires_at"):
        op.drop_column("refresh_tokens", "absolute_expires_at")
    if _has_column("refresh_tokens", "last_active_at"):
        op.drop_column("refresh_tokens", "last_active_at")