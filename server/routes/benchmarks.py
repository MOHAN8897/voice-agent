"""
Benchmark route stub — server/routes/benchmarks.py
Returns 403 when ENABLE_BENCHMARKS=false (default).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from server.config.env import get_settings

router = APIRouter()


def _require_benchmarks():
    if not get_settings().enable_benchmarks:
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "forbidden", "message": "Benchmarks are disabled. Set ENABLE_BENCHMARKS=true."}},
        )


@router.get("/api/benchmarks")
async def list_benchmarks():
    _require_benchmarks()
    return {"runs": [], "message": "Benchmark UI integration — Phase 5"}


@router.get("/api/benchmarks/{run_id}")
async def get_benchmark(run_id: str):
    _require_benchmarks()
    return {"run_id": run_id, "status": "not_found"}
