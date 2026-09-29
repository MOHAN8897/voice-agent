"""Ad-hoc check that the new tables and columns exist in the live database."""
from __future__ import annotations

from sqlalchemy import text

from dotenv import load_dotenv

load_dotenv()

from server.db.connection import get_session_factory  # noqa: E402

TABLES = ["calls", "call_attempts", "call_callbacks", "agent_telephony_profiles"]


async def main() -> int:
    from server.db.connection import init_db

    if not await init_db():
        print("DATABASE_URL is not configured")
        return 2
    factory = get_session_factory()
    if factory is None:
        print("DATABASE_URL is not configured")
        return 2
    missing = []
    async with factory() as conn:
        for table in TABLES:
            found = (
                await conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_name = :t"),
                    {"t": table},
                )
            ).scalar()
            print(f"{table:32} {'present' if found else 'MISSING'}")
            if not found:
                missing.append(table)

        status_col = (
            await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'calls' AND column_name = 'status'"
                )
            )
        ).scalar()
        print(f"{'calls.status':32} {'present' if status_col else 'MISSING'}")
        if not status_col:
            missing.append("calls.status")

        total = (await conn.execute(text("SELECT count(*) FROM calls"))).scalar()
        print(f"\nexisting call rows: {total}")
        if total:
            nulls = (
                await conn.execute(text("SELECT count(*) FROM calls WHERE status IS NULL"))
            ).scalar()
            print(f"rows with NULL status (legacy, derived on read): {nulls}")
            statuses = (
                await conn.execute(
                    text("SELECT status, count(*) FROM calls GROUP BY status ORDER BY 2 DESC")
                )
            ).all()
            print("materialised statuses:", statuses or "none yet")
    return 1 if missing else 0


if __name__ == "__main__":
    import asyncio

    raise SystemExit(asyncio.run(main()))
