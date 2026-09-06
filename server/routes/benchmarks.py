"""
Benchmark routes — PRD §5 benchmark APIs.
Returns 403 when ENABLE_BENCHMARKS=false (default) for mutating/session routes.
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from server.benchmark.session_store import (
    cancel_session,
    create_session,
    get_session,
    list_scenarios,
    list_sessions,
    start_session,
    METRIC_KEYS,
)
from server.services.dev_runtime import benchmarks_enabled

router = APIRouter()


def _require_benchmarks() -> None:
    if not benchmarks_enabled():
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "forbidden",
                    "message": "Benchmarks are disabled. Set ENABLE_BENCHMARKS=true in Environment.",
                }
            },
        )


class CombinationPick(BaseModel):
    tier: str
    combination_id: str | None = None
    label: str | None = None


class BenchmarkSessionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    environment: Literal["development", "staging", "production"] = "development"
    languages: list[str] = Field(default_factory=lambda: ["te-IN"])
    scenario_ids: list[str] = Field(..., min_length=1)
    combinations: list[CombinationPick] = Field(..., min_length=1)
    notes: str | None = None


@router.get("/api/benchmarks/status")
async def benchmarks_status():
    enabled = benchmarks_enabled()
    return {
        "enabled": enabled,
        "message": (
            "Benchmark sessions available."
            if enabled
            else "Set ENABLE_BENCHMARKS=true in Dev Environment to create and run sessions."
        ),
    }


@router.get("/api/test-scenarios")
async def test_scenarios():
    return {"scenarios": list_scenarios()}


@router.get("/api/benchmark-sessions")
async def benchmark_sessions_list():
    _require_benchmarks()
    return {"sessions": list_sessions()}


@router.get("/api/benchmarks")
async def list_benchmarks_alias():
    _require_benchmarks()
    return {"runs": list_sessions(), "sessions": list_sessions()}


@router.post("/api/benchmark-sessions")
async def benchmark_sessions_create(body: BenchmarkSessionCreate):
    _require_benchmarks()
    valid_ids = {s["id"] for s in list_scenarios()}
    for sid in body.scenario_ids:
        if sid not in valid_ids:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "validation_error", "message": f"Unknown scenario: {sid}"}},
            )
    rec = create_session(body.model_dump())
    return rec


@router.get("/api/benchmark-sessions/{session_id}")
async def benchmark_session_get(session_id: str):
    _require_benchmarks()
    rec = get_session(session_id)
    if not rec:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Session not found"}})
    return rec


@router.post("/api/benchmark-sessions/{session_id}/start")
async def benchmark_session_start(session_id: str):
    _require_benchmarks()
    rec = start_session(session_id)
    if not rec:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Session not found"}})
    return rec


@router.post("/api/benchmark-sessions/{session_id}/cancel")
async def benchmark_session_cancel(session_id: str):
    _require_benchmarks()
    rec = cancel_session(session_id)
    if not rec:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Session not found"}})
    return rec


@router.get("/api/benchmark-sessions/{session_id}/results")
async def benchmark_session_results(session_id: str):
    _require_benchmarks()
    rec = get_session(session_id)
    if not rec:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Session not found"}})
    winners = _compute_winners(rec.get("results") or [])
    return {
        "session_id": session_id,
        "status": rec.get("status"),
        "results": rec.get("results") or [],
        "winners_per_metric": winners,
        "runner_note": rec.get("runner_note"),
        "metric_keys": list(METRIC_KEYS),
    }


@router.get("/api/benchmarks/{run_id}")
async def get_benchmark_alias(run_id: str):
    return await benchmark_session_get(run_id)


def _compute_winners(results: list[dict[str, Any]]) -> dict[str, Any]:
    winners: dict[str, Any] = {}
    for metric in METRIC_KEYS:
        ranked = [
            r for r in results
            if r.get("metrics", {}).get(metric) is not None
        ]
        if not ranked:
            winners[metric] = None
            continue
        best = min(ranked, key=lambda r: r["metrics"][metric] if metric != "llm_quality" and metric != "tts_quality" and metric != "stt_accuracy" and metric != "reliability" else -r["metrics"][metric])
        winners[metric] = {
            "combination_id": best.get("combination_id"),
            "scenario_id": best.get("scenario_id"),
            "value": best["metrics"][metric],
        }
    return winners
