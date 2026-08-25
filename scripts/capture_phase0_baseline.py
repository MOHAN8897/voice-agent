#!/usr/bin/env python3
"""Capture Phase 0 regression baselines into baselines/phase0_metrics.json."""
from __future__ import annotations

import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmark_results.json"
OUT = ROOT / "baselines" / "phase0_metrics.json"


def _percentile(data: list[float], p: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    k = (len(s) - 1) * (p / 100)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def main() -> None:
    baseline = {
        "captured_at": "2026-08-25",
        "phase": "phase0_baseline",
        "source": str(BENCH.name),
        "metrics": {},
    }
    if BENCH.exists():
        data = json.loads(BENCH.read_text(encoding="utf-8"))
        turns = data.get("runs", {}).get("test_a_20", {}).get("turns", [])
        steady = [t["ttft_ms"] for t in turns if t.get("turn", 0) > 1 and t.get("ttft_ms")]
        ratios = [t["cache_ratio"] for t in turns if t.get("turn", 0) >= 2 and t.get("cache_ratio") is not None]
        baseline["metrics"] = {
            "brain_ttft_p50_ms": round(_percentile(steady, 50)) if steady else None,
            "brain_ttft_p95_ms": round(_percentile(steady, 95)) if steady else None,
            "cache_hit_rate_after_turn_2": round(statistics.mean(ratios), 3) if ratios else None,
            "stt_final_latency_p50_ms": None,
            "stt_final_latency_p95_ms": None,
            "tts_first_chunk_p50_ms": None,
            "e2e_time_to_first_audio_s": {"min": 0.9, "max": 1.6, "budget_note": "ARCHITECTURE.md target"},
            "barge_in_tests": "test_live_barge_policy.py — 100% pass required",
        }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
