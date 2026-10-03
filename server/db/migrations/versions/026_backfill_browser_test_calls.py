"""Flag historical browser practice sessions as tests.

Migration 020 added `calls.is_test` with a default of FALSE and no backfill. The
column was introduced to keep browser practice runs out of the call history, but
every session that already existed was left flagged `False` — so 472 practice
sessions were being rendered as answered inbound calls in the console, which is
exactly the "inbound flow is showing web agent talk" symptom.

`channel = 'browser'` is the same predicate the application uses at write time
(`CallLifecycleService.start` defaults `is_test` to `channel == 'browser'`), so
backfilling on it repairs the data without guessing which calls were real.

Safe to re-run: it only ever sets `is_test` to TRUE, never FALSE.
"""
from __future__ import annotations

from alembic import op

revision: str = "026_backfill_browser_test_calls"
down_revision: str | None = "025_activity_log_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE calls
           SET is_test = TRUE
         WHERE channel = 'browser'
           AND is_test = FALSE
        """
    )


def downgrade() -> None:
    # Deliberately not reversed. Un-flagging would put hundreds of practice
    # sessions back into the call history, and there is no way to tell which of
    # the browser rows were the ones this migration touched.
    pass