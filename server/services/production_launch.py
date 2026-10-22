"""Production launch — TEST 10 launch checklist, release gates, and SLO scoring."""
from __future__ import annotations

import json
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from server.config.env import get_settings
from server.services.production_canary import _load_events, score_canary_window

# Initial production SLO targets (telnyx-validation-pipeline.md TEST 10)
SLO_CONNECT_RATE = 0.98
SLO_BIDIRECTIONAL_RATE = 0.95
SLO_P95_E2E_MS = 6000
SLO_FAILED_NO_ARCHIVE = 0.0

_RUNBOOK_DOCS = (
    "architecture/integrations/telnyx-validation-pipeline.md",
    "architecture/integrations/two-way-voice-stream.md",
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 1.0
    return round(numerator / denominator, 4)


def _p95(values: list[int]) -> int | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return int(statistics.quantiles(values, n=20)[-1])


def _scan_call_archives(*, hours: int = 168) -> list[dict[str, Any]]:
    """Recent PSTN call archives with trace/meta for SLO computation."""
    settings = get_settings()
    root = settings.data_path / "calls"
    if not root.is_dir():
        return []
    since = time.time() - (hours * 3600)
    rows: list[dict[str, Any]] = []
    for call_dir in root.iterdir():
        if not call_dir.is_dir():
            continue
        meta_path = call_dir / "meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if meta.get("channel") != "pstn":
            continue
        ended = str(meta.get("ended_at") or "")
        ended_ts = call_dir.stat().st_mtime
        if ended:
            try:
                ended_ts = datetime.fromisoformat(ended.replace("Z", "+00:00")).timestamp()
            except ValueError:
                pass
        if ended_ts < since:
            continue
        trace: dict[str, Any] = {}
        trace_path = call_dir / "trace.json"
        if trace_path.exists():
            try:
                trace = json.loads(trace_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                trace = {}
        e2e_samples = [
            int(t.get("e2e_ms") or t.get("llm_ttft_ms") or 0)
            for t in (trace.get("turns") or [])
            if int(t.get("e2e_ms") or t.get("llm_ttft_ms") or 0) > 0
        ]
        rows.append(
            {
                "call_id": str(meta.get("call_id") or call_dir.name),
                "ended_at": ended,
                "end_reason": meta.get("end_reason"),
                "compiled_brain_version": meta.get("compiled_brain_version"),
                "combination_id": (meta.get("resolved_stack") or {}).get("combination_id"),
                "has_transcript": (call_dir / "transcript.jsonl").exists(),
                "has_mix": (call_dir / "mix.wav").exists(),
                "e2e_samples": e2e_samples,
                "connected": bool(ended or meta.get("end_reason")),
            }
        )
    rows.sort(key=lambda r: r.get("ended_at") or "", reverse=True)
    return rows


def build_launch_checklist(
    *,
    telnyx_checklist: dict[str, Any] | None = None,
    canary_overall: bool | None = None,
) -> dict[str, Any]:
    """TEST 10 launch checklist — operational readiness before GA."""
    settings = get_settings()
    root = _project_root()
    telnyx = telnyx_checklist or {}
    archives = _scan_call_archives(hours=168)
    brain_versions = sorted(
        {str(a.get("compiled_brain_version")) for a in archives if a.get("compiled_brain_version")}
    )

    runbooks = {doc: (root / doc).is_file() for doc in _RUNBOOK_DOCS}
    ci_yml = root / ".github" / "workflows" / "ci.yml"
    ci_has_pytest = False
    if ci_yml.is_file():
        text = ci_yml.read_text(encoding="utf-8")
        ci_has_pytest = "pytest" in text

    areas = {
        "telnyx": {
            "india_whitelist_or_verified": bool(
                telnyx.get("international_india") or telnyx.get("verified_numbers")
            ),
            "billing_balance_ok": bool(telnyx.get("account_balance_ok")),
            "phone_active": bool(telnyx.get("phone_number_active")),
            "webhook_configured": bool(telnyx.get("webhook_configured")),
        },
        "agent": {
            "call_archive_enabled": settings.enable_call_archive,
            "recent_brain_versions": brain_versions[:5],
            "has_promoted_brain": len(brain_versions) > 0,
            "tier_default": settings.voice_agent_tier,
        },
        "observability": {
            "pstn_media_flow": True,
            "call_archives": len(archives) > 0,
            "canary_log": (settings.data_path / "canary" / "events.jsonl").exists(),
        },
        "support": {
            "runbooks": runbooks,
            "all_runbooks_present": all(runbooks.values()),
        },
        "regression": {
            "ci_pytest_configured": ci_has_pytest,
            "test0_script": (root / "server" / "tests" / "test_pstn_voice_core.py").is_file(),
            "validation_pipeline_doc": (root / "architecture" / "integrations" / "telnyx-validation-pipeline.md").is_file(),
        },
        "canary": {
            "test9_passed": canary_overall if canary_overall is not None else None,
            "canary_enabled": settings.canary_enabled,
        },
    }

    required = [
        areas["telnyx"]["india_whitelist_or_verified"],
        areas["telnyx"]["billing_balance_ok"],
        areas["telnyx"]["phone_active"],
        areas["agent"]["call_archive_enabled"],
        areas["agent"]["has_promoted_brain"],
        areas["observability"]["call_archives"],
        areas["support"]["all_runbooks_present"],
        areas["regression"]["ci_pytest_configured"],
        areas["regression"]["validation_pipeline_doc"],
    ]
    if canary_overall is not None:
        required.append(bool(canary_overall))

    return {
        "areas": areas,
        "ready_for_launch": all(required),
        "ongoing_gates": [
            "TEST 0 pytest green on every PR",
            "Staging TEST 5 + TEST 6 on real handset before release",
            "Re-run diag_telnyx_sarvam_alignment.py if audio code touched",
            "Re-run TEST 7 on staging if barge-in code touched",
            "Canary 24h before promoting audio changes to production",
        ],
    }


def _connect_rate_target() -> float:
    settings = get_settings()
    if settings.app_environment != "production":
        return 0.95
    return SLO_CONNECT_RATE


def compute_production_slos(
    *,
    registry_rows: list[dict[str, Any]] | None = None,
    hours: int = 168,
) -> dict[str, Any]:
    """TEST 10 production SLOs from canary log + call archives + registry."""
    archives = _scan_call_archives(hours=hours)
    canary = score_canary_window(registry_rows=registry_rows, hours=hours)
    events = _load_events(since_ts=time.time() - (hours * 3600))

    registry = registry_rows or []
    dial_attempts = len(registry) or len(events) or len(archives)
    connected = sum(1 for r in registry if r.get("status") not in {None, "initiated", "failed"})
    if not registry:
        connected = sum(1 for a in archives if a.get("connected"))

    bidir_events = sum(1 for e in events if e.get("bidirectional_ok"))
    bidir_total = len(events) or len(archives)
    bidir_rate = _pct(bidir_events, bidir_total)

    e2e_all: list[int] = []
    for archive in archives:
        e2e_all.extend(archive.get("e2e_samples") or [])
    p95_e2e = _p95(e2e_all)

    archived_ids = {a["call_id"] for a in archives}
    registry_internal = {
        str(r.get("internal_call_id") or "") for r in registry if r.get("internal_call_id")
    }
    missing_archive = [
        cid for cid in registry_internal if cid and cid not in archived_ids
    ]

    connect_rate = _pct(connected, dial_attempts)
    connect_target = _connect_rate_target()

    slos = {
        "connect_rate": {
            "value": connect_rate,
            "target": connect_target,
            "pass": connect_rate >= connect_target,
            "connected": connected,
            "attempts": dial_attempts,
        },
        "bidirectional_ok_rate": {
            "value": bidir_rate,
            "target": SLO_BIDIRECTIONAL_RATE,
            "pass": bidir_rate >= SLO_BIDIRECTIONAL_RATE,
            "bidirectional_ok": bidir_events,
            "total": bidir_total,
        },
        "p95_e2e_turn_ms": {
            "value": p95_e2e,
            "target": SLO_P95_E2E_MS,
            "pass": p95_e2e is None or p95_e2e <= SLO_P95_E2E_MS,
            "samples": len(e2e_all),
        },
        "failed_calls_no_archive": {
            "value": len(missing_archive),
            "target": SLO_FAILED_NO_ARCHIVE,
            "pass": len(missing_archive) == 0,
            "missing_call_ids": missing_archive[:10],
        },
    }

    gates = {name: bool(s.get("pass")) for name, s in slos.items()}

    return {
        "window_hours": hours,
        "slos": slos,
        "gates": gates,
        "overall": all(gates.values()),
        "canary_window_pass": canary.get("overall"),
        "archive_count": len(archives),
    }


def score_release_gates(*, test0_passed: bool, canary_overall: bool) -> dict[str, Any]:
    """Ongoing release gate bundle for CI / pre-promote checks."""
    gates = {
        "test0_pytest": test0_passed,
        "canary_window": canary_overall,
    }
    return {"gates": gates, "overall": all(gates.values())}
