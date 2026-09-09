"""Tests for production launch service (TEST 10)."""
from __future__ import annotations

import json
from pathlib import Path

from server.services import production_launch as pl


def test_build_launch_checklist_runbooks_present(monkeypatch):
    class S:
        enable_call_archive = True
        voice_agent_tier = "medium"
        canary_enabled = False
        data_path = Path("/tmp/launch-test")

    monkeypatch.setattr(pl, "get_settings", lambda: S())
    monkeypatch.setattr(pl, "_scan_call_archives", lambda **_: [{"compiled_brain_version": "cb_v1"}])
    root = pl._project_root()
    launch = pl.build_launch_checklist(
        telnyx_checklist={
            "international_india": True,
            "account_balance_ok": True,
            "phone_number_active": True,
            "webhook_configured": True,
        },
        canary_overall=True,
    )
    assert launch["areas"]["support"]["all_runbooks_present"] is True
    assert launch["areas"]["agent"]["has_promoted_brain"] is True
    assert (root / "architecture/integrations/telnyx-validation-pipeline.md").is_file()


def test_compute_production_slos_pass(monkeypatch, tmp_path):
    from datetime import UTC, datetime

    class S:
        data_path = tmp_path
        app_environment = "production"

    monkeypatch.setattr(pl, "get_settings", lambda: S())
    import server.services.production_canary as pc

    monkeypatch.setattr(pc, "get_settings", lambda: S())

    now = 1_700_000_000.0
    monkeypatch.setattr(pl.time, "time", lambda: now)
    monkeypatch.setattr(pc.time, "time", lambda: now)
    ts = datetime.fromtimestamp(now - 3600, UTC).isoformat()

    calls = tmp_path / "calls" / "c1"
    calls.mkdir(parents=True)
    (calls / "meta.json").write_text(
        json.dumps(
            {
                "call_id": "c1",
                "channel": "pstn",
                "ended_at": ts,
                "end_reason": "pstn_hangup",
                "compiled_brain_version": "cb_v1",
                "resolved_stack": {"combination_id": "combo1"},
            }
        ),
        encoding="utf-8",
    )
    (calls / "trace.json").write_text(
        json.dumps({"turns": [{"e2e_ms": 2000, "llm_ttft_ms": 1800}]}),
        encoding="utf-8",
    )
    (calls / "transcript.jsonl").write_text('{"role":"user","text":"hi"}\n', encoding="utf-8")

    events = tmp_path / "canary" / "events.jsonl"
    events.parent.mkdir(parents=True)
    events.write_text(
        json.dumps(
            {
                "ts": ts,
                "call_id": "c1",
                "bidirectional_ok": True,
                "failures": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(pl.time, "time", lambda: now)
    result = pl.compute_production_slos(hours=168)
    assert result["gates"]["bidirectional_ok_rate"] is True
    assert result["gates"]["p95_e2e_turn_ms"] is True
    assert result["gates"]["failed_calls_no_archive"] is True


def test_score_release_gates():
    ok = pl.score_release_gates(test0_passed=True, canary_overall=True)
    assert ok["overall"] is True
    bad = pl.score_release_gates(test0_passed=False, canary_overall=True)
    assert bad["overall"] is False
