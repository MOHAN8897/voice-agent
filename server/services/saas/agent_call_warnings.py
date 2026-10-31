"""Settings warnings an agent's recent calls reveal, read from outcomes already on disk.

Three things a business can fix and the calls themselves cannot:

* the recording disclosure is switched off;
* an after-call integration keeps being skipped because calls do not capture
  what it needs (an email for a Gmail draft, for example);
* callers keep asking questions the agent has no facts for, so it answers with
  its unknown-information line.

Read-only. Nothing here is a new judgement: every item comes from the agent row
or a finished call's outcome.json.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

#: Calls looked at per request; the newest first.
RECENT_CALL_LIMIT = 100
RECENT_DAYS = 30
QUESTION_LIMIT = 20


def summarize_outcomes(outcomes: list[tuple[str, str | None, dict[str, Any]]]) -> dict[str, Any]:
    """Aggregate (call_id, started_at, outcome) rows, newest first, into warnings."""
    from server.call.post_call_pipeline import POST_CALL_REQUIRED_DETAILS

    skipped: dict[str, dict[str, Any]] = {}
    questions: dict[str, dict[str, Any]] = {}
    for call_id, at, outcome in outcomes:
        for item in outcome.get("integration_results") or []:
            result = item.get("result") if isinstance(item, dict) else None
            if not isinstance(result, dict) or result.get("status") != "skipped":
                continue
            action = str(item.get("action") or "").upper()
            entry = skipped.setdefault(action, {"action": action, "count": 0, "missing": [], "lastCallId": call_id, "lastAt": at})
            entry["count"] += 1
            missing = result.get("missing") or list(POST_CALL_REQUIRED_DETAILS.get(action, ()))
            entry["missing"] = sorted({*entry["missing"], *(str(m) for m in missing)})
        for question in outcome.get("unanswered_questions") or []:
            text = str(question or "").strip()
            key = text.casefold().rstrip("?.! ")
            if not key:
                continue
            entry = questions.setdefault(key, {"question": text, "count": 0, "lastCallId": call_id, "lastAt": at})
            entry["count"] += 1
    # Most asked first; ties keep newest first (rows arrive newest first, sort is stable).
    ranked = sorted(questions.values(), key=lambda q: -q["count"])
    return {
        "skippedActions": sorted(skipped.values(), key=lambda s: -s["count"]),
        "unansweredQuestions": ranked[:QUESTION_LIMIT],
        "callsChecked": len(outcomes),
    }


async def agent_call_warnings(tenant_id: str, agent: Any) -> dict[str, Any]:
    from server.call.call_store import call_store
    from server.call.post_call_pipeline import read_outcome

    since = (datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)).isoformat()
    rows, _ = await call_store.list_calls(tenant_id=str(tenant_id), agent_id=str(agent.agent_id), since=since,
                                         limit=RECENT_CALL_LIMIT, max_limit=RECENT_CALL_LIMIT)

    def load() -> list[tuple[str, str | None, dict[str, Any]]]:
        out = []
        for row in rows:
            outcome = read_outcome(str(row.get("call_id")))
            if outcome:
                out.append((str(row.get("call_id")), row.get("started_at"), outcome))
        return out

    summary = summarize_outcomes(await asyncio.to_thread(load))
    return {"recordingDisclosureOff": not bool(getattr(agent, "recording_disclosure_enabled", False)), **summary}
