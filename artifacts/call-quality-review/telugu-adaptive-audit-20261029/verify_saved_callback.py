"""Advance an actual live-call callback through the real durable scheduler.

Only final outbound transport is simulated. Never sleeps six hours or calls a phone.
"""
from __future__ import annotations

import asyncio
import copy
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from environment import OUT, CASE, ACTOR, NETWORK, setup, write


async def main():
    os.environ["AUDIT_RESUME"] = "1"
    _, _, manifest = await setup()
    CASE.set("saved_callback_scheduler")
    ACTOR.set("scheduler")
    from sqlalchemy import select
    from server.db.connection import get_session_factory, close_db
    from server.db.models.entities import CallCallback
    from server.db.models.followup_models import FollowUpJob
    from server.db.models.phase5_models import DncEntry
    from server.services.saas import followup_service as service
    from server.services.saas import telephony_orchestrator
    from server.services.saas.followup_policy import FollowUpConfig
    from server.services.saas.tenant_guard import SubscriberPrincipal

    case = json.loads((OUT / "sessions/A_callback_dispatch_repeat.json").read_text(encoding="utf-8"))
    agent = case["agent"]
    tid, aid = uuid.UUID(agent["tenant_id"]), uuid.UUID(agent["agent_id"])
    principal = SubscriberPrincipal(uuid.UUID(agent["user_id"]), tid, "customer_admin",
        f"audit-{uuid.UUID(agent['user_id']).hex}@example.invalid")
    revision = (await service.read_policy(tid, aid))["revision"]
    await service.save_policy(principal, aid, FollowUpConfig(enabled=True, callbackMode="automatic",
        missedMode="off", timezone="Asia/Kolkata", weekdays=list(range(7)),
        startTime="00:00", endTime="23:59", cooldownMinutes=30), revision, True)
    jid = uuid.UUID(case["db"]["jobs"][0]["id"])
    async def snapshot(job_id):
        async with get_session_factory()() as db:
            row = await db.scalar(select(FollowUpJob).where(FollowUpJob.tenant_id == tid, FollowUpJob.id == job_id))
            return {c.key: copy.deepcopy(getattr(row, c.key)) for c in row.__table__.columns}

    result = {"schema": manifest["schema"], "source_case": case["scenario"]["id"], "checks": []}
    before = await snapshot(jid)
    result["before"] = before
    clock = [datetime.now(timezone.utc)]
    dial = AsyncMock(return_value={"ok": True, "call_control_id": "audit-scheduled-control"})
    # The real scheduler, tenant resolution, brain ownership lookup and journal remain real.
    with patch.object(service, "now_utc", lambda: clock[0]), patch.object(telephony_orchestrator, "subscriber_outbound", dial):
        await service._process(jid)
        planned = await snapshot(jid)
        result["planned"] = planned
        result["checks"].append({"name": "live_Telugu_six_hour_time_resolved", "pass": planned["status"] == "scheduled"})
        caller_at = datetime.fromisoformat(before["payload"]["recentTurns"][-1]["at"].replace("Z", "+00:00"))
        if planned.get("due_at"):
            result["resolved_delay_seconds"] = (planned["due_at"] - caller_at).total_seconds()
            result["checks"].append({"name": "six_hours_anchored_to_caller_turn", "pass": abs(result["resolved_delay_seconds"] - 21600) < 1})
            clock[0] = planned["due_at"] - timedelta(seconds=1)
            await service._process(jid)
            result["checks"].append({"name": "no_early_dispatch", "pass": dial.await_count == 0})
            clock[0] = planned["due_at"]
            await service._process(jid)
            result["after_dispatch"] = await snapshot(jid)
            result["checks"].append({"name": "dispatch_at_due_time", "pass": dial.await_count == 1 and result["after_dispatch"]["status"] == "dialed"})
            await service._process(jid)
            result["checks"].append({"name": "repeat_worker_does_not_redial", "pass": dial.await_count == 1})
        # A second synthetic job for that exact tenant/number must be suppressed by DND.
        blocked_id = uuid.uuid4()
        async with get_session_factory()() as db:
            existing = await db.scalar(select(DncEntry).where(DncEntry.tenant_id == tid, DncEntry.phone_e164 == case["phone"]))
            if existing:
                existing.active = True
            else:
                db.add(DncEntry(tenant_id=tid, phone_e164=case["phone"], active=True))
            db.add(FollowUpJob(id=blocked_id, tenant_id=tid, agent_id=aid, origin_key="audit-dnd-" + uuid.uuid4().hex,
                source_id=case["call_id"], kind="callback", phone=case["phone"], status="scheduled", reason="requested_time_resolved",
                payload={}, due_at=clock[0], expires_at=clock[0] + timedelta(days=1), attempts=0,
                authorized_by=principal.user_id, billing_tenant_id=tid))
            await db.commit()
        previous_count = dial.await_count
        await service._process(blocked_id)
        suppressed = await snapshot(blocked_id)
        result["dnd_job"] = suppressed
        result["checks"].append({"name": "DND_prevents_callback_dispatch", "pass": suppressed["reason"] == "do_not_call" and dial.await_count == previous_count})
        result["outbound_mock_calls"] = dial.await_count
    async with get_session_factory()() as db:
        rows = (await db.scalars(select(CallCallback).where(CallCallback.tenant_id == tid,
            CallCallback.original_call_id == uuid.UUID(case["call_id"])))).all()
        result["journal"] = [{c.key: getattr(row, c.key) for c in row.__table__.columns} for row in rows]
    result["all_pass"] = all(c["pass"] for c in result["checks"])
    write("saved-callback-scheduler.json", result)
    write("scheduler-network.json", NETWORK)
    await close_db()
    print(json.dumps({"all_pass": result["all_pass"], "checks": result["checks"]}))


if __name__ == "__main__":
    asyncio.run(main())
