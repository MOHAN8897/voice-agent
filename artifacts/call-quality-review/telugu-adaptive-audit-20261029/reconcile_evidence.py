"""Read-only reconciliation by source call ID, including a caller-changed number."""
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from environment import OUT, setup, write, source_manifest


async def main():
    os.environ["AUDIT_RESUME"] = "1"
    _, _, manifest = await setup()
    from sqlalchemy import select
    from server.db.connection import get_session_factory, close_db
    from server.db.models.followup_models import FollowUpJob
    reconciled = {}
    async with get_session_factory()() as db:
        for path in (OUT / "sessions").glob("*.json"):
            case = json.loads(path.read_text(encoding="utf-8"))
            rows = (await db.scalars(select(FollowUpJob).where(
                FollowUpJob.tenant_id == uuid.UUID(case["agent"]["tenant_id"]),
                FollowUpJob.agent_id == uuid.UUID(case["agent"]["agent_id"]),
                FollowUpJob.source_id == case["call_id"]))).all()
            reconciled[case["scenario"]["id"]] = [{c.key: getattr(row, c.key) for c in row.__table__.columns} for row in rows]
    write("reconciled-followup-jobs.json", reconciled)
    after = source_manifest()
    write("final-source-drift.json", {k: {"before": v, "after": after.get(k)} for k, v in manifest["source_hashes"].items() if after.get(k) != v})
    await close_db()
    print(json.dumps({"reconciled_cases": len(reconciled), "source_drift": sum(after.get(k) != v for k, v in manifest["source_hashes"].items())}))


if __name__ == "__main__":
    asyncio.run(main())
