"""Backfill `calls.status_tags` from outcomes already written to disk.

The tag column is populated by the post-call pipeline for new calls. This script
brings historical calls in line without re-running the LLM: it re-derives the
deterministic tags and re-merges the model's stored choices. Idempotent and safe
to re-run.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()

from server.call.outcome_schema import derive_status_tags  # noqa: E402
from server.call.paths import calls_root  # noqa: E402
from server.call.post_call_pipeline import read_outcome  # noqa: E402
from server.db.connection import get_session_factory, init_db  # noqa: E402
from server.utils.logger import logger  # noqa: E402

BATCH = 500


def _tags_for(call_id: str) -> list[str] | None:
    outcome = read_outcome(call_id)
    if not outcome:
        return None
    facts = outcome.get("facts") or outcome.get("extracted_fields") or {}
    return derive_status_tags(
        outcome.get("disposition"),
        facts if isinstance(facts, dict) else {},
        next_action=outcome.get("next_action"),
        objections=outcome.get("objections"),
        model_tags=outcome.get("tags"),
        custom_tags=outcome.get("custom_tags"),
        disclosure_status=outcome.get("disclosure_status"),
    )


async def main() -> int:
    if not await init_db():
        print("DATABASE_URL is not configured")
        return 2
    factory = get_session_factory()
    assert factory is not None

    root: Path = calls_root()
    updated = scanned = skipped = 0
    async with factory() as session:
        while True:
            rows = (
                await session.execute(
                    text(
                        "SELECT call_id FROM calls "
                        "WHERE status_tags = '{}' ORDER BY started_at LIMIT :n"
                    ),
                    {"n": BATCH},
                )
            ).mappings().all()
            if not rows:
                break
            for row in rows:
                call_id = str(row["call_id"])
                scanned += 1
                if not (root / call_id).is_dir():
                    skipped += 1
                    continue
                tags = _tags_for(call_id)
                if not tags:
                    skipped += 1
                    continue
                await session.execute(
                    text("UPDATE calls SET status_tags = :tags WHERE call_id = :cid"),
                    {"tags": tags, "cid": call_id},
                )
                updated += 1
            await session.commit()
            if len(rows) < BATCH:
                break

        remaining = (
            await session.execute(text("SELECT count(*) FROM calls WHERE status_tags = '{}'"))
        ).scalar()

    logger.info(
        "[TAGS] backfill scanned=%s updated=%s without_outcome=%s remaining_empty=%s",
        scanned,
        updated,
        skipped,
        remaining,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
