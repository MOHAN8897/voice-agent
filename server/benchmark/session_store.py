"""In-memory benchmark sessions — v1 store until PostgreSQL benchmark_runs."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

_SESSIONS: dict[str, dict[str, Any]] = {}

BUILTIN_SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "greeting_te",
        "name": "Telugu greeting",
        "language": "te-IN",
        "description": "Caller greets and asks who is calling.",
    },
    {
        "id": "property_inquiry",
        "name": "Property inquiry",
        "language": "te-IN",
        "description": "Budget, location, and timeline capture.",
    },
    {
        "id": "callback_request",
        "name": "Callback request",
        "language": "te-IN",
        "description": "Schedule follow-up and confirm phone number.",
    },
    {
        "id": "english_switch",
        "name": "English switch",
        "language": "en-IN",
        "description": "Mid-call language switch handling.",
    },
]

METRIC_KEYS = ("latency_ms", "stt_accuracy", "llm_quality", "tts_quality", "reliability", "cost_inr")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def list_scenarios() -> list[dict[str, Any]]:
    return list(BUILTIN_SCENARIOS)


def list_sessions() -> list[dict[str, Any]]:
    return sorted(_SESSIONS.values(), key=lambda s: s.get("created_at") or "", reverse=True)


def get_session(session_id: str) -> dict[str, Any] | None:
    return _SESSIONS.get(session_id)


def create_session(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = str(uuid.uuid4())
    combinations = payload.get("combinations") or []
    scenarios = payload.get("scenario_ids") or []
    estimated_runs = len(combinations) * len(scenarios) if combinations and scenarios else 0
    record = {
        "session_id": session_id,
        "name": payload.get("name") or "Benchmark session",
        "environment": payload.get("environment") or "development",
        "languages": payload.get("languages") or ["te-IN"],
        "scenario_ids": scenarios,
        "combinations": combinations,
        "estimated_runs": estimated_runs,
        "status": "draft",
        "created_at": _utcnow(),
        "started_at": None,
        "completed_at": None,
        "results": [],
        "notes": payload.get("notes") or "",
    }
    _SESSIONS[session_id] = record
    return record


def start_session(session_id: str) -> dict[str, Any]:
    rec = _SESSIONS.get(session_id)
    if not rec:
        return None
    rec["status"] = "completed"
    rec["started_at"] = _utcnow()
    rec["completed_at"] = _utcnow()
    rec["results"] = _build_result_skeleton(rec)
    rec["runner_note"] = (
        "Session recorded. Automated scenario execution worker is not yet wired — "
        "metrics below are placeholders until the benchmark runner populates trace-backed scores."
    )
    return rec


def cancel_session(session_id: str) -> dict[str, Any] | None:
    rec = _SESSIONS.get(session_id)
    if not rec:
        return None
    if rec.get("status") in ("completed", "cancelled"):
        return rec
    rec["status"] = "cancelled"
    rec["completed_at"] = _utcnow()
    return rec


def _build_result_skeleton(rec: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for combo in rec.get("combinations") or []:
        combo_id = combo.get("combination_id") or combo.get("tier") or "unknown"
        for scenario_id in rec.get("scenario_ids") or []:
            out.append(
                {
                    "combination_id": combo_id,
                    "tier": combo.get("tier"),
                    "scenario_id": scenario_id,
                    "metrics": {k: None for k in METRIC_KEYS},
                    "status": "pending_runner",
                }
            )
    return out


def reset_for_tests() -> None:
    _SESSIONS.clear()
