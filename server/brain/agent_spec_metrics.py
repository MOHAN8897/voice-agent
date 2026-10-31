"""
Agent Spec Metrics & Shadow Mode Pipeline.
Tracks extraction sources, verifier failures, user input rate, fallback rate, and shadow mode comparisons.
"""
from __future__ import annotations

import threading
import time
from typing import Any


class AgentSpecMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._total_extractions = 0
        self._sources: dict[str, int] = {}
        self._verifier_failures = 0
        self._needs_user_input_count = 0
        self._fallback_count = 0
        self._shadow_comparisons = 0
        self._shadow_discrepancies = 0
        self._durations: list[float] = []

    def record_extraction(
        self,
        *,
        source: str,
        duration_sec: float,
        verifier_passed: bool = True,
        needs_user_input: bool = False,
    ) -> None:
        with self._lock:
            self._total_extractions += 1
            src_key = source or "unknown"
            self._sources[src_key] = self._sources.get(src_key, 0) + 1
            if not verifier_passed:
                self._verifier_failures += 1
            if needs_user_input:
                self._needs_user_input_count += 1
            if "fallback" in src_key.lower():
                self._fallback_count += 1
            self._durations.append(duration_sec)
            # Keep bounded memory
            if len(self._durations) > 1000:
                self._durations = self._durations[-500:]

    def record_shadow_comparison(
        self,
        *,
        session_id: str,
        old_agent_name: str,
        new_agent_name: str,
        discrepancy: bool,
    ) -> None:
        with self._lock:
            self._shadow_comparisons += 1
            if discrepancy:
                self._shadow_discrepancies += 1

    def get_summary(self) -> dict[str, Any]:
        with self._lock:
            total = self._total_extractions
            v_fail_rate = (self._verifier_failures / total) if total > 0 else 0.0
            input_rate = (self._needs_user_input_count / total) if total > 0 else 0.0
            fb_rate = (self._fallback_count / total) if total > 0 else 0.0
            avg_dur = (sum(self._durations) / len(self._durations)) if self._durations else 0.0
            return {
                "total_extractions": total,
                "sources": dict(self._sources),
                "verifier_failures": self._verifier_failures,
                "verifier_failure_rate": round(v_fail_rate, 4),
                "needs_user_input_count": self._needs_user_input_count,
                "needs_user_input_rate": round(input_rate, 4),
                "fallback_count": self._fallback_count,
                "fallback_rate": round(fb_rate, 4),
                "shadow_comparisons": self._shadow_comparisons,
                "shadow_discrepancies": self._shadow_discrepancies,
                "avg_duration_sec": round(avg_dur, 4),
            }

    def reset(self) -> None:
        with self._lock:
            self._total_extractions = 0
            self._sources.clear()
            self._verifier_failures = 0
            self._needs_user_input_count = 0
            self._fallback_count = 0
            self._shadow_comparisons = 0
            self._shadow_discrepancies = 0
            self._durations.clear()


spec_metrics = AgentSpecMetrics()
