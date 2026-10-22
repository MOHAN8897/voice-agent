"""Tests for production canary service (TEST 9)."""
from __future__ import annotations

import json
from pathlib import Path

from server.services import production_canary as pc


def test_build_deploy_checklist_has_required_keys(monkeypatch):
    class S:
        app_environment = "production"
        enable_telnyx = True
        enable_call_archive = True
        canary_enabled = True
        canary_max_calls_per_day = 20
        recording_consent_required = False
        data_path = Path("/tmp/voice-agent-test")

    monkeypatch.setattr(pc, "get_settings", lambda: S())
    monkeypatch.setattr(pc, "public_api_base", lambda: "https://api.example.com")
    monkeypatch.setattr(pc, "ENABLE_PSTN_BARGE_IN", True)

    deploy = pc.build_deploy_checklist(telnyx_checklist={"ready_for_india": True, "webhook_configured": True})
    assert deploy["ready_for_smoke"] is True
    assert deploy["items"]["webhook_url"].endswith("/api/telnyx/webhook")


def test_assert_canary_outbound_blocked_when_over_limit(monkeypatch, tmp_path):
    class S:
        canary_enabled = True
        app_environment = "production"
        canary_max_calls_per_day = 2
        canary_allowed_destinations_csv = ""
        data_path = tmp_path

    monkeypatch.setattr(pc, "get_settings", lambda: S())
    events = tmp_path / "canary" / "events.jsonl"
    events.parent.mkdir(parents=True)
    for i in range(2):
        events.write_text(
            (events.read_text(encoding="utf-8") if events.exists() else "")
            + json.dumps({"ts": "2099-01-01T00:00:00+00:00", "call_id": f"c{i}"})
            + "\n",
            encoding="utf-8",
        )

    err = pc.assert_canary_outbound_allowed("+918897908470")
    assert err and "daily limit" in err


def test_assert_canary_allows_when_disabled(monkeypatch):
    class S:
        canary_enabled = False
        app_environment = "production"
        canary_max_calls_per_day = 1
        canary_allowed_destinations_csv = ""
        data_path = Path("/tmp/x")

    monkeypatch.setattr(pc, "get_settings", lambda: S())
    assert pc.assert_canary_outbound_allowed("+918897908470") is None


def test_score_canary_window_from_events(monkeypatch, tmp_path):
    from datetime import UTC, datetime

    class S:
        data_path = tmp_path

    monkeypatch.setattr(pc, "get_settings", lambda: S())
    now = 1_700_000_000.0
    monkeypatch.setattr(pc.time, "time", lambda: now)
    events = tmp_path / "canary" / "events.jsonl"
    events.parent.mkdir(parents=True)
    lines = []
    for i in range(10):
        ts = datetime.fromtimestamp(now - 3600 - i, UTC).isoformat()
        lines.append(
            json.dumps(
                {
                    "ts": ts,
                    "call_id": f"call-{i}",
                    "bidirectional_ok": True,
                    "failures": [],
                    "health_score": 90,
                }
            )
        )
    events.write_text("\n".join(lines) + "\n", encoding="utf-8")

    score = pc.score_canary_window(hours=48)
    assert score["bidirectional_ok_calls"] == 10
    assert score["gates"]["bidirectional_calls_gte_10"] is True
    assert score["overall"] is True
