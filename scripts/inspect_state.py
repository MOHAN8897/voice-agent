import asyncio
import json
from server.db.connection import init_db, get_session_factory
from server.db.models.entities import Agent, TierAssignment
from sqlalchemy import select

async def main():
    await init_db()
    factory = get_session_factory()
    async with factory() as db:
        tiers = (await db.execute(select(TierAssignment))).scalars().all()
        for t in tiers:
            print(f"=== TIER: {t.tier} (env={t.environment}) ===")
            print(json.dumps(t.stack_payload, indent=2))

asyncio.run(main())
