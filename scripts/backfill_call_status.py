"""Backfill `calls.status` from the fields already recorded on each row.

The column is intentionally nullable so the migration is instant, but backfilling it
means the console's status filters are index-backed from day one instead of relying
on read-time derivation forever. Idempotent and safe to re-run.
"""
from __future__ import annotations

import asyncio

from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()

from server.call.call_status import status_for_record  # noqa: E402
from server.db.connection import get_session_factory, init_db  # noqa: E402

BATCH = 500


async def main() -> int:
    if not await init_db():
        print("DATABASE_URL is not configured")
        return 2
    factory = get_session_factory()
    assert factory is not None

    updated = 0
    total = 0
    async with factory() as session:
        while True:
            rows = (
                await session.execute(
                    text(
                        "SELECT call_id, direction, duration_sec, disposition, end_reason, ended_at "
                        "FROM calls WHERE status IS NULL ORDER BY started_at LIMIT :n"
                    ),
                    {"n": BATCH},
                )
            ).mappings().all()
            if not rows:
                break
            for row in rows:
                record = dict(row)
                # The column is NULL for these rows, so this re-derives on read.
                record["status"] = None
                await session.execute(
                    text("UPDATE calls SET status = :status WHERE call_id = :cid"),
                    {"status": status_for_record(record), "cid": row["call_id"]},
                )
                updated += 1
            total += len(rows)
            await session.commit()
            if len(rows) < BATCH:
                break

        remaining = (
            await session.execute(
                text("SELECT count(*) FROM calls WHERE status IS NULL")
            )
        ).scalar()
        breakdown = (
            await session.execute(
                text("SELECT status, count(*) FROM calls GROUP BY status ORDER BY 2 DESC")
            )
        ).all()

    print(f"scanned {total} row(s), backfilled {updated}, still NULL: {remaining}")
    print("status distribution:", breakdown)
    return 0 if not remaining else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
